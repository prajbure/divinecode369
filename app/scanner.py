from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from . import config
from .provider import live_quotes


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


def run_scan() -> dict:
    symbols = load_watchlist()
    if not symbols:
        return {"as_of": datetime.now(ZoneInfo(config.APP_TIMEZONE)).isoformat(), "rows": [], "matches": [], "checked_count": 0, "message": "Your watchlist is empty. Add stock symbols first."}
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
        if abs(difference_decimal) > Decimal(str(config.MAX_DIFFERENCE)):
            continue
        difference = float(difference_decimal)
        matched = difference_decimal.is_zero()
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
            "data_available": valid,
        }
        rows.append(row)
        if matched:
            matches.append(row)
    return {
        "as_of": payload.get("meta", {}).get("as_of"),
        "route": payload.get("meta", {}).get("route"),
        "rows": rows,
        "matches": matches,
        "checked_count": len(symbols),
        "tolerance": 0,
        "max_difference": config.MAX_DIFFERENCE,
        "message": f"Showing stocks within ₹{config.MAX_DIFFERENCE:g}; only an exact ₹0 difference is marked as MATCH.",
    }
