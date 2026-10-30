from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from . import config
from .scanner import load_watchlist, save_watchlist, run_scan, reference_scan_symbols
from .provider import ProviderError, create_kite_session, daily_history, equity_symbols, live_quotes, stock_names

scheduler = BackgroundScheduler(timezone=ZoneInfo(config.APP_TIMEZONE))
latest_result = {"as_of": None, "rows": [], "matches": [], "message": "Waiting for the scheduled 09:15 scan or click Refresh now."}
last_error = None

def scheduled_scan():
    global latest_result, last_error
    try:
        latest_result = run_scan(reference_scan_symbols(), universe="reference")
        last_error = None
    except Exception as exc:
        last_error = str(exc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(scheduled_scan, CronTrigger(day_of_week="mon-fri", hour=9, minute=15, timezone=ZoneInfo(config.APP_TIMEZONE)), id="daily_scan", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="Open Match Scanner", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.ROOT / "static")), name="static")

@app.get("/")
def home():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace("Up to 500 NSE + BSE instruments", "150 optionable NSE + BSE stocks")
    html = html.replace("Up to 500 instruments · use NSE:SYMBOL or BSE:SYMBOL.", "150 optionable stocks · 75 NSE + 75 BSE.")
    html = html.replace("Load 500 NSE + BSE stocks", "Load 150 NSE + BSE stocks")
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )

@app.get("/api/status")
def status():
    return {"watchlist": load_watchlist(), "latest": latest_result, "error": last_error, "scheduled_time": "09:15 Asia/Kolkata, Monday-Friday", "tolerance": config.MATCH_TOLERANCE, "max_difference": config.MAX_DIFFERENCE, "token_configured": bool(config.KITE_ACCESS_TOKEN)}


@app.get("/api/market-overview")
def market_overview():
    """Return index pulse data for the dashboard without exposing credentials."""
    symbols = [
        "NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:NIFTY IT", "NSE:NIFTY AUTO",
        "NSE:NIFTY PHARMA", "NSE:NIFTY FMCG", "NSE:NIFTY METAL", "NSE:NIFTY REALTY",
        "NSE:NIFTY PSU BANK", "NSE:NIFTY MIDCAP 50", "NSE:INDIA VIX", "BSE:SENSEX",
    ]
    try:
        result = live_quotes(symbols)
        cards = [
            {"symbol": row["symbol"], "price": row["ltp"], "change_pct": row["change_pct"], "open": row["open"], "prev_close": row["prev_close"]}
            for row in result.get("data", [])
        ]
        return {"cards": cards, "as_of": datetime.now(ZoneInfo(config.APP_TIMEZONE)).isoformat()}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/auth/kite/login")
def kite_login():
    if not config.KITE_API_KEY or not config.KITE_REDIRECT_URL:
        raise HTTPException(status_code=503, detail="Configure KITE_API_KEY and KITE_REDIRECT_URL first.")
    return RedirectResponse(
        f"https://kite.zerodha.com/connect/login?v=3&api_key={config.KITE_API_KEY}"
    )


@app.get("/auth/kite/callback")
def kite_callback(request_token: str | None = None, status: str | None = None):
    if status != "success" or not request_token:
        raise HTTPException(status_code=400, detail="Kite login was not completed.")
    try:
        create_kite_session(request_token)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/")

@app.post("/api/scan")
def scan():
    global latest_result, last_error
    try:
        latest_result = run_scan(reference_scan_symbols(), universe="reference")
        last_error = None
        return latest_result
    except ProviderError as exc:
        last_error = str(exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        last_error = str(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/api/watchlist")
def get_watchlist():
    symbols = load_watchlist()
    details = []
    if config.KITE_ACCESS_TOKEN:
        try:
            details = stock_names(symbols)
        except ProviderError:
            details = []
    return {"symbols": symbols, "details": details}


@app.get("/api/watchlist/names")
def get_watchlist_names():
    try:
        return {"details": stock_names(load_watchlist())}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.put("/api/watchlist")
def put_watchlist(body: dict):
    try:
        symbols = save_watchlist(str(body.get("symbols", "")))
        return {"symbols": symbols, "count": len(symbols)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/watchlist/universe")
def put_market_universe():
    """Load 150 optionable equities, balanced across NSE and BSE."""
    try:
        universe = equity_symbols("NSE", 75) + equity_symbols("BSE", 75)
        if not universe:
            raise ProviderError("Kite returned no optionable equity instruments. Please reconnect Kite and try again.")
        symbols = save_watchlist("\n".join(universe))
        return {"symbols": symbols, "count": len(symbols), "nse_count": sum(s.startswith("NSE:") for s in symbols), "bse_count": sum(s.startswith("BSE:") for s in symbols), "optionable_only": True}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/history/{symbol}")
def history(symbol: str):
    symbol = symbol.strip().upper()
    if not symbol or not all(ch.isalnum() or ch in "&-._" for ch in symbol):
        raise HTTPException(status_code=400, detail="Invalid stock symbol.")
    try:
        return daily_history(symbol, 8)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
