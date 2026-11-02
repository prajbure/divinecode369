import csv
import hashlib
import io
import json
import math
from functools import lru_cache
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import threading
import time

import requests

from . import config

BASE_URL = "https://api.kite.trade"
KITE_VERSION = "3"
_instrument_tokens: dict[str, dict[str, int]] = {}
_instrument_details: dict[str, dict[str, dict[str, str]]] = {}
_instrument_dates: dict[str, date] = {}
_request_lock = threading.Lock()
_last_request = 0.0


def _get(url, *, params=None, access_token=None):
    """One shared REST budget, including history/import requests."""
    global _last_request
    with _request_lock:
        time.sleep(max(0, 1.05 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        try:
            return requests.get(url, params=params, headers=_headers(access_token), timeout=(5,20), allow_redirects=False)
        except requests.RequestException as exc:
            # Do not interpolate request URLs/headers which can carry credentials.
            raise ProviderError("Kite connection failed. Check connectivity and reconnect your session.") from exc


class ProviderError(RuntimeError):
    def __init__(self,message,*,code='provider_error',status_code=None):
        super().__init__(message)
        self.code,self.status_code=code,status_code


@lru_cache(maxsize=1)
def alias_registry():
    return json.loads((config.ROOT / "data" / "instrument-aliases.json").read_text(encoding="utf-8"))


def resolve_instrument(requested: str) -> dict:
    exchange, name = requested.split(":", 1) if ":" in requested else ("NSE", requested)
    details = _load_instrument_details(exchange)
    row = details.get(name)
    alias = alias_registry()["aliases"].get(f"{exchange}:{name}")
    applied = None
    if not row and alias:
        candidate = details.get(alias["provider_symbol"])
        if candidate and any(part in candidate.get("name", "").upper() for part in alias["name_contains"]):
            row, applied = candidate, alias
    return {"symbol": f"{exchange}:{name}", "name": (row or {}).get("name") or name,
            "exchange": exchange, "is_equity": bool(row),
            "instrument_token": int(row["instrument_token"]) if row and row.get("instrument_token") else None,
            "provider_symbol": (row or {}).get("tradingsymbol") or name,
            "quote_symbol": f"{exchange}:{(row or {}).get('tradingsymbol') or name}",
            "tick_size": float(row["tick_size"]) if row and row.get("tick_size") else None,
            "resolution_kind": applied["kind"] if applied else "exact" if row else "unavailable",
            "resolution_note": applied["reason"] if applied else alias_registry()["unavailable"].get(f"{exchange}:{name}", {}).get("reason", "") if not row else "",
            "resolution_source": applied["source"] if applied else "kite:/instruments"}


def _credentials_required() -> None:
    if not config.KITE_API_KEY or not config.KITE_API_SECRET:
        raise ProviderError("Kite API credentials are not configured. Add KITE_API_KEY and KITE_API_SECRET.")
    if not config.KITE_ACCESS_TOKEN:
        raise ProviderError("Kite session expired. Open /auth/kite/login and sign in again.")


def _headers(access_token=None) -> dict[str, str]:
    if not config.KITE_API_KEY or not config.KITE_API_SECRET:
        raise ProviderError('Kite API credentials are missing.',code='key_missing')
    token=config.KITE_ACCESS_TOKEN if access_token is None else access_token
    if not token:
        raise ProviderError('Official Kite login is required.',code='authentication_failed')
    return {
        "X-Kite-Version": KITE_VERSION,
        "Authorization": f"token {config.KITE_API_KEY}:{token}",
    }


def create_kite_session(request_token: str) -> str:
    """Exchange Kite's short-lived request token for the daily access token."""
    if not config.KITE_API_KEY or not config.KITE_API_SECRET:
        raise ProviderError("KITE_API_KEY and KITE_API_SECRET are required for Kite login.")
    checksum = hashlib.sha256(
        f"{config.KITE_API_KEY}{request_token}{config.KITE_API_SECRET}".encode("utf-8")
    ).hexdigest()
    try:
        response = requests.post(
            f"{BASE_URL}/session/token",
            data={"api_key": config.KITE_API_KEY, "request_token": request_token, "checksum": checksum},
            headers={"X-Kite-Version": KITE_VERSION},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise ProviderError("Could not connect to Kite Connect.") from exc
    payload = _json_payload(response)
    token = payload.get("data", {}).get("access_token")
    if not token:
        raise ProviderError("Kite did not return an access token.")
    config.set_kite_access_token(token)
    return token


def _json_payload(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(f"Kite returned a non-JSON response (HTTP {response.status_code}).") from exc
    if not isinstance(payload, dict):
        raise ProviderError("Kite returned an unexpected response.")
    if not response.ok or payload.get("status") == "error":
        code='authentication_failed' if payload.get('error_type')=='TokenException' or response.status_code==401 else 'rate_limited' if response.status_code==429 else 'provider_error'
        message='Kite Login Required. The session expired or was revoked.' if code=='authentication_failed' else 'Kite request limit reached; recovery is deferred.' if code=='rate_limited' else f'Kite request unavailable (HTTP {response.status_code}). Check provider access and connectivity.'
        raise ProviderError(message,code=code,status_code=response.status_code)
    return payload


def validate_session(access_token):
    """Authenticated profile proves authorization without exposing profile details."""
    payload=_json_payload(_get(f'{BASE_URL}/user/profile',access_token=access_token))
    if not isinstance(payload.get('data'),dict) or not payload['data'].get('user_id'):
        raise ProviderError('Kite profile verification returned incomplete data.',code='provider_response')
    return True


def revoke_session(access_token):
    try:
        response=requests.delete(f'{BASE_URL}/session/token',headers=_headers(access_token),params={'api_key':config.KITE_API_KEY,'access_token':access_token},timeout=(5,15),allow_redirects=False)
    except requests.RequestException:
        raise ProviderError('Local Kite session cleared; provider logout could not be confirmed.') from None
    _json_payload(response)


def quote_intelligence(quote: dict, *, streaming=False) -> dict:
    """Normalize optional fields actually returned by Kite; no inferred VWAP."""
    def valid(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    ohlc = quote.get("ohlc") or {}
    average = quote.get("average_traded_price" if streaming else "average_price")
    depth = quote.get("depth") or {}
    bids = [r for r in depth.get("buy", []) if valid(r.get("price")) and r["price"] > 0 and valid(r.get("quantity")) and r["quantity"] >= 0]
    asks = [r for r in depth.get("sell", []) if valid(r.get("price")) and r["price"] > 0 and valid(r.get("quantity")) and r["quantity"] >= 0]
    return {"vwap": average if valid(average) and average > 0 else None,
            "vwap_source": "Kite average traded price" if valid(average) and average > 0 else None,
            "day_high": ohlc.get("high") if valid(ohlc.get("high")) and ohlc["high"] > 0 else None,
            "day_low": ohlc.get("low") if valid(ohlc.get("low")) and ohlc["low"] > 0 else None,
            "best_bid": max((r["price"] for r in bids), default=None),
            "best_ask": min((r["price"] for r in asks), default=None),
            "depth_bid_quantity": sum(r["quantity"] for r in bids) if bids else None,
            "depth_ask_quantity": sum(r["quantity"] for r in asks) if asks else None}


def live_quotes(symbols: list[str]) -> dict:
    if not symbols:
        return {"data": [], "meta": {"route": "kite:/quote"}}
    if len(symbols) > 500:
        raise ProviderError("Kite supports at most 500 instruments per quote request.")
    instruments = [resolve_instrument(symbol) for symbol in symbols]
    params = [("i", symbol) for symbol in dict.fromkeys(d["quote_symbol"] for d in instruments)]
    response = _get(f"{BASE_URL}/quote", params=params)
    payload = _json_payload(response)
    rows = []
    for instrument in instruments:
        requested, exchange = instrument["symbol"], instrument["exchange"]
        name = requested.split(":", 1)[1]
        quote = payload.get("data", {}).get(instrument["quote_symbol"])
        if not quote:
            continue
        ohlc = quote.get("ohlc", {})
        previous_close = ohlc.get("close")
        last_price = quote.get("last_price")
        change_pct = None
        if isinstance(previous_close, (int, float)) and previous_close and isinstance(last_price, (int, float)):
            change_pct = (last_price - previous_close) / previous_close * 100
        rows.append({
            **quote_intelligence(quote),
            "found": True,
            "requested": requested,
            "symbol": name,
            "exchange": exchange,
            "name": instrument["name"],
            "quote_symbol": instrument["quote_symbol"],
            "resolution_note": instrument["resolution_note"],
            "tick_size": instrument["tick_size"],
            "open": ohlc.get("open"),
            "prev_close": previous_close,
            "ltp": last_price,
            "change_pct": change_pct,
            "volume": quote.get("volume"),
            "last_trade_at": quote.get("last_trade_time") or quote.get("timestamp"),
            "quote_timestamp": quote.get("timestamp"),
            "instrument_token": quote.get("instrument_token"),
        })
    return {"data": rows, "meta": {"route": "kite:/quote"}}


def _load_instrument_details(exchange: str = "NSE") -> dict[str, dict[str, str]]:
    today = datetime.now(ZoneInfo(config.APP_TIMEZONE)).date()
    if exchange in _instrument_details and _instrument_dates.get(exchange) == today:
        return _instrument_details[exchange]
    try:
        response = _get(f"{BASE_URL}/instruments/{exchange}")
    except requests.RequestException as exc:
        raise ProviderError("Could not download Kite instruments.") from exc
    if not response.ok:
        raise ProviderError(f"Kite instruments request failed (HTTP {response.status_code}).")
    try:
        rows = csv.DictReader(io.StringIO(response.text))
        _instrument_details[exchange] = {
            row["tradingsymbol"]: row
            for row in rows
            if row.get("segment") == exchange and row.get("instrument_type") == "EQ"
        }
        _instrument_dates[exchange] = today
        _instrument_tokens.pop(exchange, None)
    except (KeyError, ValueError) as exc:
        raise ProviderError("Kite returned an invalid instruments file.") from exc
    return _instrument_details[exchange]


def _load_instrument_tokens(exchange: str = "NSE") -> dict[str, int]:
    if exchange not in _instrument_tokens:
        try:
            _instrument_tokens[exchange] = {
                symbol: int(row["instrument_token"])
                for symbol, row in _load_instrument_details(exchange).items()
            }
        except (KeyError, ValueError) as exc:
            raise ProviderError("Kite returned an invalid instruments file.") from exc
    return _instrument_tokens[exchange]


def _optionable_underlyings(exchange: str) -> set[str]:
    """Return equity underlyings that have a listed futures/options contract."""
    derivative_exchange = {"NSE": "NFO", "BSE": "BFO"}[exchange]
    try:
        response = _get(f"{BASE_URL}/instruments/{derivative_exchange}")
    except requests.RequestException as exc:
        raise ProviderError("Could not download Kite instruments.") from exc
    if not response.ok:
        raise ProviderError(
            f"Kite {derivative_exchange} instruments request failed (HTTP {response.status_code})."
        )
    try:
        rows = csv.DictReader(io.StringIO(response.text))
        return {
            row.get("name", "").strip().upper()
            for row in rows
            if row.get("segment", "").startswith(derivative_exchange)
            and row.get("instrument_type") in {"FUT", "CE", "PE"}
            and row.get("name")
        }
    except (KeyError, ValueError) as exc:
        raise ProviderError("Kite returned an invalid derivatives instruments file.") from exc


def equity_symbols(exchange: str, limit: int = 75) -> list[str]:
    """Return optionable equities only for an exchange-qualified watchlist."""
    if exchange not in {"NSE", "BSE"}:
        raise ProviderError(f"Unsupported exchange {exchange}.")
    equities = _load_instrument_details(exchange)
    optionable = _optionable_underlyings(exchange)
    symbols = sorted(
        symbol for symbol in equities
        if symbol.upper() in optionable and "-" not in symbol
    )
    return [f"{exchange}:{symbol}" for symbol in symbols[: max(1, min(250, limit))]]


def stock_names(symbols: list[str]) -> list[dict]:
    """Resolve exchange-qualified symbols to Kite's company names."""
    return [resolve_instrument(symbol) for symbol in symbols]


def daily_history(symbol: str, limit: int = 8) -> dict:
    """Fetch recent daily OHLC bars for one NSE equity."""
    exchange, name = symbol.split(":", 1) if ":" in symbol else ("NSE", symbol)
    if exchange not in {"NSE", "BSE"}:
        raise ProviderError(f"Unsupported exchange {exchange}.")
    token = resolve_instrument(f"{exchange}:{name}")["instrument_token"]
    if token is None:
        raise ProviderError(f"Kite could not find {exchange} equity symbol {name}.")
    today = datetime.now(ZoneInfo(config.APP_TIMEZONE)).date()
    response = _get(f"{BASE_URL}/instruments/historical/{token}/day",
                    params={"from": (today - timedelta(days=22)).isoformat(), "to": today.isoformat()})
    payload = _json_payload(response)
    bars = [
        {"date": row[0], "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
        for row in payload.get("data", {}).get("candles", [])
    ]
    bars.sort(key=lambda row: row["date"], reverse=True)
    return {"symbol": f"{exchange}:{name}", "data": bars[: max(1, min(20, limit))], "meta": {"route": "kite:/instruments/historical"}}


def historical_candles(symbol: str, start: date, end: date, interval="day") -> list[dict]:
    if not config.HISTORICAL_ENABLED:
        raise ProviderError("Historical capability has not been enabled for this account.")
    if interval != "day" and not config.INTRADAY_ENABLED:
        raise ProviderError("Intraday history is not enabled for this account.")
    exchange, name = symbol.split(":", 1)
    token = resolve_instrument(symbol)["instrument_token"]
    if token is None:
        raise ProviderError("Instrument is unavailable in Kite's instrument master.")
    response = _get(f"{BASE_URL}/instruments/historical/{token}/{interval}",
                    params={"from": start.isoformat(), "to": end.isoformat()})
    payload = _json_payload(response)
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in payload.get("data", {}).get("candles", []) if len(r) >= 6]
