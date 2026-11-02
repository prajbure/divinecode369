"""Additive private research helpers. No historical downloads or order APIs."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from . import config
from .calendar import completed_daily_date, session_state
from .scanner import reference_groups
from .journal import Journal, summary


def create_router(store, require_admin):
    router = APIRouter()
    journal=Journal(store)

    @router.get('/api/journal')
    def journal_records(request: Request):
        require_admin(request)
        rows=journal.records()
        return {'records':rows[:500], 'total':len(rows), 'analytics':summary(rows)}

    @router.get('/api/journal/export')
    def export_journal(request: Request, as_json: bool=False):
        require_admin(request)
        if as_json:return {'csv':journal.export()}
        return Response(journal.export(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=divine-personal-journal.csv','Cache-Control':'no-store'})

    @router.post('/api/journal',status_code=201)
    def add_journal(request: Request,body:dict):
        require_admin(request)
        try:return journal.save(body)
        except ValueError as error:raise HTTPException(422,str(error)) from error

    @router.put('/api/journal/{record_id}')
    def edit_journal(request: Request,record_id:str,body:dict):
        require_admin(request)
        try:return journal.save(body,record_id)
        except ValueError as error:raise HTTPException(422,str(error)) from error
        except LookupError as error:raise HTTPException(404,str(error)) from error

    @router.delete('/api/journal/{record_id}')
    def delete_journal(request: Request,record_id:str):
        require_admin(request)
        try:journal.delete(record_id)
        except LookupError as error:raise HTTPException(404,str(error)) from error
        return {'deleted':True}

    @router.get('/api/intelligence/context/{symbol}')
    def candle_context(request: Request, symbol: str):
        require_admin(request)
        allowed = {'NSE:' + stock[0] for group in reference_groups() for stock in group['stocks']}
        if symbol not in allowed:
            raise HTTPException(400, 'Choose an existing approved instrument.')
        if not config.DATA_RETENTION_AUTHORIZED:
            return {'enabled': False, 'reason': 'Historical retention remains disabled. No candle data was requested or stored.', 'daily': [], 'minutes': []}
        latest = completed_daily_date().isoformat()
        current=datetime.now(ZoneInfo(config.APP_TIMEZONE))
        previous_session=None
        for offset in range(1,15):
            candidate=current-timedelta(days=offset)
            if session_state(candidate)['is_trading_day']:
                previous_session=candidate.date().isoformat()
                break
        daily = [r for r in store.candles(symbol, limit=10) if r['timestamp'][:10] <= latest]
        minutes = store.candles(symbol, interval='minute', limit=600) if config.INTRADAY_ENABLED else []
        return {'enabled': True, 'daily': daily, 'minutes': minutes,
                'session_date': current.date().isoformat(), 'previous_session_date': previous_session,
                'reason': 'Previously authorized stored Kite candles only; no provider requests are made.'}

    return router
