"""Durable, resumable authorized Kite backfills and incremental imports."""
from datetime import date, timedelta
import json
import threading
import uuid

from . import config, provider
from .calendar import completed_daily_date
from .scanner import reference_scan_symbols
from .storage import now_iso

INTERVALS = {"day", "minute", "3minute", "5minute", "15minute", "30minute", "60minute"}
ACTIVE = {"queued", "running", "retrying"}


def require_authorization(interval="day"):
    if not config.DATA_RETENTION_AUTHORIZED or not config.HISTORICAL_ENABLED:
        raise ValueError("Historical import is blocked: HISTORICAL_ENABLED and explicit DATA_RETENTION_AUTHORIZED are required. No market candles have been stored by this request.")
    if interval != "day" and not config.INTRADAY_ENABLED:
        raise ValueError("Intraday storage authorization has not been enabled.")


class ImportService:
    def __init__(self, store, on_complete=None):
        self.store = store
        self.on_complete = on_complete
        self.stop_event = threading.Event()
        self.thread = None
        self.work_lock = threading.Lock()

    def start(self):
        with self.store.connection() as db:
            db.execute("UPDATE history_imports SET state='interrupted',error='Server restarted; resume from the last committed cursor.',updated_at=? WHERE state IN ('running','retrying')", (now_iso(),))
            db.execute("UPDATE history_imports SET state='cancelled',updated_at=? WHERE state='cancel_requested'", (now_iso(),))
        self.thread = threading.Thread(target=self._loop, daemon=True, name="divine-history-import")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _loop(self):
        while not self.stop_event.is_set():
            self.run_pending()
            self.stop_event.wait(1)

    def get(self, job_id):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM history_imports WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("Import job not found.")
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["symbols"] = json.loads(result.pop("symbols_json"))
        result["skipped"] = json.loads(result.pop("skipped_json"))
        return result

    def update(self, job_id, **fields):
        allowed = {"state", "symbols_json", "skipped_json", "symbol_index", "cursor_date", "candles_processed", "requests_completed", "attempts", "last_success_at", "error"}
        if set(fields) - allowed:
            raise ValueError("Invalid import progress field.")
        fields["updated_at"] = now_iso()
        with self.store.connection() as db:
            db.execute("UPDATE history_imports SET " + ",".join(key + "=?" for key in fields) + " WHERE id=?", (*fields.values(), job_id))

    def create(self, body):
        interval = str(body.get("interval", "day"))
        require_authorization(interval)
        if interval not in INTERVALS:
            raise ValueError("Unsupported candle interval.")
        raw_symbols = reference_scan_symbols() if body.get("all_approved") else body.get("symbols") or [body.get("symbol", "")]
        if not isinstance(raw_symbols, list) or not raw_symbols or not all(isinstance(s, str) for s in raw_symbols):
            raise ValueError("Choose approved stock symbols for this import.")
        symbols = list(dict.fromkeys(s.strip().upper() for s in raw_symbols))
        if set(symbols) - set(reference_scan_symbols()):
            raise ValueError("Import contains an instrument outside the approved available-candidate universe.")
        try:
            days = int(body.get("days", 365 if interval == "day" else 7))
            if not 1 <= days <= (1825 if interval == "day" else 30):
                raise ValueError("Daily backfills support 1–1825 calendar days; intraday backfills support 1–30.")
            end = date.fromisoformat(body["end"]) if body.get("end") else completed_daily_date()
            start = date.fromisoformat(body["start"]) if body.get("start") else end - timedelta(days=days - 1)
            if end > completed_daily_date() or start > end or (end - start).days >= (1825 if interval == "day" else 30):
                raise ValueError("Import must cover a supported range of completed sessions.")
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        if self.store.import_summary()["active_jobs"] >= 10:
            raise ValueError("Finish or cancel queued imports before starting more jobs.")
        job_id = uuid.uuid4().hex
        request = {"symbols": symbols, "interval": interval, "start": start.isoformat(), "end": end.isoformat()}
        with self.store.connection() as db:
            db.execute("INSERT INTO history_imports(id,state,created_at,updated_at,request_json,incremental) VALUES(?,?,?,?,?,?)",
                       (job_id, "queued", now_iso(), now_iso(), json.dumps(request), int(bool(body.get("incremental", False)))))
        return self.get(job_id)

    def control(self, job_id, operation):
        job = self.get(job_id)
        if operation == "resume":
            require_authorization(job["request"]["interval"])
            if job["state"] not in {"failed", "interrupted", "blocked_authorization"}:
                raise ValueError("Only failed, interrupted or authorization-blocked imports can resume.")
            self.update(job_id, state="queued", error=None)
        elif operation == "cancel":
            if job["state"] in {"completed", "cancelled"}:
                raise ValueError("Import is already finished.")
            self.update(job_id, state="cancel_requested" if job["state"] in {"running", "retrying"} else "cancelled")
        else:
            raise ValueError("Use resume or cancel.")
        return self.get(job_id)

    def run_pending(self):
        if not self.work_lock.acquire(blocking=False):
            return
        try:
            with self.store.connection() as db:
                row = db.execute("SELECT id FROM history_imports WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
                if not row:
                    return
                job_id = row["id"]
                db.execute("UPDATE history_imports SET state='running',updated_at=? WHERE id=?", (now_iso(), job_id))
            try:
                self._execute(job_id)
            except ValueError as exc:
                self.update(job_id, state="blocked_authorization" if not config.DATA_RETENTION_AUTHORIZED or not config.HISTORICAL_ENABLED else "failed", error=str(exc))
            except provider.ProviderError as exc:
                self.store.capability("historical", "unavailable", str(exc))
                self.update(job_id, state="failed", error=str(exc))
            except Exception:
                self.update(job_id, state="failed", error="Import stopped after an unexpected server error. Its last committed cursor is safe to resume.")
        finally:
            self.work_lock.release()

    def _execute(self, job_id):
        job = self.get(job_id)
        request, interval = job["request"], job["request"]["interval"]
        require_authorization(interval)
        candidates = provider.stock_names(request["symbols"])
        self.store.instrument_details(candidates)
        available = {d["symbol"] for d in candidates if d["is_equity"] and d.get("instrument_token")}
        if not job["symbols"]:
            symbols = [s for s in request["symbols"] if s in available]
            skipped = [{"symbol": d["symbol"], "reason": d.get("resolution_note") or "Unavailable in verified Kite instrument master"} for d in candidates if d["symbol"] not in available]
            self.update(job_id, symbols_json=json.dumps(symbols), skipped_json=json.dumps(skipped))
            job = self.get(job_id)
        else:
            symbols = job["symbols"]
            missing = [s for s in symbols[job["symbol_index"]:] if s not in available]
            if missing:
                raise ValueError("Previously resolved instruments are no longer available: " + ", ".join(missing))
        if not symbols:
            raise ValueError("None of the requested instruments resolved to verified Kite equity tokens.")
        end = date.fromisoformat(request["end"])
        batch_days = 180 if interval == "day" else 7 if interval == "minute" else 30
        for index in range(job["symbol_index"], len(symbols)):
            symbol = symbols[index]
            cursor = date.fromisoformat(job["cursor_date"]) if index == job["symbol_index"] and job["cursor_date"] else date.fromisoformat(request["start"])
            if job["incremental"] and not (index == job["symbol_index"] and job["cursor_date"]):
                prior = self.store.candles(symbol, interval, limit=1)
                if prior:
                    cursor = max(cursor, date.fromisoformat(prior[-1]["timestamp"][:10]) - timedelta(days=2))
            while cursor <= end:
                current = self.get(job_id)
                if current["state"] == "cancel_requested":
                    self.update(job_id, state="cancelled")
                    return
                if self.stop_event.is_set():
                    self.update(job_id, state="interrupted", error="Server stopped. Resume this job from the saved cursor.")
                    return
                require_authorization(interval)
                batch_end = min(end, cursor + timedelta(days=batch_days - 1))
                for attempt in range(config.IMPORT_RETRY_LIMIT):
                    if self.get(job_id)["state"] == "cancel_requested":
                        self.update(job_id, state="cancelled")
                        return
                    try:
                        require_authorization(interval)
                        bars = provider.historical_candles(symbol, cursor, batch_end, interval)
                        break
                    except provider.ProviderError as exc:
                        current = self.get(job_id)
                        self.update(job_id, attempts=current["attempts"] + 1, state="retrying", error=str(exc))
                        if attempt + 1 == config.IMPORT_RETRY_LIMIT:
                            raise
                        if self.stop_event.wait(min(30, 2 ** attempt)):
                            self.update(job_id, state="interrupted", error="Import interrupted during retry; cursor preserved.")
                            return
                require_authorization(interval)
                if self.get(job_id)["state"] == "cancel_requested":
                    self.update(job_id, state="cancelled")
                    return
                if any(not cursor.isoformat() <= str(b.get("date", ""))[:10] <= batch_end.isoformat() for b in bars):
                    raise ValueError("Provider returned candles outside the requested date window.")
                count = self.store.save_candles(symbol, bars, interval)
                current = self.get(job_id)
                # Upsert commits before cursor advancement. A crash between these
                # commits only replays one idempotent batch; it cannot skip candles.
                cursor = batch_end + timedelta(days=1)
                self.update(job_id, cursor_date=cursor.isoformat(), symbol_index=index,
                            candles_processed=current["candles_processed"] + count,
                            requests_completed=current["requests_completed"] + 1,
                            state="running", error=None, last_success_at=now_iso())
                self.store.capability("historical", "verified", "Authorized historical batch fetched and committed.")
            self.update(job_id, symbol_index=index + 1, cursor_date=None)
        self.update(job_id, state="completed", error=None)
        if self.on_complete:
            try:
                self.on_complete()
            except (ValueError, ImportError):
                pass  # A completed import does not imply a validated model exists.

    def schedule_incremental(self):
        if not config.HISTORY_AUTO_UPDATE_ENABLED or not config.DATA_RETENTION_AUTHORIZED or not config.HISTORICAL_ENABLED:
            return None
        if self.store.import_summary()["active_jobs"]:
            return None
        with self.store.connection() as db:
            symbols = [r["symbol"] for r in db.execute("SELECT DISTINCT symbol FROM candles WHERE interval='day'") if r["symbol"] in set(reference_scan_symbols())]
        if not symbols:
            return None
        return self.create({"symbols": symbols, "interval": "day", "days": 1825, "incremental": True})
