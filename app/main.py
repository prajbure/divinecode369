from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import asyncio
import hmac
import json
import logging
import secrets
import threading
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, provider
from .market import MarketService, session_state
from .predictions import PredictionLab
from .scanner import load_watchlist, save_watchlist, reference_groups
from .storage import Store
from .imports import ImportService
from .reconciliation import reconciliation_report
from .ipoguru import IPOGuruClient
from .ipo_service import IPOService
from .connections import ConnectionManager
from .logging_filters import install as install_credential_filters,remember_secret
from .admin_auth import auth as admin_auth, router as admin_router


class RedactAuthAccessLog(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and record.args[2].startswith("/auth/"):
            args = list(record.args)
            args[2] = args[2].split("?", 1)[0]
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(RedactAuthAccessLog())
install_credential_filters()

store = Store()
market = MarketService(store)
ipo_service = IPOService(IPOGuruClient())
connections = ConnectionManager(market,ipo_service)
lab = PredictionLab(store)
scheduler = BackgroundScheduler(timezone=ZoneInfo(config.APP_TIMEZONE))
history_lock = threading.Lock()
index_lock = threading.Lock()
index_cache = {"cards": [], "as_of": None}
index_fetched = None


def scheduled_scan():
    current = session_state()
    if current["is_open"] and datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%H:%M") == current["opening_time"][:5]:
        try:
            market.scan()
        except provider.ProviderError:
            pass


def daily_maintenance():
    store.cleanup()
    if config.AUTO_RETRAIN_ENABLED and config.DATA_RETENTION_AUTHORIZED:
        try:
            lab.train()
        except ValueError:
            pass


def incremental_maintenance():
    if session_state()["is_trading_day"] and hasattr(app.state, "imports"):
        app.state.imports.schedule_incremental()


@asynccontextmanager
async def lifespan(app):
    store.initialize(reference_groups())
    store.cleanup()
    app.state.imports = ImportService(store, on_complete=lab.infer)
    app.state.imports.start()
    scheduler.add_job(scheduled_scan, CronTrigger(minute="*", second=5, timezone=ZoneInfo(config.APP_TIMEZONE)), id="daily_scan", replace_existing=True)
    scheduler.add_job(incremental_maintenance, CronTrigger(hour=18, minute=20, timezone=ZoneInfo(config.APP_TIMEZONE)), id="incremental_history", replace_existing=True)
    scheduler.add_job(daily_maintenance, CronTrigger(hour=18, minute=30, timezone=ZoneInfo(config.APP_TIMEZONE)), id="maintenance", replace_existing=True)
    scheduler.start()
    connections.start()
    market.start()
    yield
    connections.stop()
    app.state.imports.stop()
    market.stop()
    scheduler.shutdown(wait=False)


app = FastAPI(title="DIVINE CODE 369 — Market Intelligence", version="2.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.ROOT / "static")), name="static")
app.include_router(admin_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        # All API mutations are administrative, including future provider/credential endpoints.
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_admin(request)
        response = await call_next(request)
    except HTTPException as error:
        response = JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/api/", "/auth/")):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/auth/"):
        response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def require_admin(request: Request):
    return admin_auth.require_admin(request)


def home_response():
    return HTMLResponse((config.ROOT / "static" / "index.html").read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


from .advanced import create_router
app.include_router(create_router(store, require_admin))

from .ipo_routes import create_ipo_router
app.include_router(create_ipo_router(require_admin, home_response, service=ipo_service, manager=connections))

@app.get('/connections',response_class=HTMLResponse)
@app.get('/health',response_class=HTMLResponse)
def connection_page():return home_response()

@app.get('/api/connections/status')
def connection_status():return connections.snapshot()

@app.post('/api/connections/kite/disconnect')
def disconnect_kite(request:Request):
    require_admin(request)
    try:connections.disconnect_kite()
    except Exception:raise HTTPException(503,'Kite stopped locally. Protected session cleanup could not be confirmed; check local file permissions.') from None
    response=JSONResponse(connections.snapshot())
    response.delete_cookie('divine_scan_session')
    return response

@app.post('/api/connections/kite/recheck')
def recheck_kite(request:Request):
    require_admin(request)
    connections.kite.next_check=0
    return connections.snapshot()


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/sectors", response_class=HTMLResponse)
@app.get("/scanner", response_class=HTMLResponse)
@app.get("/live-market", response_class=HTMLResponse)
@app.get("/ai-predictions", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
def home():
    return home_response()


@app.get("/sectors/{sector_id}", response_class=HTMLResponse)
def sector_page(sector_id: str):
    if sector_id not in {g["id"] for g in reference_groups()}:
        raise HTTPException(404, "Sector not found.")
    return home_response()


@app.get("/stocks/{symbol}", response_class=HTMLResponse)
def stock_page(symbol: str):
    if symbol.upper() not in {s[0] for g in reference_groups() for s in g["stocks"]}:
        raise HTTPException(404, "Stock is outside the approved universe.")
    return home_response()


@app.get("/api/status")
def status():
    snap = market.snapshot()
    return {"watchlist": load_watchlist(), "latest": {**market.scan_result, "rows": snap["rows"], "universe": "reference"},
            "error": snap["error"], "scheduled_time": "Official NSE session opening, including published special sessions, Asia/Kolkata",
            "tolerance": 0, "max_difference": config.MAX_DIFFERENCE, "token_configured": bool(config.KITE_ACCESS_TOKEN), "market": snap,"connections":connections.snapshot()}


@app.get("/api/quotes")
def quotes():
    return market.snapshot()


@app.get("/api/stream")
async def stream(request: Request):
    async def events():
        yield "retry: 5000\n\n"
        previous = None
        counter = 0
        while not await request.is_disconnected():
            snap = await asyncio.to_thread(market.snapshot)
            key = (snap["sequence"], tuple(r["quote_status"] for r in snap["rows"]), snap["market"]["status"])
            if previous != key:
                yield f"id: {snap['sequence']}\nevent: quotes\ndata: {json.dumps(snap, allow_nan=False)}\n\n"
                previous = key
            if counter % 7 == 0:
                yield ': heartbeat\nevent: heartbeat\ndata: {"connected":true}\n\n'
            if counter % 5 == 0:
                health=await asyncio.to_thread(connections.snapshot)
                yield f'event: connections\ndata: {json.dumps(health,allow_nan=False)}\n\n'
            counter += 1
            await asyncio.sleep(2)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/market-overview")
def market_overview():
    global index_cache, index_fetched
    symbols = ["NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:NIFTY IT", "NSE:NIFTY AUTO", "NSE:NIFTY PHARMA", "NSE:NIFTY FMCG", "NSE:NIFTY METAL", "NSE:NIFTY REALTY", "NSE:NIFTY PSU BANK", "NSE:NIFTY MIDCAP 50", "NSE:INDIA VIX", "BSE:SENSEX"]
    with index_lock:
        now = datetime.now(ZoneInfo(config.APP_TIMEZONE))
        if index_fetched and (now - index_fetched).total_seconds() < 30:
            return index_cache
        try:
            result = provider.live_quotes(symbols)
            index_cache = {"cards": [{"symbol": r["symbol"], "price": r["ltp"], "change_pct": r["change_pct"], "open": r["open"], "prev_close": r["prev_close"], "quote_timestamp": r.get("quote_timestamp")} for r in result["data"]], "as_of": now.isoformat()}
            index_fetched = now
            return index_cache
        except provider.ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc


@app.get("/auth/kite/login")
def kite_login():
    # Old bookmarks remain useful; provider changes start only through a CSRF-protected POST.
    return RedirectResponse("/settings?connect=kite", status_code=303)


@app.post("/auth/kite/login")
def kite_login_start(request: Request):
    require_admin(request)
    if not config.KITE_API_KEY or not config.KITE_REDIRECT_URL:
        raise HTTPException(503, "Configure KITE_API_KEY and KITE_REDIRECT_URL first.")
    state = secrets.token_urlsafe(32)
    admin_auth.start_oauth(request, state)
    response = JSONResponse({"redirect_url": f"https://kite.zerodha.com/connect/login?v=3&api_key={config.KITE_API_KEY}&redirect_params=state%3D{state}"})
    response.set_cookie("kite_oauth_state", state, httponly=True, samesite="lax", secure=True, max_age=600)
    return response


@app.get("/auth/kite/callback")
def kite_callback(request: Request, request_token: str | None = None, status: str | None = None, state: str | None = None):
    admin_auth.require_admin(request, oauth_callback=True)
    cookie = request.cookies.get("kite_oauth_state", "")
    if status != "success" or not request_token or not state or not cookie or not hmac.compare_digest(state.encode(), cookie.encode()):
        raise HTTPException(400, "Kite login was not completed or the login state expired. Start login again.")
    admin_auth.consume_oauth(request, state)
    try:
        remember_secret(request_token)
        token=provider.create_kite_session(request_token)
        connections.accept_kite(token)
    except provider.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    response = RedirectResponse("/")
    response.delete_cookie("kite_oauth_state", secure=True, httponly=True, samesite="lax")
    return response


@app.post("/api/scan")
def scan(request: Request):
    require_admin(request)
    try:
        return market.scan()
    except provider.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/watchlist")
def get_watchlist():
    return {"symbols": load_watchlist(), "details": []}


@app.get("/api/watchlist/names")
def get_watchlist_names():
    try:
        return {"details": provider.stock_names(load_watchlist())}
    except provider.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put("/api/watchlist")
def put_watchlist(request: Request, body: dict):
    require_admin(request)
    try:
        symbols = save_watchlist(str(body.get("symbols", "")))
        return {"symbols": symbols, "count": len(symbols)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/watchlist/universe")
def put_market_universe(request: Request):
    require_admin(request)
    try:
        universe = provider.equity_symbols("NSE", 75) + provider.equity_symbols("BSE", 75)
        if not universe:
            raise provider.ProviderError("Kite returned no optionable equities.")
        symbols = save_watchlist("\n".join(universe))
        return {"symbols": symbols, "count": len(symbols), "nse_count": sum(s.startswith("NSE:") for s in symbols), "bse_count": sum(s.startswith("BSE:") for s in symbols), "optionable_only": True}
    except provider.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/history/imports")
def import_status():
    return {**store.import_summary(), "retention_authorized": config.DATA_RETENTION_AUTHORIZED,
            "historical_enabled": config.HISTORICAL_ENABLED, "auto_update_enabled": config.HISTORY_AUTO_UPDATE_ENABLED}


@app.get("/api/history/{symbol}")
def history(symbol: str, stored: bool = False):
    symbol = symbol.strip().upper()
    qualified = symbol if ":" in symbol else "NSE:" + symbol
    exchange, name = qualified.split(":", 1)
    if exchange not in {"NSE", "BSE"} or not name or not all(c.isalnum() or c in "&-._" for c in name):
        raise HTTPException(400, "Invalid stock symbol.")
    if stored:
        return {"symbol": qualified, "data": store.candles(qualified), "source": "stored Kite candles"}
    try:
        result = provider.daily_history(qualified, 8)
        store.capability("historical_viewer", "verified", "Transient daily candles succeeded. Retention rights are separate.")
        return result
    except provider.ProviderError as exc:
        store.capability("historical_viewer", "unavailable", str(exc))
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/settings")
def settings():
    return {"retention_authorized": config.DATA_RETENTION_AUTHORIZED, "historical_enabled": config.HISTORICAL_ENABLED,
            "intraday_enabled": config.INTRADAY_ENABLED, "streaming_enabled": config.STREAMING_ENABLED,
            "quote_poll_seconds": config.QUOTE_POLL_SECONDS, "snapshot_interval_seconds": config.SNAPSHOT_INTERVAL_SECONDS,
            "snapshot_retention_days": config.SNAPSHOT_RETENTION_DAYS, "daily_retention_days": config.DAILY_RETENTION_DAYS,
            "intraday_retention_days": config.INTRADAY_RETENTION_DAYS, "auto_retrain_enabled": config.AUTO_RETRAIN_ENABLED,
            "training_min_new_sessions": config.TRAINING_MIN_NEW_SESSIONS, "admin_login_configured": admin_auth.configured,
            "coverage": store.overview(), "market_calendar": session_state(), "market_depth": "Not requested; account capability unverified.",
            "historical_note": "Historical access and retention rights are separate capabilities. Confirm provider/exchange terms before enabling storage."}


@app.get("/api/instruments/reconciliation")
def instrument_report(download: bool = False):
    report = reconciliation_report(store)
    return JSONResponse(report, headers={"Content-Disposition": "attachment; filename=divine-instrument-reconciliation.json"} if download else {})


@app.post("/api/instruments/reconcile")
def audit_instruments(request: Request):
    require_admin(request)
    try:
        from .scanner import reference_scan_symbols
        store.instrument_details(provider.stock_names(reference_scan_symbols()))
        return reconciliation_report(store)
    except provider.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/calendar")
def calendar_status():
    return session_state()


@app.post("/api/history/imports/{job_id}/{operation}")
def control_import(request: Request, job_id: str, operation: str):
    require_admin(request)
    try:
        return request.app.state.imports.control(job_id, operation)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/history/import", status_code=202)
def import_history(request: Request, body: dict):
    require_admin(request)
    try:
        return request.app.state.imports.create(body)
    except ValueError as exc:
        raise HTTPException(409 if not config.DATA_RETENTION_AUTHORIZED or not config.HISTORICAL_ENABLED else 400, str(exc)) from exc


@app.get("/api/ai/status")
def ai_status():
    return lab.status()


@app.post("/api/ai/train", status_code=202)
def train_model(request: Request):
    require_admin(request)
    if lab.state == "training":
        raise HTTPException(409, "Training is already running.")
    if not config.DATA_RETENTION_AUTHORIZED:
        raise HTTPException(409, "Authorized historical data retention must be enabled first.")
    def work():
        try:
            lab.train()
        except ValueError:
            pass
    threading.Thread(target=work, daemon=True, name="divine-training").start()
    return {"message": "Training requested. Monitor model status for validation results."}


@app.post("/api/ai/predict")
def predict(request: Request):
    require_admin(request)
    try:
        return lab.infer()
    except (ValueError, ImportError) as exc:
        raise HTTPException(409, str(exc)) from exc
