"""Private, deduplicated market research storage. No raw tick persistence."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import sqlite3
from zoneinfo import ZoneInfo

from . import config
from .calendar import completed_daily_date


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or config.DATABASE_PATH

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self, groups):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS instruments (
              symbol TEXT PRIMARY KEY, name TEXT NOT NULL, exchange TEXT NOT NULL,
              instrument_token INTEGER, status TEXT NOT NULL DEFAULT 'unverified');
            CREATE TABLE IF NOT EXISTS sector_memberships (
              sector_id TEXT NOT NULL, entry_index INTEGER NOT NULL, sector_name TEXT NOT NULL,
              symbol TEXT NOT NULL REFERENCES instruments(symbol), display_name TEXT NOT NULL,
              note TEXT, PRIMARY KEY(sector_id, entry_index));
            CREATE TABLE IF NOT EXISTS candles (
              symbol TEXT NOT NULL REFERENCES instruments(symbol), interval TEXT NOT NULL,
              timestamp TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
              close REAL NOT NULL, volume REAL NOT NULL, source TEXT NOT NULL,
              data_timestamp TEXT NOT NULL, PRIMARY KEY(symbol, interval, timestamp));
            CREATE INDEX IF NOT EXISTS candles_time ON candles(interval, timestamp);
            CREATE TABLE IF NOT EXISTS quote_snapshots (
              symbol TEXT NOT NULL, timestamp TEXT NOT NULL, price REAL NOT NULL,
              change_pct REAL, source TEXT NOT NULL, data_timestamp TEXT,
              PRIMARY KEY(symbol, timestamp));
            CREATE TABLE IF NOT EXISTS scan_results (
              trading_date TEXT NOT NULL, symbol TEXT NOT NULL, previous_close REAL NOT NULL,
              opening_price REAL NOT NULL, difference REAL NOT NULL, status TEXT NOT NULL,
              scanned_at TEXT NOT NULL, PRIMARY KEY(trading_date, symbol));
            CREATE TABLE IF NOT EXISTS model_versions (
              version TEXT PRIMARY KEY, trained_at TEXT NOT NULL, name TEXT NOT NULL,
              artifact_path TEXT NOT NULL, data_through TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_metrics (
              version TEXT NOT NULL REFERENCES model_versions(version), split TEXT NOT NULL,
              payload TEXT NOT NULL, PRIMARY KEY(version, split));
            CREATE TABLE IF NOT EXISTS predictions (
              version TEXT NOT NULL REFERENCES model_versions(version), symbol TEXT NOT NULL,
              as_of TEXT NOT NULL, horizon TEXT NOT NULL, probability_up REAL NOT NULL,
              probability_down REAL NOT NULL, price REAL NOT NULL, created_at TEXT NOT NULL,
              actual_return REAL, PRIMARY KEY(version, symbol, as_of, horizon));
            CREATE INDEX IF NOT EXISTS predictions_time ON predictions(as_of);
            CREATE TABLE IF NOT EXISTS capabilities (
              name TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS training_evaluations(at TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS instrument_resolutions(
              symbol TEXT PRIMARY KEY REFERENCES instruments(symbol), provider_symbol TEXT,
              kind TEXT NOT NULL, note TEXT, source TEXT, tick_size REAL, checked_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history_imports(
              id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              request_json TEXT NOT NULL, symbols_json TEXT NOT NULL DEFAULT '[]', skipped_json TEXT NOT NULL DEFAULT '[]',
              symbol_index INTEGER NOT NULL DEFAULT 0, cursor_date TEXT, candles_processed INTEGER NOT NULL DEFAULT 0,
              requests_completed INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
              last_success_at TEXT, error TEXT, incremental INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS imports_state ON history_imports(state,created_at);
            """)
            for group in groups:
                for index, stock in enumerate(group["stocks"]):
                    symbol = "NSE:" + stock[0]
                    status = stock[3] if len(stock) > 3 else "unverified"
                    db.execute("INSERT OR IGNORE INTO instruments(symbol,name,exchange,status) VALUES(?,?,?,?)",
                               (symbol, stock[1], "NSE", status))
                    db.execute("INSERT OR REPLACE INTO sector_memberships VALUES(?,?,?,?,?,?)",
                               (group["id"], index, group["name"], symbol, stock[1], stock[2] if len(stock) > 2 else ""))

    def capability(self, name, status, detail=""):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO capabilities VALUES(?,?,?,?)", (name, status, now_iso(), detail))

    def instrument_details(self, details):
        with self.connection() as db:
            for item in details:
                db.execute("UPDATE instruments SET status=?, instrument_token=COALESCE(?,instrument_token) WHERE symbol=?",
                           ("valid" if item.get("is_equity") else "unavailable", item.get("instrument_token"), item["symbol"]))
                db.execute("INSERT OR REPLACE INTO instrument_resolutions VALUES(?,?,?,?,?,?,?)",
                           (item["symbol"], item.get("quote_symbol", item["symbol"]), item.get("resolution_kind", "exact" if item.get("is_equity") else "unavailable"), item.get("resolution_note", ""), item.get("resolution_source", "kite:/instruments"), item.get("tick_size"), now_iso()))

    def save_candles(self, symbol, bars, interval="day", *, authorized=None):
        if not (config.DATA_RETENTION_AUTHORIZED if authorized is None else authorized):
            raise ValueError("Market-data retention is not authorized in server settings.")
        count = 0
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM instruments WHERE symbol=?", (symbol,)).fetchone():
                raise ValueError("Instrument is outside the approved universe.")
            for bar in bars:
                values = [bar.get(key) for key in ("open", "high", "low", "close", "volume")]
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                    raise ValueError("Candle contains missing or non-finite OHLCV values.")
                opening, high, low, close, volume = values
                if min(opening, high, low, close) <= 0 or volume < 0 or high < max(opening, close) or low > min(opening, close) or high < low:
                    raise ValueError("Candle has inconsistent OHLCV values.")
                raw = str(bar.get("date") or bar.get("timestamp") or "")
                stamp = datetime.fromisoformat(raw)
                if stamp.date() > completed_daily_date() and interval == "day":
                    continue  # Never train on today's unfinished candle.
                key = stamp.date().isoformat() if interval == "day" else stamp.isoformat()
                db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol,interval,timestamp) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume,source=excluded.source,data_timestamp=excluded.data_timestamp",
                           (symbol, interval, key, *values, "kite", now_iso()))
                count += 1
        return count

    def import_jobs(self, limit=30):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM history_imports ORDER BY created_at DESC LIMIT ?", (limit,))]
        for row in rows:
            row["request"] = json.loads(row.pop("request_json"))
            row["symbols"] = json.loads(row.pop("symbols_json"))
            row["skipped"] = json.loads(row.pop("skipped_json"))
        return rows

    def import_summary(self):
        with self.connection() as db:
            last = db.execute("SELECT MAX(last_success_at) FROM history_imports").fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM history_imports WHERE state IN ('queued','running','retrying')").fetchone()[0]
        return {"last_successful_import": last, "active_jobs": count, "jobs": self.import_jobs()}

    def candles(self, symbol=None, interval="day", limit=2000):
        with self.connection() as db:
            if symbol:
                rows = db.execute("SELECT * FROM candles WHERE symbol=? AND interval=? ORDER BY timestamp DESC LIMIT ?", (symbol, interval, limit)).fetchall()
                return list(reversed([dict(r) for r in rows]))
            return [dict(r) for r in db.execute("SELECT * FROM candles WHERE interval=? ORDER BY symbol,timestamp", (interval,))]

    def save_scan(self, trading_date, result):
        if not config.DATA_RETENTION_AUTHORIZED:
            return
        with self.connection() as db:
            for row in result.get("rows", []):
                # Preserve the first official open and reference close for a session.
                db.execute("INSERT OR IGNORE INTO scan_results VALUES(?,?,?,?,?,?,?)",
                           (trading_date, row["symbol"], row["prev_close"], row["open"], row["difference"], row["status"], result["as_of"]))

    def opening_anchors(self, trading_date):
        if not config.DATA_RETENTION_AUTHORIZED:
            return []
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM scan_results WHERE trading_date=?", (trading_date,))]

    def snapshot(self, rows):
        if not config.DATA_RETENTION_AUTHORIZED:
            return
        interval = config.SNAPSHOT_INTERVAL_SECONDS
        epoch = int(datetime.now(timezone.utc).timestamp())
        bucket = datetime.fromtimestamp(epoch - epoch % interval, timezone.utc).isoformat()
        with self.connection() as db:
            for row in rows:
                if row.get("ltp") is not None and row.get("quote_status") == "live":
                    db.execute("INSERT OR IGNORE INTO quote_snapshots VALUES(?,?,?,?,?,?)",
                               (row["symbol"], bucket, row["ltp"], row.get("change_pct"), "kite", row.get("quote_timestamp")))

    def cleanup(self):
        with self.connection() as db:
            for table, column, days in [("quote_snapshots", "timestamp", config.SNAPSHOT_RETENTION_DAYS),
                                        ("candles", "timestamp", config.DAILY_RETENTION_DAYS),
                                        ("scan_results", "trading_date", config.DAILY_RETENTION_DAYS)]:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
                db.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
            cutoff = (datetime.now(timezone.utc) - timedelta(days=config.INTRADAY_RETENTION_DAYS)).date().isoformat()
            db.execute("DELETE FROM candles WHERE interval != 'day' AND timestamp < ?", (cutoff,))

    def overview(self):
        with self.connection() as db:
            coverage = dict(db.execute("SELECT COUNT(*) candles, COUNT(DISTINCT symbol) instruments, MIN(timestamp) first_date, MAX(timestamp) last_date FROM candles WHERE interval='day'").fetchone())
            coverage["capabilities"] = [dict(r) for r in db.execute("SELECT * FROM capabilities")]
            coverage["snapshots"] = db.execute("SELECT COUNT(*) FROM quote_snapshots").fetchone()[0]
            coverage["scan_results"] = db.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
            return coverage

    def last_evaluation(self):
        with self.connection() as db:
            row = db.execute("SELECT * FROM training_evaluations ORDER BY at DESC LIMIT 1").fetchone()
            return {"at": row["at"], **json.loads(row["payload"])} if row else None

    def model(self):
        with self.connection() as db:
            row = db.execute("SELECT * FROM model_versions ORDER BY trained_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            model = dict(row)
            model["payload"] = json.loads(model["payload"])
            model.pop("artifact_path", None)
            model["metrics"] = {r["split"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM model_metrics WHERE version=?", (row["version"],))}
            return model

    def predictions(self, limit=500):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT p.*, i.name, m.name model_name FROM predictions p JOIN instruments i USING(symbol) JOIN model_versions m USING(version) ORDER BY p.created_at DESC, p.symbol LIMIT ?", (limit,))]
