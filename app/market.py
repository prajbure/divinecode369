"""One provider subscription/cache per process; fan out snapshots via SSE."""
from copy import deepcopy
from datetime import datetime, timedelta, time as dt_time
import math
import random
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
        self.last_tick_at = None
        self.subscription_count = 0
        self.last_stream_tick = 0.0
        self.token = None
        self.stream_attempt = 0.0
        self.sequence = 0
        self.authorization = None
        self.on_provider_error = None
        self.session_generation = 0
        self.stream_retry_at = 0.0
        self.stream_failures = 0
        self.closed_fetch_phase = None
        self.symbols = reference_scan_symbols()
        self.allowed_symbols = set(self.symbols)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="divine-market", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.close_stream()
        with self.lock:self.session_generation+=1
        if self.thread:
            self.thread.join(timeout=3)

    def close_stream(self):
        with self.lock:
            ticker=self.ticker
            self.ticker=None;self.stream_connected=False;self.subscription_count=0
        if ticker:
            try:ticker.close()
            except Exception:pass

    def reset_session(self):
        self.close_stream()
        with self.lock:
            self.session_generation+=1;self.token=None;self.details=None;self.last_fetch=0
            self.stream_attempt=0;self.stream_retry_at=0;self.stream_failures=0
            self.closed_fetch_phase=None
            self.transport='unavailable';self.sequence+=1
            self.error=None if self.authorization is None or self.authorization() else 'Kite Login Required. Cached prices are not a connected feed.'

    def _run(self):
        failures = 0
        last_snapshot = 0.0
        while not self.stop_event.is_set():
            try:
                authorized=self.authorization is None or self.authorization()
                if not authorized or not config.KITE_ACCESS_TOKEN:
                    if self.ticker:self.close_stream()
                if config.KITE_ACCESS_TOKEN and authorized:
                    # A new daily session invalidates the previous socket and token map.
                    if self.token != config.KITE_ACCESS_TOKEN:
                        self.close_stream()
                        self.token = config.KITE_ACCESS_TOKEN
                        self.details = None
                        self.last_fetch = 0
                        self.closed_fetch_phase=None
                    session=session_state()
                    active = session["is_open"]
                    healthy_stream = self.stream_connected and time.monotonic() - self.last_stream_tick < config.QUOTE_STALE_SECONDS
                    interval = 60 if healthy_stream else config.QUOTE_POLL_SECONDS
                    phase=(session.get('trading_date'),session.get('status'))
                    due=time.monotonic()-self.last_fetch>=interval if active else phase!=self.closed_fetch_phase
                    if due:
                        self.refresh()
                        if not active:self.closed_fetch_phase=phase
                    if active:self.closed_fetch_phase=None
                    if active and config.STREAMING_ENABLED and not self.ticker and time.monotonic()>=self.stream_retry_at and time.monotonic() - self.stream_attempt > 3:
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
            delay=min(900,max(1,config.QUOTE_POLL_SECONDS*2**min(failures,6))) if failures else 1
            self.stop_event.wait(delay+random.uniform(0,min(5,delay*.1)) if failures else 1)

    def refresh(self):
        generation=self.session_generation
        if self.authorization is not None and not self.authorization():
            raise provider.ProviderError('Kite Login Required. Restore a validated official session first.',code='authentication_failed')
        try:return self._refresh()
        except provider.ProviderError as error:
            if self.on_provider_error and generation==self.session_generation:self.on_provider_error(error)
            raise

    def _refresh(self):
        with self.fetch_lock:
            generation=self.session_generation
            if time.monotonic() - self.last_fetch < 3:
                return
            self.last_fetch = time.monotonic()
            if self.details is None:
                details = provider.stock_names(self.symbols)
                if generation!=self.session_generation:return
                self.details=details
                self.store.instrument_details(self.details)
                self.store.capability("instrument_master", "verified", "Approved NSE symbols validated.")
            symbols = [d["symbol"] for d in self.details if d["is_equity"]]
            payload = provider.live_quotes(symbols)
            with self.lock:
                if generation!=self.session_generation or (self.authorization is not None and not self.authorization()):return
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
                       "volume": quote.get("volume") if finite(quote.get("volume")) and quote["volume"] >= 0 else None, "quote_timestamp": stamp.isoformat() if stamp else None,
                       "quote_symbol": quote.get("quote_symbol") or prior.get("quote_symbol") or qualified,
                       "resolution_note": quote.get("resolution_note") or prior.get("resolution_note") or "",
                       "tick_size": quote.get("tick_size") or prior.get("tick_size"),
                       "last_trade_at": str(quote.get("last_trade_at") or ""), "received_at": now.isoformat()}
                for field in ("vwap", "day_high", "day_low", "best_bid", "best_ask", "depth_bid_quantity", "depth_ask_quantity"):
                    value = quote.get(field)
                    row[field] = value if finite(value) and value >= 0 else None
                row["vwap_source"] = quote.get("vwap_source") if row["vwap"] else None
                calendar = session_state(stamp) if stamp else None
                opening_time = dt_time.fromisoformat(calendar['opening_time']) if calendar else dt_time(9, 15)
                eligible_session = calendar and (not calendar['calendar_verified'] or calendar['is_trading_day'])
                if qualified not in self.anchors and stamp and eligible_session and stamp.time().replace(tzinfo=None) >= opening_time:
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
            authorized=self.authorization is None or self.authorization()
            rows = deepcopy(list(self.rows.values()))
            for row in rows:
                stamp = parse_time(row.get("quote_timestamp"))
                age = (now - stamp).total_seconds() if stamp else None
                row["quote_age_seconds"] = round(age) if age is not None else None
                row["quote_status"] = "unavailable" if row.get("ltp") is None else "unknown" if stamp is None or market.get("status") == "unknown" else "closed" if not market["is_open"] else "stale" if age > config.QUOTE_STALE_SECONDS or self.error or not authorized else "live"
                row["opening_date"] = self.anchor_date
            verified = [r for r in rows if r["change_pct"] is not None and r["quote_status"] in {"live", "closed", "stale"}]
            performers = sorted(verified, key=lambda r: (-r["change_pct"], r["symbol"]))[:15]
            return {"sequence": self.sequence, "rows": rows, "top_performers": performers,
                    "as_of": self.updated_at, "scan_as_of": self.scan_result.get("as_of"), "opening_date": self.anchor_date,
                    "market": market, "transport": self.transport, "stream_connected": self.stream_connected,
                    "stream_error": self.stream_error, "error": self.error,
                    "stream_retry_after":max(0,round(self.stream_retry_at-time.monotonic())),"stream_failures":self.stream_failures,
                    "last_received_tick": self.last_tick_at, "active_subscriptions": self.subscription_count if self.stream_connected else 0,
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
        if self.ticker is not None or (self.authorization is not None and not self.authorization()):return
        self.stream_attempt = time.monotonic()
        try:
            from kiteconnect import KiteTicker
            mapping = {d["instrument_token"]: d for d in self.details or [] if d.get("is_equity") and d.get("instrument_token")}
            if not mapping:
                return
            token=config.KITE_ACCESS_TOKEN
            ticker = KiteTicker(config.KITE_API_KEY, token, reconnect=True, reconnect_max_tries=8, reconnect_max_delay=60)

            def connected(ws, response):
                if self.ticker is not ticker:
                    return
                if token!=config.KITE_ACCESS_TOKEN or (self.authorization is not None and not self.authorization()):
                    self.close_stream();return
                if self.stream_connected:return
                ws.subscribe(list(mapping))
                ws.set_mode(ws.MODE_FULL, list(mapping))
                self.stream_connected = True
                self.subscription_count = len(mapping)
                self.stream_error = None
                self.stream_failures=0;self.stream_retry_at=0
                self.store.capability("streaming", "verified", "Kite WebSocket connected and subscribed.")

            def ticks(ws, values):
                if self.ticker is not ticker or not values:
                    return
                self.last_stream_tick = time.monotonic()
                self.last_tick_at = datetime.now(TZ).isoformat()
                quotes = []
                for tick in values:
                    detail = mapping.get(tick.get("instrument_token"))
                    if not detail:
                        continue
                    ohlc = tick.get("ohlc", {})
                    quotes.append({"symbol": detail["symbol"].split(":", 1)[1], "exchange": "NSE", "name": detail["name"],
                                   **provider.quote_intelligence(tick, streaming=True),
                                   "quote_symbol": detail.get("quote_symbol"), "resolution_note": detail.get("resolution_note"), "tick_size": detail.get("tick_size"),
                                   "ltp": tick.get("last_price"), "open": ohlc.get("open"), "prev_close": ohlc.get("close"),
                                   "volume": tick.get("volume_traded"), "quote_timestamp": tick.get("exchange_timestamp"),
                                   "last_trade_at": tick.get("last_trade_time")})
                with self.lock:
                    if self.ticker is ticker and token==config.KITE_ACCESS_TOKEN and (self.authorization is None or self.authorization()):self.ingest(quotes, "streaming")

            def failed(ws, code, reason):
                if self.ticker is not ticker:
                    return
                self.stream_connected = False
                self.subscription_count = 0
                self.transport = "polling"
                self.stream_error = "Streaming disconnected or unavailable; using batched REST quotes."
                self.store.capability("streaming", "unavailable", self.stream_error)

            ticker.on_connect = connected
            ticker.on_ticks = ticks
            ticker.on_error = failed
            ticker.on_close = failed
            ticker.on_reconnect = lambda ws, attempts: failed(ws, None, None)
            def exhausted(ws):
                if self.ticker is not ticker:
                    return
                failed(ws, None, None)
                self.ticker = None
                self.subscription_count = 0
                self.stream_attempt = time.monotonic()
                self.stream_failures+=1
                self.stream_retry_at=time.monotonic()+min(900,30*2**min(self.stream_failures-1,5))+random.uniform(0,10)
            ticker.on_noreconnect = exhausted
            self.ticker = ticker
            ticker.connect(threaded=True)
        except Exception:
            self.ticker = None
            self.stream_error = "Streaming unavailable; using batched REST quotes."
            self.store.capability("streaming", "unavailable", self.stream_error)
