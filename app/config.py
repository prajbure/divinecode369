import os
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KITE_API_KEY = os.getenv("KITE_API_KEY", "").strip()
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "").strip()
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "").strip()
KITE_REDIRECT_URL = os.getenv("KITE_REDIRECT_URL", "").strip()


def set_kite_access_token(token: str) -> None:
    global KITE_ACCESS_TOKEN
    KITE_ACCESS_TOKEN = token.strip()
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
try:
    MATCH_TOLERANCE = max(0.0, float(os.getenv("MATCH_TOLERANCE", "0.01")))
except ValueError:
    MATCH_TOLERANCE = 0.01
try:
    MAX_DIFFERENCE = max(0.0, float(os.getenv("MAX_DIFFERENCE", "10")))
except ValueError:
    MAX_DIFFERENCE = 10.0
WATCHLIST_PATH = ROOT / "data" / "watchlist.txt"


def enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def integer(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "data" / "divine.sqlite3")))
MODEL_DIRECTORY = Path(os.getenv("MODEL_DIRECTORY", str(ROOT / "data" / "models")))
# Enable only after confirming the account's exchange/provider retention rights.
DATA_RETENTION_AUTHORIZED = enabled("DATA_RETENTION_AUTHORIZED")
HISTORICAL_ENABLED = enabled("HISTORICAL_ENABLED")
INTRADAY_ENABLED = enabled("INTRADAY_ENABLED")
STREAMING_ENABLED = enabled("STREAMING_ENABLED", "true")
QUOTE_POLL_SECONDS = integer("QUOTE_POLL_SECONDS", 10, 3)
QUOTE_STALE_SECONDS = integer("QUOTE_STALE_SECONDS", 45, 10)
SNAPSHOT_INTERVAL_SECONDS = integer("SNAPSHOT_INTERVAL_SECONDS", 300, 60)
SNAPSHOT_RETENTION_DAYS = integer("SNAPSHOT_RETENTION_DAYS", 7)
INTRADAY_RETENTION_DAYS = integer("INTRADAY_RETENTION_DAYS", 30)
DAILY_RETENTION_DAYS = integer("DAILY_RETENTION_DAYS", 1825, 365)
MARKET_HOLIDAYS = set(filter(None, os.getenv("MARKET_HOLIDAYS", "").split(",")))
MARKET_CALENDAR_VERIFIED_THROUGH = os.getenv("MARKET_CALENDAR_VERIFIED_THROUGH", "")
try:
    MARKET_SPECIAL_SESSIONS = json.loads(os.getenv("MARKET_SPECIAL_SESSIONS", "{}"))
    if not isinstance(MARKET_SPECIAL_SESSIONS, dict):
        MARKET_SPECIAL_SESSIONS = {}
except ValueError:
    MARKET_SPECIAL_SESSIONS = {}
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
# ADMIN_TOKEN is a backend-only session key, never a browser credential.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
ADMIN_ORIGIN = os.getenv("ADMIN_ORIGIN", "https://divinecode369.in").rstrip("/")
ADMIN_SESSION_SECONDS = min(integer("ADMIN_SESSION_SECONDS", 28800, 300), 86400)
ADMIN_SESSION_DATABASE_PATH = DATABASE_PATH.parent / ".private" / "admin-sessions.sqlite3"
PLATFORM_DATABASE_PATH = Path(os.getenv('PLATFORM_DATABASE_PATH', str(DATABASE_PATH.parent / '.private' / 'platform.sqlite3')))
ANDROID_APP_ID = "in.divinecode369.app"
ANDROID_APP_SHA256_CERTIFICATE = os.getenv("ANDROID_APP_SHA256_CERTIFICATE", "").strip()
AUTO_RETRAIN_ENABLED = enabled("AUTO_RETRAIN_ENABLED")
TRAINING_MIN_NEW_SESSIONS = integer("TRAINING_MIN_NEW_SESSIONS", 20, 5)
BACKTEST_COST_BPS = integer("BACKTEST_COST_BPS", 20, 0)
HISTORY_AUTO_UPDATE_ENABLED = enabled("HISTORY_AUTO_UPDATE_ENABLED")
IMPORT_RETRY_LIMIT = integer("IMPORT_RETRY_LIMIT", 3, 1)

# Separate, opt-in IPO provider. Never use or change Kite credentials here.
IPOGURU_API_KEY = os.getenv("IPOGURU_API_KEY", "").strip()
IPOGURU_BASE_URL = os.getenv("IPOGURU_BASE_URL", "https://www.ipoguru.in/api/v2").rstrip("/")
IPOGURU_ENABLED = enabled("IPOGURU_ENABLED")
IPOGURU_CACHE_SECONDS = integer("IPOGURU_CACHE_SECONDS", 900, 300)
IPOGURU_QUOTA_PATH = DATABASE_PATH.parent / "ipoguru-quota.sqlite3"
KITE_SESSION_PATH = DATABASE_PATH.parent / ".private" / "kite-session.bin"
