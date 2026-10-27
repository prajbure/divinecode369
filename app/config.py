import os
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
