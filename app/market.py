"""One provider subscription/cache per process; fan out snapshots via SSE."""
from copy import deepcopy
from datetime import datetime, timedelta, time as dt_time
import math
import threading
import time
from zoneinfo import ZoneInfo

from . import config, provider
from .scanner import reference_scan_symbols, run_scan
from .calendar import session_state

TZ = ZoneInfo(config.APP_TIMEZONE)


def parse_time(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)
    try:
        stamp = datetime.fromisoformat(str(value))
        return stamp.replace(tzinfo=TZ) if stamp.tzinfo is None else stamp.astimezone(TZ)
    except (TypeError, ValueError):
        return None


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


class MarketService:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.fetch_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.ticker = None
        self.details = None
        self.rows = {}
        self.anchors = {}
        self.anchor_date = None
        self.scan_result = {"rows": [], "as_of": None, "matches": []}
        self.last_fetch = 0.0
        self.updated_at = None
        self.error = None
        self.stream_error = None
        self.transport = "unavailable"
        self.stream_connected = False
        self.last_stream_tick = 0.0
        self.token = None
        self.stream_attempt = 0.0
        self.sequence = 0
        self.symbols = reference_scan_symbols()
        self.allowed_symbols = set(self.symbols)

    def start(self):
        self.thread = threading.Thread(target=self._run, name="divine-market", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.ticker:
            self.ticker.close()
        if self.thread:
            self.thread.join(timeout=3)

    def _run(self):
        failures = 0
        last_snapshot = 0.0
        while not self.stop_event.is_set():
            try:
                if config.KITE_ACCESS_TOKEN:
                    # A new daily session invalidates the previous socket and token map.
                    if self.token != config.KITE_ACCESS_TOKEN:
                        if self.ticker:
                            self.ticker.close()
                        self.ticker = None
                        self.stream_connected = False
                        self.token = config.KITE_ACCESS_TOKEN
                        self.details = None
                        self.last_fetch = 0
                    active = session_state()["is_open"]
                    healthy_stream = self.stream_connected and time.monotonic() - self.last_stream_tick < config.QUOTE_STALE_SECONDS
                    interval = (60 if healthy_stream else config.QUOTE_POLL_SECONDS) if active else 300
                    if time.monotonic() - self.last_fetch >= interval:
                        self.refresh()
                    if active and config.STREAMING_ENABLED and not self.ticker and time.monotonic() - self.stream_attempt > 120:
                        self._start_stream()
                    if time.monotonic() - last_snapshot >= config.SNAPSHOT_INTERVAL_SECONDS:
                        self.store.snapshot(self.snapshot()["rows"])
                        last_snapshot = time.monotonic()
                    failures = 0
            except Exception as exc:
                with self.lock:
                    self.error = str(exc) if isinstance(exc, provider.ProviderError) else "Market update unavailable; reconnect Kite or check the server."
                    self.sequence += 1
                failures += 1
            self.stop_event.wait(min(120, max(1, config.QUOTE_POLL_SECONDS * 2 ** min(failures, 4))) if failures else 1)

    def refresh(self):
        with self.fetch_lock:
            if time.monotonic() - self.last_fetch < 3:
                return
            self.last_fetch = time.monotonic()
            if self.details is None:
                self.details = provider.stock_names(self.symbols)
                self.store.instrument_details(self.details)
                self.store.capability("instrument_master", "verified", "Approved NSE symbols validated.")
            symbols = [d["symbol"] for d in self.details if d["is_equity"]]
            payload = provider.live_quotes(symbols)
            self.ingest(payload.get("data", []), transport="polling")
            self.store.capability("quotes", "verified", "Kite REST quote request succeeded.")

    def ingest(self, quotes, transport="polling"):
        now = datetime.now(TZ)
        # A quote's exchange timestamp establishes its trading session, never fetch time.
        with self.lock:
            changed = False
            scan_candidates = []
            for quote in quotes:
                symbol = quote.get("symbol", "")
                qualified = symbol if ":" in symbol else f"{quote.get('exchange', 'NSE')}:{symbol}"
                if qualified not in self.allowed_symbols:
                    continue
                stamp = parse_time(quote.get("quote_timestamp"))
                if stamp is None or stamp > now.replace(microsecond=0) + timedelta(seconds=5):
                    stamp = None
                prior = self.rows.get(qualified, {})
                prior_stamp = parse_time(prior.get("quote_timestamp"))
                if stamp and prior_stamp and stamp < prior_stamp:
                    continue
                if stamp and self.anchor_date != stamp.date().isoformat():
                    if self.anchor_date and stamp.date().isoformat() < self.anchor_date:
                        continue
                    self.anchor_date = stamp.date().isoformat()
                    self.anchors = {r["symbol"]: {"open": r["opening_price"], "prev_close": r["previous_close"], "difference": r["difference"], "status": r["status"], "match": r["status"] == "MATCH", "near_match": r["status"] == "NEAR", "data_available": True} for r in self.store.opening_anchors(self.anchor_date)}
                    self.rows = {}
                row = {**prior, "symbol": qualified, "name": quote.get("name") or prior.get("name") or qualified,
                       "ltp": quote.get("ltp") if finite(quote.get("ltp")) and quote["ltp"] > 0 else None,
                       "volume": quote.get("volume") if finite(quote.get("volume")) else None, "quote_timestamp": stamp.isoformat() if stamp else None,
                       "quote_symbol": quote.get("quote_symbol") or prior.get("quote_symbol") or qualified,
                       "resolution_note": quote.get("resolution_note") or prior.get("resolution_note") or "",
                       "tick_size": quote.get("tick_size") or prior.get("tick_size"),
                       "last_trade_at": str(quote.get("last_trade_at") or ""), "received_at": now.isoformat()}
                if qualified not in self.anchors and stamp and stamp.time().replace(tzinfo=None) >= dt_time(9, 15):
                    scan_candidates.append({**quote, "symbol": qualified.split(":", 1)[1]})
                anchor = self.anchors.get(qualified)
                if anchor:
                    row.update(anchor)
                else:
                    row.update({"open": None, "prev_close": quote.get("prev_close") if finite(quote.get("prev_close")) and quote["prev_close"] > 0 else None, "difference": None, "status": "DATA N/A", "match": False, "near_match": False, "data_available": False})
                close = row.get("prev_close")
                row["change_pct"] = (row["ltp"] - close) / close * 100 if finite(close) and close > 0 and row["ltp"] is not None else None
                self.rows[qualified] = row
                changed = True
            # Compute opening rules only for newly established official opens.
            if scan_candidates:
                result = run_scan(self.symbols, universe="reference", quote_payload={"data": scan_candidates}, validated_details=self.details or [])
                self.scan_result = result
                for row in result["rows"]:
                    anchor = {k: row[k] for k in ("open", "prev_close", "difference", "difference_display", "status", "match", "near_match", "data_available")}
                    self.anchors[row["symbol"]] = anchor
                    self.rows[row["symbol"]].update(anchor)
                if self.anchor_date:
                    self.store.save_scan(self.anchor_date, result)
            if changed:
                self.updated_at = now.isoformat()
                self.error = None
                self.transport = "streaming" if self.stream_connected else transport
                self.sequence += 1

    def snapshot(self):
        with self.lock:
            now = datetime.now(TZ)
            market = session_state(now)
            rows = deepcopy(list(self.rows.values()))
            for row in rows:
                stamp = parse_time(row.get("quote_timestamp"))
                age = (now - stamp).total_seconds() if stamp else None
                row["quote_age_seconds"] = round(age) if age is not None else None
                row["quote_status"] = "unavailable" if row.get("ltp") is None else "unknown" if stamp is None or market.get("status") == "unknown" else "closed" if not market["is_open"] else "stale" if age > config.QUOTE_STALE_SECONDS or self.error else "live"
                row["opening_date"] = self.anchor_date
            verified = [r for r in rows if r["change_pct"] is not None and r["quote_status"] in {"live", "closed", "stale"}]
            performers = sorted(verified, key=lambda r: (-r["change_pct"], r["symbol"]))[:15]
            return {"sequence": self.sequence, "rows": rows, "top_performers": performers,
                    "as_of": self.updated_at, "scan_as_of": self.scan_result.get("as_of"), "opening_date": self.anchor_date,
                    "market": market, "transport": self.transport, "stream_connected": self.stream_connected,
                    "stream_error": self.stream_error, "error": self.error,
                    "quote_poll_seconds": config.QUOTE_POLL_SECONDS, "stale_seconds": config.QUOTE_STALE_SECONDS,
                    "token_configured": bool(config.KITE_ACCESS_TOKEN), "max_difference": config.MAX_DIFFERENCE,
                    "instrument_status": {d["symbol"]: "valid" if d["is_equity"] else "unavailable" for d in self.details or []},
                    "instrument_resolutions": {d["symbol"]: {k: d.get(k) for k in ("quote_symbol", "resolution_kind", "resolution_note", "resolution_source", "tick_size")} for d in self.details or []}}

    def scan(self):
        self.refresh()
        snap = self.snapshot()
        return {**self.scan_result, "rows": snap["rows"], "matches": [r for r in snap["rows"] if r.get("match")],
                "near_matches": [r for r in snap["rows"] if r.get("near_match")], "as_of": snap["as_of"],
                "universe": "reference", "checked_count": len(self.rows), "instrument_status": snap["instrument_status"],
                "reference_entry_count": 160}

    def _start_stream(self):
        self.stream_attempt = time.monotonic()
        try:
            from kiteconnect import KiteTicker
            mapping = {d["instrument_token"]: d for d in self.details or [] if d.get("is_equity") and d.get("instrument_token")}
            if not mapping:
                return
            ticker = KiteTicker(config.KITE_API_KEY, config.KITE_ACCESS_TOKEN, reconnect=True, reconnect_max_tries=20, reconnect_max_delay=60)

            def connected(ws, response):
                ws.subscribe(list(mapping))
                ws.set_mode(ws.MODE_FULL, list(mapping))
                self.stream_connected = True
                self.stream_error = None
                self.store.capability("streaming", "verified", "Kite WebSocket connected and subscribed.")

            def ticks(ws, values):
                self.last_stream_tick = time.monotonic()
                quotes = []
                for tick in values:
                    detail = mapping.get(tick.get("instrument_token"))
                    if not detail:
                        continue
                    ohlc = tick.get("ohlc", {})
                    quotes.append({"symbol": detail["symbol"].split(":", 1)[1], "exchange": "NSE", "name": detail["name"],
                                   "quote_symbol": detail.get("quote_symbol"), "resolution_note": detail.get("resolution_note"), "tick_size": detail.get("tick_size"),
                                   "ltp": tick.get("last_price"), "open": ohlc.get("open"), "prev_close": ohlc.get("close"),
                                   "volume": tick.get("volume_traded"), "quote_timestamp": tick.get("exchange_timestamp"),
                                   "last_trade_at": tick.get("last_trade_time")})
                self.ingest(quotes, "streaming")

            def failed(ws, code, reason):
                self.stream_connected = False
                self.transport = "polling"
                self.stream_error = "Streaming disconnected or unavailable; using batched REST quotes."
                self.store.capability("streaming", "unavailable", self.stream_error)

            ticker.on_connect = connected
            ticker.on_ticks = ticks
            ticker.on_error = failed
            ticker.on_close = failed
            ticker.on_reconnect = lambda ws, attempts: failed(ws, None, None)
            ticker.on_noreconnect = lambda ws: failed(ws, None, None)
            self.ticker = ticker
            ticker.connect(threaded=True)
        except Exception:
            self.ticker = None
            self.stream_error = "Streaming unavailable; using batched REST quotes."
            self.store.capability("streaming", "unavailable", self.stream_error)
