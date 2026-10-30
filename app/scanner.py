from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from zoneinfo import ZoneInfo
from . import config
from .provider import live_quotes, stock_names

REFERENCE_UNIVERSE_PATH = config.ROOT / "static" / "sector-universe.json"


def load_watchlist() -> list[str]:
    if not config.WATCHLIST_PATH.exists():
        return []
    symbols = []
    for line in config.WATCHLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip().upper()
        if line and not line.startswith("#") and line not in symbols:
            symbols.append(line)
    return symbols[:500]


def save_watchlist(raw: str) -> list[str]:
    symbols = []
    for line in raw.replace(",", "\n").splitlines():
        symbol = line.strip().upper()
        if symbol and not symbol.startswith("#") and symbol not in symbols:
            if ":" in symbol:
                exchange, symbol_name = symbol.split(":", 1)
                valid_exchange = exchange in {"NSE", "BSE"}
            else:
                exchange, symbol_name, valid_exchange = "NSE", symbol, True
            if not valid_exchange or not symbol_name or not all(ch.isalnum() or ch in "&-._" for ch in symbol_name):
                continue
            symbols.append(f"{exchange}:{symbol_name}")
    if len(symbols) > 500:
        raise ValueError("Please enter 500 symbols or fewer. Kite accepts up to 500 instruments per quote request.")
    config.WATCHLIST_PATH.write_text("# Use NSE:SYMBOL or BSE:SYMBOL; maximum 500 instruments\n" + "\n".join(symbols) + "\n", encoding="utf-8")
    return symbols


def reference_groups() -> list[dict]:
    """Load the exact dashboard entries supplied by the user."""
    with REFERENCE_UNIVERSE_PATH.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    return payload["groups"]


def reference_scan_symbols() -> list[str]:
    """Return unique NSE symbols, excluding securities known to be suspended."""
    symbols = []
    for group in reference_groups():
        for stock in group["stocks"]:
            symbol = stock[0]
            known_status = stock[3] if len(stock) > 3 else None
            qualified = f"NSE:{symbol}"
            if known_status != "suspended" and qualified not in symbols:
                symbols.append(qualified)
    return symbols


def reference_entry_count() -> int:
    return sum(len(group["stocks"]) for group in reference_groups())


def run_scan(symbols: list[str] | None = None, *, universe: str = "watchlist") -> dict:
    requested_symbols = list(dict.fromkeys(symbols if symbols is not None else load_watchlist()))
    symbol_status: dict[str, str] = {}
    unavailable_symbols: list[str] = []
    if universe == "reference":
        instrument_details = stock_names(requested_symbols)
        symbol_status = {
            item["symbol"]: "valid" if item["is_equity"] else "unavailable"
            for item in instrument_details
        }
        unavailable_symbols = [
            symbol for symbol in requested_symbols if symbol_status.get(symbol) != "valid"
        ]
        symbols = [symbol for symbol in requested_symbols if symbol_status.get(symbol) == "valid"]
    else:
        symbols = requested_symbols
    if not symbols:
        return {
            "as_of": datetime.now(ZoneInfo(config.APP_TIMEZONE)).isoformat(),
            "rows": [],
            "matches": [],
            "checked_count": 0,
            "message": "No valid NSE reference instruments are available to scan." if universe == "reference" else "Your watchlist is empty. Add stock symbols first.",
            "universe": universe,
            "requested_count": len(requested_symbols),
            "unavailable_symbols": unavailable_symbols,
            "instrument_status": symbol_status,
            "reference_entry_count": reference_entry_count() if universe == "reference" else None,
        }
    payload = live_quotes(symbols)
    rows = []
    matches = []
    for q in payload.get("data", []):
        open_price = q.get("open")
        prev_close = q.get("prev_close")
        valid = q.get("found", True) and isinstance(open_price, (int, float)) and not isinstance(open_price, bool) and isinstance(prev_close, (int, float)) and not isinstance(prev_close, bool)
        try:
            open_decimal = Decimal(str(open_price)) if valid else None
            close_decimal = Decimal(str(prev_close)) if valid else None
            difference_decimal = open_decimal - close_decimal if open_decimal is not None and close_decimal is not None else None
            valid = valid and open_decimal.is_finite() and close_decimal.is_finite()
        except (InvalidOperation, TypeError, ValueError):
            valid = False
            difference_decimal = None
        if not valid or difference_decimal is None:
            continue
        difference = float(difference_decimal)
        matched = difference_decimal.is_zero()
        near_match = not matched and abs(difference_decimal) <= Decimal(str(config.MAX_DIFFERENCE))
        row = {
            "symbol": f"{q.get('exchange', 'NSE')}:{q.get('symbol') or q.get('requested')}",
            "name": q.get("name") or "",
            "prev_close": prev_close,
            "open": open_price,
            "difference": difference,
            "ltp": q.get("ltp"),
            "change_pct": q.get("change_pct"),
            "volume": q.get("volume"),
            "market_status": q.get("market_status"),
            "last_trade_at": q.get("last_trade_at"),
            "match": matched,
            "near_match": near_match,
            "status": "MATCH" if matched else "NEAR" if near_match else "NO MATCH",
            "data_available": valid,
        }
        rows.append(row)
        if matched:
            matches.append(row)
    scan_timestamp = payload.get("meta", {}).get("as_of")
    return {
        # Kite's /quote response does not include meta.as_of. Stamp the
        # successful fetch time so the UI can distinguish a completed scan
        # from the empty startup state without presenting sample data.
        "as_of": scan_timestamp or datetime.now(ZoneInfo(config.APP_TIMEZONE)).isoformat(),
        "as_of_source": "provider" if scan_timestamp else "scan_fetch",
        "route": payload.get("meta", {}).get("route"),
        "rows": rows,
        "matches": matches,
        "near_matches": [row for row in rows if row["near_match"]],
        "checked_count": len(symbols),
        "requested_count": len(requested_symbols),
        "unavailable_symbols": unavailable_symbols,
        "instrument_status": symbol_status,
        "universe": universe,
        "reference_entry_count": reference_entry_count() if universe == "reference" else None,
        "tolerance": 0,
        "max_difference": config.MAX_DIFFERENCE,
        "message": f"Showing stocks within ₹{config.MAX_DIFFERENCE:g}; only an exact ₹0 difference is marked as MATCH.",
    }
