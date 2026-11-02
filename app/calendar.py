"""Versioned official cash-market calendars; unknown years fail closed."""
from datetime import datetime, time, timedelta
from functools import lru_cache
import json
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo("Asia/Kolkata")


@lru_cache(maxsize=8)
def calendar_for_year(year):
    path = config.ROOT / "data" / f"nse-calendar-{year}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("exchange") != "NSE" or data.get("segment") != "Capital Market":
        raise ValueError("Calendar must identify the NSE capital-market segment.")
    return data


def session_state(now=None):
    now = now or datetime.now(TZ)
    now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    day, clock = now.date().isoformat(), now.time().replace(tzinfo=None)
    data = calendar_for_year(now.year)
    known = bool(data and data["valid_from"] <= day <= data["valid_through"])
    operator_known = config.MARKET_CALENDAR_VERIFIED_THROUGH >= day
    holidays = data.get("holidays", {}) if data else {}
    special = config.MARKET_SPECIAL_SESSIONS.get(day) or (data or {}).get("special_sessions", {}).get(day)
    regular = (data or {}).get("regular", {"pre_open": "09:00", "open": "09:15", "close": "15:30", "post_close_start": "15:40", "post_close_end": "16:00"})
    hours = {**regular, **special} if isinstance(special, dict) else regular
    if isinstance(special, dict):
        hours["pre_open"] = special.get("pre_open", special["open"])
        hours["post_close_start"] = special.get("post_close_start", special["close"])
        hours["post_close_end"] = special.get("post_close_end", special["close"])
    try:
        start = time.fromisoformat(hours["open"])
        end = time.fromisoformat(hours["close"])
        pre = time.fromisoformat(hours.get("pre_open", hours["open"]))
        post = time.fromisoformat(hours.get("post_close_start", hours["close"]))
        finish = time.fromisoformat(hours.get("post_close_end", hours["close"]))
        if not pre <= start < end <= post <= finish:
            raise ValueError("Invalid session order")
    except (TypeError, ValueError, KeyError):
        special, known, operator_known = None, False, False
        start, end, pre, post, finish = time(9,15), time(15,30), time(9), time(15,40), time(16)
    verified = known or operator_known or bool(special)
    holiday = day in holidays or day in config.MARKET_HOLIDAYS
    weekend = now.weekday() >= 5
    is_trading_day = verified and (bool(special) or (not holiday and not weekend))
    reason = str(special.get("name", "Configured special session")) if special else holidays.get(day, "Exchange holiday") if holiday else "Weekend" if weekend else "Official NSE cash-market calendar"
    if not verified:
        phase, label = "unknown", "NSE · Calendar unavailable"
    elif not is_trading_day:
        phase, label = "closed", "NSE · Market closed"
    elif pre <= clock < start:
        phase, label = "pre_open", "NSE · Pre-open"
    elif start <= clock < end:
        phase, label = "open", "NSE · Normal market"
        if hours.get("cas_continuous_close") and clock >= time.fromisoformat(hours["cas_continuous_close"]):
            label = "NSE · Normal / CAS auction"
    elif end <= clock < post:
        phase, label = "closing", "NSE · Closing session"
    elif post <= clock < finish:
        phase, label = "post_close", "NSE · Post-close"
    else:
        phase, label = "closed", "NSE · Market closed"
    return {"is_open": phase == "open", "status": phase, "label": label, "reason": reason,
            "trading_date": day, "is_trading_day": is_trading_day,
            "opening_time": start.isoformat(), "closing_time": end.isoformat(),
            "completed_session_time": finish.isoformat(),
            "calendar_verified": verified, "calendar_reviewed_on": (data or {}).get("reviewed_on"),
            "calendar_valid_through": (data or {}).get("valid_through"),
            "calendar_sources": (data or {}).get("sources", []),
            "calendar_note": (data or {}).get("note", "No authoritative calendar loaded for this year; check the official exchange circulars."),
            "timezone": "Asia/Kolkata"}


def completed_daily_date(now=None):
    now = now or datetime.now(TZ)
    now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    state = session_state(now)
    finish = datetime.combine(now.date(), time.fromisoformat(state["completed_session_time"]), TZ)
    if state["is_trading_day"] and now >= finish + timedelta(minutes=15):
        return now.date()
    return now.date() - timedelta(days=1)
