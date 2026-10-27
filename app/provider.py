import csv
import hashlib
import io
from datetime import date, timedelta

import requests

from . import config

BASE_URL = "https://api.kite.trade"
KITE_VERSION = "3"
_instrument_tokens: dict[str, dict[str, int]] = {}


class ProviderError(RuntimeError):
    pass


def _credentials_required() -> None:
    if not config.KITE_API_KEY or not config.KITE_API_SECRET:
        raise ProviderError("Kite API credentials are not configured. Add KITE_API_KEY and KITE_API_SECRET.")
    if not config.KITE_ACCESS_TOKEN:
        raise ProviderError("Kite session expired. Open /auth/kite/login and sign in again.")


def _headers() -> dict[str, str]:
    _credentials_required()
    return {
        "X-Kite-Version": KITE_VERSION,
        "Authorization": f"token {config.KITE_API_KEY}:{config.KITE_ACCESS_TOKEN}",
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
        raise ProviderError(f"Could not connect to Kite Connect: {exc}") from exc
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
    if not response.ok or payload.get("status") == "error":
        message = payload.get("message") or payload.get("error_type") or f"HTTP {response.status_code}"
        raise ProviderError(f"Kite API error: {message}")
    if not isinstance(payload, dict):
        raise ProviderError("Kite returned an unexpected response.")
    return payload


def live_quotes(symbols: list[str]) -> dict:
    if not symbols:
        return {"data": [], "meta": {"route": "kite:/quote"}}
    if len(symbols) > 500:
        raise ProviderError("Kite supports at most 500 instruments per quote request.")
    instruments = []
    for symbol in symbols:
        exchange, name = symbol.split(":", 1) if ":" in symbol else ("NSE", symbol)
        instruments.append((symbol, exchange, name))
    params = [("i", f"{exchange}:{name}") for _, exchange, name in instruments]
    try:
        response = requests.get(f"{BASE_URL}/quote", params=params, headers=_headers(), timeout=25)
    except requests.RequestException as exc:
        raise ProviderError(f"Could not connect to Kite Connect: {exc}") from exc
    payload = _json_payload(response)
    rows = []
    for requested, exchange, name in instruments:
        quote = payload.get("data", {}).get(f"{exchange}:{name}")
        if not quote:
            continue
        ohlc = quote.get("ohlc", {})
        previous_close = ohlc.get("close")
        last_price = quote.get("last_price")
        change_pct = None
        if isinstance(previous_close, (int, float)) and previous_close and isinstance(last_price, (int, float)):
            change_pct = (last_price - previous_close) / previous_close * 100
        rows.append({
            "found": True,
            "requested": requested,
            "symbol": name,
            "exchange": exchange,
            "name": "",
            "open": ohlc.get("open"),
            "prev_close": previous_close,
            "ltp": last_price,
            "change_pct": change_pct,
            "volume": quote.get("volume"),
            "last_trade_at": quote.get("last_trade_time") or quote.get("timestamp"),
        })
    return {"data": rows, "meta": {"route": "kite:/quote"}}


def _load_instrument_tokens(exchange: str = "NSE") -> dict[str, int]:
    if exchange in _instrument_tokens:
        return _instrument_tokens[exchange]
    try:
        response = requests.get(f"{BASE_URL}/instruments/{exchange}", headers=_headers(), timeout=30)
    except requests.RequestException as exc:
        raise ProviderError(f"Could not download Kite instruments: {exc}") from exc
    if not response.ok:
        raise ProviderError(f"Kite instruments request failed (HTTP {response.status_code}).")
    try:
        rows = csv.DictReader(io.StringIO(response.text))
        _instrument_tokens[exchange] = {
            row["tradingsymbol"]: int(row["instrument_token"])
            for row in rows
            if row.get("segment") == exchange and row.get("instrument_type") == "EQ"
        }
    except (KeyError, ValueError) as exc:
        raise ProviderError("Kite returned an invalid instruments file.") from exc
    return _instrument_tokens[exchange]


def equity_symbols(exchange: str, limit: int = 250) -> list[str]:
    """Return a bounded equity universe for an exchange-qualified watchlist."""
    if exchange not in {"NSE", "BSE"}:
        raise ProviderError(f"Unsupported exchange {exchange}.")
    # Kite's EQ segment also contains listed debt instruments with maturity-style
    # symbols (for example, ``...-N0``). Prefer conventional equity symbols so
    # the broad scanner is useful to clients looking for shares.
    symbols = sorted(_load_instrument_tokens(exchange))
    equity_like = [symbol for symbol in symbols if "-" not in symbol]
    symbols = equity_like or symbols
    return [f"{exchange}:{symbol}" for symbol in symbols[: max(1, min(250, limit))]]


def daily_history(symbol: str, limit: int = 8) -> dict:
    """Fetch recent daily OHLC bars for one NSE equity."""
    exchange, name = symbol.split(":", 1) if ":" in symbol else ("NSE", symbol)
    if exchange not in {"NSE", "BSE"}:
        raise ProviderError(f"Unsupported exchange {exchange}.")
    token = _load_instrument_tokens(exchange).get(name)
    if token is None:
        raise ProviderError(f"Kite could not find {exchange} equity symbol {name}.")
    today = date.today()
    try:
        response = requests.get(
            f"{BASE_URL}/instruments/historical/{token}/day",
            params={"from": (today - timedelta(days=22)).isoformat(), "to": today.isoformat()},
            headers=_headers(),
            timeout=25,
        )
    except requests.RequestException as exc:
        raise ProviderError(f"Could not connect to Kite Connect: {exc}") from exc
    payload = _json_payload(response)
    bars = [
        {"date": row[0], "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
        for row in payload.get("data", {}).get("candles", [])
    ]
    bars.sort(key=lambda row: row["date"], reverse=True)
    return {"symbol": f"{exchange}:{name}", "data": bars[: max(1, min(20, limit))], "meta": {"route": "kite:/instruments/historical"}}
