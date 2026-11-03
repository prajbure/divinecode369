"""Native/web adapters over the existing shared provider pipeline."""
from datetime import datetime, timezone
from typing import Literal
import re
import json

from fastapi import APIRouter, HTTPException, Query, Request

from . import config, personal
from . import mobile_models as m
from .mobile_auth import personal_identity
from .market_intelligence import analytics
from .scanner import reference_groups


def phase(ipo, confirmed=False):
    stage = (ipo.get('stage') or '').lower()
    if not ipo.get('is_listed') and (confirmed or stage in ('allotted', 'allotment completed', 'allotment_finalized')):
        return 'allotted'
    if ipo.get('status', '').lower() == 'open' and not ipo.get('is_listed'):
        return 'ongoing'
    if ipo.get('status', '').lower() == 'upcoming':
        return 'upcoming'
    return 'closed'


def ipo_row(row, confirmed=False):
    return {**row, 'phase': phase(row, confirmed)}


def ipo_meta(resource):
    meta = resource.get('meta', {})
    return m.Meta(cache_timestamp=meta.get('fetched_at'), provider_timestamp=None,
                  stale=bool(meta.get('cache_stale')), unavailable=not meta.get('available', False),
                  source='IPO Guru · shared Standard cache', message=(meta.get('error') or {}).get('message'))


def create_mobile_router(resolve):
    """Resolve application singletons on demand, including when tests replace them."""
    router = APIRouter(prefix='/api/v1/mobile', tags=['Mobile v1'],responses={status:{'model':m.APIError} for status in (400,401,403,404,422,429,503)})

    def state():
        market, manager, ipo, store, lab = resolve()
        snap = market.snapshot()
        shared = analytics.build(reference_groups(), snap)
        meta = m.Meta(cache_timestamp=snap.get('as_of'), provider_timestamp=max((r.get('quote_timestamp') for r in snap['rows'] if r.get('quote_timestamp')), default=None),
                      stale=any(r.get('quote_status') == 'stale' for r in snap['rows']), unavailable=not any(r.get('ltp') is not None for r in snap['rows']), source='Kite · shared market pipeline')
        rows = []
        opportunities = {r['symbol']:r for r in shared['opportunities']}
        for row in snap['rows']:
            groups = [g for g in reference_groups() if any('NSE:'+s[0] == row['symbol'] for s in g['stocks'])]
            rows.append(m.Stock(**{**row, 'name':row.get('name') or row['symbol'].split(':')[-1],
                                  'sectors':[g['name'] for g in groups], 'sector_ids':[g['id'] for g in groups],
                                  'match_type':'exact' if row.get('match') else 'near' if row.get('near_match') else 'none' if row.get('open') is not None else 'unavailable',
                                  'freshness':row.get('quote_status') or 'unavailable', 'provider_timestamp':row.get('quote_timestamp'),
                                  'opening_date':snap.get('opening_date'), 'signal_state':shared['opening'][row['symbol']]['ranges']['fifteen'].get('state', 'unavailable'),
                                  'intelligence':shared['opening'][row['symbol']], 'opportunity':opportunities[row['symbol']]}))
        sectors = [m.Sector(**{**s, 'memberships':len(g['stocks']), 'unique_symbols':s['total'], 'stocks':[r for r in rows if s['id'] in r.sector_ids]}) for s,g in zip(shared['sectors'],reference_groups())]
        return snap, shared, rows, sectors, meta

    def health_value(snap):
        manager = resolve()[1]
        connection = manager.snapshot()
        quality = {key:sum(r.get('quote_status')==key for r in snap['rows']) for key in ('live','stale','unavailable')}
        return m.Health(kite_state=connection.get('kite',{}).get('state','unavailable'), ipo_state=connection.get('ipoguru',{}).get('state','unavailable'),
                        market_state=snap.get('market',{}).get('status','unavailable'), **quality, provider_timestamp=max((r.get('quote_timestamp') for r in snap['rows'] if r.get('quote_timestamp')),default=None), cache_timestamp=snap.get('as_of'),ipo_cache_timestamp=manager.get_overview().get('meta',{}).get('fetched_at'))

    @router.get('/health', response_model=m.Health)
    def health():
        return health_value(resolve()[0].snapshot())

    @router.get('/intelligence')
    def intelligence(request:Request,weights:str=Query('{}',max_length=500),context_symbols:str=Query('',max_length=1000)):
        try:
            selected=json.loads(weights)
            if not isinstance(selected,dict) or set(selected)-{'opening','sector','price','volume','liquidity','freshness'}: raise ValueError()
        except (ValueError,TypeError): raise HTTPException(422,'Invalid relevance weights.') from None
        contexts={}
        if context_symbols:
            personal_identity(request,'research:read')
            symbols=context_symbols.split(',')
            allowed={'NSE:'+s[0] for g in reference_groups() for s in g['stocks']}
            if len(symbols)>8 or any(s not in allowed for s in symbols):raise HTTPException(422,'Choose at most eight approved instruments.')
            from .calendar import session_state, completed_daily_date
            from datetime import timedelta
            from zoneinfo import ZoneInfo
            now=datetime.now(ZoneInfo(config.APP_TIMEZONE));previous=None
            for offset in range(1,15):
                candidate=now-timedelta(days=offset)
                if session_state(candidate)['is_trading_day']:previous=candidate.date().isoformat();break
            if config.DATA_RETENTION_AUTHORIZED:
                for symbol in symbols:
                    contexts[symbol]={'enabled':True,'daily':[r for r in resolve()[3].candles(symbol,limit=10) if r['timestamp'][:10]<=completed_daily_date().isoformat()],
                                      'minutes':resolve()[3].candles(symbol,interval='minute',limit=600) if config.INTRADAY_ENABLED else [],'session_date':now.date().isoformat(),'previous_session_date':previous}
        try:return analytics.build(reference_groups(),resolve()[0].snapshot(),contexts,selected)
        except ValueError:raise HTTPException(422,'Invalid relevance weights.') from None

    @router.get('/overview', response_model=m.Overview)
    def overview():
        snap, shared, rows, sectors, meta = state()
        cached = resolve()[1].get_overview()
        return m.Overview(health=health_value(snap), market_label=snap['market'].get('label',snap['market'].get('status','Unavailable')), summary=shared['summary'], sectors=sectors,
                          matches=[r for r in rows if r.match or r.near_match][:12], ipo_highlights=[ipo_row(r) for r in cached.get('rows',[]) if phase(r) in ('ongoing','upcoming')][:6], regime=shared['regime'], meta=meta)

    @router.get('/scanner', response_model=m.StockPage)
    def scanner(page:int=Query(1,ge=1), page_size:int=Query(30,ge=1,le=100), match:Literal['all','exact','near','universe']='all', sector:str|None=None,
                search:str=Query('',max_length=100), sort:Literal['symbol','difference','change','relevance']='symbol', direction:Literal['asc','desc']='asc'):
        _,_,rows,_,meta = state()
        if sector and sector not in {g['id'] for g in reference_groups()}: raise HTTPException(404,'Sector not found.')
        matches = {'universe':lambda r:True,'all':lambda r:r.match or r.near_match,'exact':lambda r:r.match,'near':lambda r:r.near_match}[match]
        rows=[r for r in rows if matches(r)
              and (not sector or sector in r.sector_ids) and (search.casefold() in (r.name+' '+r.symbol).casefold())]
        field={'symbol':lambda r:r.symbol, 'difference':lambda r:abs(r.difference) if r.difference is not None else None, 'change':lambda r:r.change_pct, 'relevance':lambda r:r.opportunity.get('score')}[sort]
        present=[r for r in rows if field(r) is not None]; missing=[r for r in rows if field(r) is None]
        rows=sorted(present,key=field,reverse=direction=='desc')+missing
        return m.StockPage(items=rows[(page-1)*page_size:page*page_size],total=len(rows),page=page,page_size=page_size,meta=meta)

    @router.get('/sectors', response_model=m.SectorPage)
    def sectors():
        _,_,_,sectors,meta=state()
        return m.SectorPage(items=sectors,meta=meta)

    @router.get('/sectors/{sector_id}', response_model=m.Sector)
    def sector(sector_id:str):
        found=next((s for s in state()[3] if s.id==sector_id),None)
        if not found: raise HTTPException(404,'Sector not found.')
        return found

    @router.get('/stocks/{symbol}', response_model=m.Stock)
    def stock(symbol:str):
        symbol=symbol.upper(); symbol=symbol if ':' in symbol else 'NSE:'+symbol
        found=next((r for r in state()[2] if r.symbol==symbol),None)
        if not found: raise HTTPException(404,'Stock is outside the approved universe.')
        return found

    @router.get('/ipos', response_model=m.IPOPage)
    def ipos(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),phase_filter:Literal['all','ongoing','upcoming','allotted','closed']=Query('ongoing',alias='phase'),
             board:Literal['all','Mainboard','SME']='all',search:str=Query('',max_length=100),sort:Literal['schedule','name','gmp','subscription']='schedule'):
        cached=resolve()[1].get_overview()
        rows=[ipo_row(r) for r in cached.get('rows',[])]
        rows=[r for r in rows if (board=='all' or r['type']==board) and search.casefold() in (r['name']+' '+r['slug']).casefold()]
        counts={p:sum(r['phase']==p for r in rows) if not ipo_meta(cached).unavailable else None for p in ('ongoing','upcoming','allotted','closed')}
        rows=[r for r in rows if phase_filter=='all' or r['phase']==phase_filter]
        field={'name':lambda r:r['name'].casefold(), 'schedule':lambda r:r['timeline'].get('close_date' if r['phase']=='ongoing' else 'open_date') or '9999',
               'gmp':lambda r:r['gmp'].get('percentage'), 'subscription':lambda r:r.get('subscription_total')}[sort]
        present=[r for r in rows if field(r) is not None]; missing=[r for r in rows if field(r) is None]
        rows=sorted(present,key=field,reverse=sort in ('gmp','subscription'))+missing
        return m.IPOPage(items=rows[(page-1)*page_size:page*page_size],total=len(rows),page=page,page_size=page_size,counts=counts,meta=ipo_meta(cached))

    def validate_slug(slug):
        if len(slug)>150 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug): raise HTTPException(422,'Invalid IPO identifier.')

    @router.get('/ipos/{slug}', response_model=m.IPODetail)
    def ipo_detail(slug:str):
        validate_slug(slug)
        result=resolve()[2].detail(slug)
        return m.IPODetail(**{**result,'ipo':ipo_row(result['ipo'],result.get('allotment_confirmed')) if result.get('ipo') else None,'meta':ipo_meta(result)})

    @router.get('/ipos/{slug}/{kind}', response_model=m.Resource)
    def ipo_resource(slug:str,kind:Literal['history','subscription','anchors','listing-comparison']):
        validate_slug(slug)
        if kind=='listing-comparison':
            from .ipo_comparison import listing_comparison
            ipo=next((r for r in resolve()[1].get_overview().get('rows',[]) if r['slug']==slug),None)
            if ipo is None:ipo=resolve()[2].detail(slug).get('ipo')
            resource=resolve()[2].resource(slug,'history')
            data=listing_comparison(ipo,resource['data']) if ipo and resource.get('data') else {'available':False,'reason':'Verified listing and pre-listing GMP archive are unavailable.'}
            return m.Resource(data=data,meta=ipo_meta(resource))
        if kind=='subscription': resolve()[1].interest(slug,kind)
        result=resolve()[2].resource(slug,kind)
        meta=ipo_meta(result)
        if result.get('data'): meta.provider_timestamp=result['data'].get('freshness',{}).get('as_of')
        return m.Resource(data=result.get('data'),meta=meta)

    @router.get('/watchlist', response_model=m.Watchlist)
    def watchlist(request:Request): return personal.saved_items(personal_identity(request)['owner'])

    @router.put('/watchlist', response_model=m.Watchlist)
    def save_watchlist(request:Request,body:m.SavedItem): return personal.save_item(personal_identity(request)['owner'],body)

    @router.get('/alerts', response_model=m.AlertRules)
    def alerts(request:Request): return personal.rules(personal_identity(request)['owner'])

    @router.put('/alerts', response_model=m.AlertRules)
    def save_alert(request:Request,body:m.AlertRule): return personal.save_rule(personal_identity(request)['owner'],body)

    @router.delete('/alerts/{rule_id}', response_model=m.AlertRules)
    def delete_alert(request:Request,rule_id:str): return personal.delete_rule(personal_identity(request)['owner'],rule_id)

    @router.get('/alerts/inbox', response_model=m.AlertInbox)
    def inbox(request:Request): return personal.inbox(personal_identity(request)['owner'])

    @router.get('/preferences', response_model=m.Preferences)
    def preferences(request:Request): return personal.preferences(personal_identity(request)['owner'])

    @router.put('/preferences', response_model=m.Preferences)
    def save_preferences(request:Request,body:m.Preferences): return personal.preferences(personal_identity(request)['owner'],body)

    @router.get('/history/{symbol}', response_model=m.History)
    def history(request:Request,symbol:str):
        personal_identity(request)
        symbol=stock(symbol).symbol
        allowed=config.HISTORICAL_ENABLED and config.DATA_RETENTION_AUTHORIZED
        return m.History(symbol=symbol,candles=resolve()[3].candles(symbol) if allowed else [],enabled=allowed,
                         meta=m.Meta(unavailable=not allowed,source='Existing licensed backend history',message=None if allowed else 'Historical retention is not enabled.'))

    @router.get('/predictions')
    def predictions(request:Request):
        personal_identity(request)
        return resolve()[4].status()

    return router
