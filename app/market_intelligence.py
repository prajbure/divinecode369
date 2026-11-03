"""Shared presentation analytics, ported from the existing terminal rules.

Never recomputes or replaces scanner exact/near classifications. No provider calls.
"""
from datetime import datetime, timezone
import math
from statistics import median
import threading
from zoneinfo import ZoneInfo

DEFAULT_WEIGHTS = {'opening':20, 'sector':20, 'price':20, 'volume':15, 'liquidity':10, 'freshness':15}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def positive(value):
    return finite(value) and value > 0


def clamp(value, low, high):
    return min(high, max(low, value))


def instant(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=ZoneInfo('Asia/Kolkata')) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def gap(row):
    return (row['open']-row['prev_close'])/row['prev_close']*100 if positive(row.get('open')) and positive(row.get('prev_close')) else None


def sector_metrics(group, rows):
    symbols = {'NSE:'+s[0] for s in group['stocks']}
    observed = list({r['symbol']:r for r in rows if r['symbol'] in symbols}.values())
    valid = [r for r in observed if finite(r.get('change_pct')) and positive(r.get('ltp'))]
    moves = [r['change_pct'] for r in valid]
    advance, decline = sum(v>0 for v in moves), sum(v<0 for v in moves)
    average, mid = (sum(moves)/len(moves), median(moves)) if moves else (None, None)
    absolute = sum(abs(v) for v in moves)
    concentration = sum(sorted([abs(v) for v in moves], reverse=True)[:2])/absolute if absolute else None
    breadth = advance/len(valid) if valid else None
    good_vwap = lambda r: positive(r.get('vwap')) and positive(r.get('volume')) and positive(r.get('ltp')) and r.get('vwap_source') == 'Kite average traded price'
    return {'id':group['id'], 'name':group['name'], 'total':len(symbols), 'available':len(valid), 'advancing':advance, 'declining':decline,
            'unchanged':len(valid)-advance-decline, 'average':average, 'median':mid, 'breadth':breadth, 'concentration':concentration,
            'dispersion':math.sqrt(sum((v-average)**2 for v in moves)/len(moves)) if len(moves)>=2 else None,
            'volume_participation':sum(positive(r.get('volume')) for r in observed)/len(symbols) if symbols else None,
            'above_vwap':sum(bool(good_vwap(r) and r['ltp']>r['vwap']) for r in observed),
            'below_vwap':sum(bool(good_vwap(r) and r['ltp']<r['vwap']) for r in observed),
            'strength':clamp(50+(advance-decline)/len(valid)*35+clamp(mid,-3,3)*5,0,100) if valid else None,
            'participation':'Unavailable' if not valid else 'Broad-based' if breadth>=.65 and len(valid)>=4 and concentration is not None and concentration<.65 else 'Concentrated in one or two stocks' if concentration is not None and concentration>=.65 else 'Mixed participation',
            'strongest':max(valid,key=lambda r:r['change_pct']) if valid else None, 'weakest':min(valid,key=lambda r:r['change_pct']) if valid else None,
            'gap_up':sum(gap(r) is not None and gap(r)>0 for r in observed), 'gap_down':sum(gap(r) is not None and gap(r)<0 for r in observed),
            'flat':sum(gap(r)==0 for r in observed), 'live':sum(r.get('quote_status')=='live' for r in valid),
            'stale':sum(r.get('quote_status')=='stale' for r in valid), 'unavailable':len(symbols)-len(valid),
            'volume_available':sum(finite(r.get('volume')) and r['volume']>=0 for r in observed),
            'vwap_available':sum(positive(r.get('vwap')) and positive(r.get('volume')) and r.get('vwap_source')=='Kite average traded price' for r in observed)}


def regime(groups, rows, benchmark=None):
    configured = {'NSE:'+s[0] for g in groups for s in g['stocks']}
    valid = list({r['symbol']:r for r in rows if r['symbol'] in configured and finite(r.get('change_pct')) and positive(r.get('ltp'))}.values())
    sectors = [sector_metrics(g, valid) for g in groups]
    observed = [s for s in sectors if s['available']]
    coverage = len(valid)/len(configured) if configured else 0
    advance = sum(r['change_pct']>0 for r in valid)/len(valid) if valid else None
    average = sum(r['change_pct'] for r in valid)/len(valid) if valid else None
    mid = median([r['change_pct'] for r in valid]) if valid else None
    participation = sum(s['median']>0 and s['breadth']>=.6 for s in observed)/len(observed) if observed else None
    bearish = sum(s['median']<0 and s['declining']/s['available']>=.6 for s in observed)/len(observed) if observed else None
    label = 'Mixed'
    if coverage<.6 or len(valid)<min(20,len(configured)):
        label = 'Insufficient data'
    elif advance>=.65 and participation>=.6 and average>=.5 and mid>0:
        label = 'Bullish trend'
    elif advance<=.35 and bearish>=.6 and average<=-.5 and mid<0:
        label = 'Bearish trend'
    elif abs(average)<.25 and abs(mid)<.25 and .35<=advance<=.65:
        label = 'Range-bound'
    contradictory, unavailable, observations = [], [], []
    benchmark = benchmark or {}
    at = instant(benchmark.get('quote_timestamp'))
    age = (datetime.now(timezone.utc)-at).total_seconds() if at else None
    if benchmark.get('quote_status')=='live' and positive(benchmark.get('vix')) and age is not None and 0<=age<=60:
        observations.append(f"Observed INDIA VIX {benchmark['vix']:.2f}")
        if label!='Insufficient data' and benchmark['vix']>=25: label='High volatility'
        elif label=='Range-bound' and benchmark['vix']<=12: label='Low volatility'
    else: unavailable.append('Verified benchmark/VIX and time-series volatility unavailable.')
    if valid:
        observations.extend([f'{len(valid)}/{len(configured)} unique configured stocks observed.', f'{advance*100:.1f}% advancing; median move {mid:.2f}%.'])
        if average>0 and advance<.5 or average<0 and advance>.5: contradictory.append('Average movement and majority breadth point in opposing directions.')
        if label=='Bullish trend' and any(s['median'] is not None and s['median']<0 for s in sectors): contradictory.append('Some custom baskets still have negative median movement.')
        if label=='Bearish trend' and any(s['median'] is not None and s['median']>0 for s in sectors): contradictory.append('Some custom baskets still have positive median movement.')
        if any(r.get('quote_status')!='live' for r in valid): contradictory.append('Includes closed, stale or timestamp-unknown observations; this is not a live whole-market assessment.')
    return {'label':label, 'coverage':coverage, 'average':average, 'median':mid, 'advancing_fraction':advance, 'sector_participation':participation,
            'observations':observations, 'contradictions':contradictory, 'unavailable':unavailable, 'sectors':sectors,
            'scope':f'Approved {len(configured)}-symbol sector universe and custom baskets only; not the whole NSE market or official sector indices.',
            'rules':'Minimum 60% coverage. Bull/bear requires 65%/35% breadth, 60% aligned baskets, aligned mean and median. Missing inputs remain unavailable.'}


def valid_candle(c):
    return c.get('source')=='kite' and all(positive(c.get(k)) for k in ['open','high','low','close']) and finite(c.get('volume')) and c['volume']>=0 and c['high']>=max(c['open'],c['close']) and c['low']<=min(c['open'],c['close']) and c['high']>=c['low']


def opening_range(candles, start, minutes, now):
    missing = {'available':False, 'reason':'Requires every completed one-minute Kite candle from the official session open.'}
    begins = instant(start)
    if not begins or minutes not in (5,15): return missing
    begins = begins.timestamp()
    end = begins+minutes*60
    if now.timestamp()<end: return missing
    bars = {instant(c['timestamp']).timestamp():c for c in candles if c.get('interval')=='minute' and valid_candle(c) and instant(c.get('timestamp')) and instant(c['timestamp']).timestamp()+60<=now.timestamp()}
    initial = [bars.get(begins+i*60) for i in range(minutes)]
    if any(c is None for c in initial): return missing
    high, low = max(c['high'] for c in initial), min(c['low'] for c in initial)
    after, cursor = [], end
    while cursor in bars and cursor+60<=now.timestamp():
        after.append(bars[cursor]); cursor+=60
    last = after[-1] if after else None
    above = any(c['close']>high for c in after[:-1]); below = any(c['close']<low for c in after[:-1])
    return {'available':True, 'high':high, 'low':low, 'through':datetime.fromtimestamp(end,timezone.utc).isoformat(),
            'breakout':last['close']>high if last else None, 'breakdown':last['close']<low if last else None,
            'failed_breakout':above and low<=last['close']<=high if last else None, 'failed_breakdown':below and low<=last['close']<=high if last else None,
            'retest':(above and last['low']<=high and last['close']>=high or below and last['high']>=low and last['close']<=low) if last else None,
            'event_through':last['timestamp'] if last else None}


def opening(row, context=None, session=None, now=None):
    context, session, now = context or {}, session or {}, now or datetime.now(timezone.utc)
    gap_pct, at = gap(row), instant(row.get('quote_timestamp'))
    same_session = at is not None and row.get('opening_date')==at.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat()
    fill = clamp((row['open']-row['ltp'])/(row['open']-row['prev_close'])*100,0,100) if gap_pct not in (None,0) and positive(row.get('ltp')) and same_session else 0 if gap_pct==0 else None
    good_vwap = positive(row.get('vwap')) and positive(row.get('volume')) and row.get('vwap_source')=='Kite average traded price'
    range_valid = positive(row.get('day_high')) and positive(row.get('day_low')) and row['day_high']>row['day_low'] and positive(row.get('ltp')) and row['day_low']<=row['ltp']<=row['day_high']
    previous = next((c for c in context.get('daily',[]) if c.get('interval')=='day' and valid_candle(c) and c['timestamp'][:10]==context.get('previous_session_date')),None) if context.get('session_date')==row.get('opening_date') else None
    start = f"{row['opening_date']}T{session['opening_time']}+05:30" if session.get('calendar_verified') and session.get('is_trading_day') and session.get('trading_date')==row.get('opening_date') else None
    ranges = {'five':opening_range(context.get('minutes',[]),start,5,now), 'fifteen':opening_range(context.get('minutes',[]),start,15,now)}
    begins = instant(start)
    bars = sorted([c for c in context.get('minutes',[]) if begins and c.get('interval')=='minute' and valid_candle(c) and instant(c.get('timestamp')) and begins<=instant(c['timestamp']) and instant(c['timestamp']).timestamp()+60<=now.timestamp()],key=lambda c:c['timestamp'])
    recent = bars[-4:]
    continuous = len(recent)>=3 and all((instant(recent[i]['timestamp'])-instant(recent[i-1]['timestamp'])).total_seconds()==60 for i in range(1,len(recent)))
    structure = 'Unavailable — complete consecutive candles required'
    if continuous:
        last = recent[-3:]
        if all(last[i]['high']>last[i-1]['high'] and last[i]['low']>last[i-1]['low'] for i in [1,2]): structure='Higher highs and higher lows'
        elif all(last[i]['high']<last[i-1]['high'] and last[i]['low']<last[i-1]['low'] for i in [1,2]): structure='Lower highs and lower lows'
        elif (max(c['high'] for c in last)/min(c['low'] for c in last)-1)*100<=.3: structure='Consolidation (three-candle range ≤0.3%)'
        else: structure='Mixed completed-candle structure'
    spread = row['best_ask']-row['best_bid'] if positive(row.get('best_bid')) and positive(row.get('best_ask')) and row['best_ask']>=row['best_bid'] else None
    quantities = [row.get('depth_bid_quantity'), row.get('depth_ask_quantity')]
    imbalance = (quantities[0]-quantities[1])/sum(quantities) if all(finite(v) and v>=0 for v in quantities) and sum(quantities)>0 else None
    return {'gap_pct':gap_pct, 'opening_class':'Unavailable' if gap_pct is None else 'Flat opening' if gap_pct==0 else 'Gap up' if gap_pct>0 else 'Gap down', 'gap_fill_pct':fill,
            'vwap':row['vwap'] if good_vwap else None, 'vwap_distance_pct':(row['ltp']/row['vwap']-1)*100 if good_vwap and positive(row.get('ltp')) else None,
            'range_position':(row['ltp']-row['day_low'])/(row['day_high']-row['day_low'])*100 if range_valid else None,
            'previous_high':previous['high'] if previous else None, 'previous_low':previous['low'] if previous else None,
            'previous_high_breakout':row['ltp']>previous['high'] if previous and positive(row.get('ltp')) else None,
            'previous_low_breakdown':row['ltp']<previous['low'] if previous and positive(row.get('ltp')) else None,
            'ranges':ranges, 'structure':structure, 'range_expansion':recent[-1]['high']-recent[-1]['low']>1.5*median([c['high']-c['low'] for c in recent[:-1]]) if continuous and len(recent)==4 else None,
            'spread':spread, 'spread_pct':spread/((row['best_bid']+row['best_ask'])/2)*100 if spread is not None else None,
            'depth_imbalance':imbalance, 'relative_volume':None, 'relative_volume_reason':'No licensed comparable same-time historical volume baseline loaded.'}


class Analytics:
    def __init__(self):
        self.lock = threading.RLock(); self.samples = {}; self.volumes = {}; self.transport = None; self.benchmark = None

    def volume(self, row):
        symbol, at = row['symbol'], instant(row.get('quote_timestamp'))
        previous = self.samples.get(symbol)
        missing = {'rate':None,'rate_ratio':None,'acceleration':None,'momentum':None,'momentum_acceleration':None,'reason':'Needs fresh, ordered observations with comparable uninterrupted windows.'}
        if row.get('quote_status')!='live' or at is None or not finite(row.get('volume')) or row['volume']<0:
            self.samples.pop(symbol,None); self.volumes[symbol]=missing; return missing
        if previous and at<=previous['at']: return self.volumes.get(symbol,missing)
        elapsed = (at-previous['at']).total_seconds() if previous else None
        result = missing
        if previous and 5<=elapsed<=90 and at.astimezone(ZoneInfo('Asia/Kolkata')).date()==previous['at'].astimezone(ZoneInfo('Asia/Kolkata')).date() and row['volume']>=previous['volume']:
            rate = (row['volume']-previous['volume'])/elapsed*60
            momentum = (row['ltp']/previous['price']-1)*100/elapsed*60 if positive(row.get('ltp')) and positive(previous['price']) else None
            result = {'rate':rate,'rate_ratio':rate/previous['rate'] if positive(previous['rate']) else None,
                      'acceleration':rate-previous['rate'] if finite(previous['rate']) else None,'momentum':momentum,
                      'momentum_acceleration':momentum-previous['momentum'] if finite(momentum) and finite(previous['momentum']) else None,
                      'reason':'Consecutive observed windows; not historical relative volume.'}
        elif previous and elapsed<5: return self.volumes.get(symbol,missing)
        self.samples[symbol]={'at':at,'volume':row['volume'],'price':row.get('ltp'),'rate':result['rate'],'momentum':result['momentum']}
        self.volumes[symbol]=result
        return result

    def build(self, groups, snapshot, contexts=None, weights=None, benchmark=None):
        with self.lock:
            weights = {**DEFAULT_WEIGHTS, **(weights or {})}
            if any(not finite(v) or not 0<=v<=100 for v in weights.values()) or not any(weights.values()): raise ValueError('Invalid relevance weights.')
            rows = snapshot['rows']; sectors = [sector_metrics(g,rows) for g in groups]
            analyses = {r['symbol']:opening(r,(contexts or {}).get(r['symbol']),snapshot['market']) for r in rows}
            volumes=self.volumes if self.transport==snapshot.get('transport') else {}
            opportunities = [opportunity(r,groups,sectors,analyses[r['symbol']],volumes.get(r['symbol'],{}),weights) for r in rows]
            market_regime=regime(groups,rows,benchmark or self.benchmark)
            for sector in sectors:
                constituents=[r for r in rows if any('NSE:'+s[0]==r['symbol'] for s in next(g for g in groups if g['id']==sector['id'])['stocks'])]
                sector.update(exact=sum(bool(r.get('match')) for r in constituents),near=sum(bool(r.get('near_match')) for r in constituents))
            return {'sectors':sectors,'regime':market_regime,'opening':analyses,'volumes':dict(volumes),'opportunities':opportunities,
                    'summary':{'tracked':len({'NSE:'+s[0] for g in groups for s in g['stocks']}),'memberships':160,
                               'exact':sum(bool(r.get('match')) for r in rows),'near':sum(bool(r.get('near_match')) for r in rows),
                               'advancing':sum(finite(r.get('change_pct')) and r['change_pct']>0 for r in rows),
                               'declining':sum(finite(r.get('change_pct')) and r['change_pct']<0 for r in rows),
                               'live':sum(r.get('quote_status')=='live' for r in rows),'stale':sum(r.get('quote_status')=='stale' for r in rows),'average':market_regime['average'],'available':sum(positive(r.get('ltp')) for r in rows)}}

    def observe_snapshot(self,snapshot):
        """Called by one server sampling job, never by a client request."""
        with self.lock:
            if self.transport!=snapshot.get('transport'):
                self.samples.clear();self.volumes.clear();self.transport=snapshot.get('transport')
            for row in snapshot['rows']:
                value=self.volume(row)
                value['as_of']=row.get('quote_timestamp')


def opportunity(row, groups, sectors, analysis, volume, weights):
    baskets = [g for g in groups if any('NSE:'+s[0]==row['symbol'] for s in g['stocks'])]
    valid_sectors = [s for s in sectors if s['id'] in {g['id'] for g in baskets} and s['available']/s['total']>=.6 and s['breadth'] is not None]
    direction = (1 if row['change_pct']>0 else -1) if finite(row.get('change_pct')) and row['change_pct'] else None
    factors, supporting, contradictory, unavailable = {}, [], [], []
    if row.get('match'): factors['opening']=1; supporting.append('Original exact opening match (₹0 difference).')
    elif row.get('near_match'): factors['opening']=.7; supporting.append('Original near opening match within the configured absolute difference.')
    elif analysis['gap_pct'] is not None:
        factors['opening']=.5 if direction and (1 if analysis['gap_pct']>0 else -1 if analysis['gap_pct']<0 else 0)==direction else 0
        contradictory.append('Opening is outside the original exact/near match conditions.')
    else: unavailable.append('Official opening reference unavailable.')
    if valid_sectors and direction:
        aligned = sum(s['breadth'] if direction>0 else s['declining']/s['available'] for s in valid_sectors)/len(valid_sectors)
        factors['sector']=aligned
        (supporting if aligned>=.6 else contradictory).append('At least 60% of observed sector constituents align with this stock’s direction.' if aligned>=.6 else 'Sector participation is weak or opposes the observed stock direction.')
    else: unavailable.append('Sufficient sector coverage or directional movement unavailable.')
    if analysis['vwap_distance_pct'] is not None and direction:
        factors['price']=1 if (1 if analysis['vwap_distance_pct']>0 else -1 if analysis['vwap_distance_pct']<0 else 0)==direction else 0
        (supporting if factors['price'] else contradictory).append('Price is on the directionally aligned side of provider VWAP.' if factors['price'] else 'Price is on the opposing side of provider VWAP.')
    elif direction and analysis['ranges']['fifteen']['available'] and analysis['ranges']['fifteen']['breakout'] is not None:
        factors['price']=int(analysis['ranges']['fifteen']['breakout'] if direction>0 else analysis['ranges']['fifteen']['breakdown'])
        (supporting if factors['price'] else contradictory).append('Completed 15-minute opening-range price confirmation.' if factors['price'] else 'No aligned completed-candle opening-range confirmation.')
    else: unavailable.append('Valid VWAP or completed-candle price confirmation unavailable.')
    if finite(volume.get('rate_ratio')):
        factors['volume']=min(1,volume['rate_ratio']/2) if volume['rate_ratio']>=1.5 else 0
        (supporting if factors['volume'] else contradictory).append('Observed-window volume rate increased at least 1.5×; this is not historical RVOL.' if factors['volume'] else 'Observed-window volume rate does not confirm acceleration.')
    else: unavailable.append('Consecutive fresh volume windows unavailable.')
    if analysis['spread_pct'] is not None:
        spread = analysis['spread_pct']; factors['liquidity']=1 if spread<=.25 else (1-spread)/.75 if spread<1 else 0
        (contradictory if spread>.5 else supporting).append('Wide supplied bid/ask spread reduces liquidity quality.' if spread>.5 else 'Supplied bid/ask spread is no wider than 0.5%.')
    else: unavailable.append('Valid bid/ask spread unavailable; liquidity cannot be confirmed.')
    factors['freshness']=int(row.get('quote_status')=='live')
    (supporting if factors['freshness'] else contradictory).append('Provider timestamp passes the server freshness check.' if factors['freshness'] else f"Quote status is {row.get('quote_status') or 'unknown'}; fresh confirmation is absent.")
    if any(r.get('failed_breakout') or r.get('failed_breakdown') for r in analysis['ranges'].values()):
        factors['price']=0; contradictory.append('A completed-candle opening-range break failed.')
    total = sum(weights.values()); earned = sum(value*weights[key] for key,value in factors.items())
    return {'symbol':row['symbol'],'sectors':[g['name'] for g in baskets],'sector_strength':sum(s['strength'] for s in valid_sectors)/len(valid_sectors) if valid_sectors else None,
            'ltp':row.get('ltp'),'difference':row.get('difference'),'gap_pct':analysis['gap_pct'],'score':math.floor(earned/total*100+.5) if positive(row.get('ltp')) else None,
            'coverage':sum(weights[k] for k in factors)/total*100,'quality':row.get('quote_status') or 'unavailable',
            'supporting':supporting,'contradictory':contradictory,'unavailable':unavailable,'factors':factors,
            'explanation':f'{len(supporting)} supporting, {len(contradictory)} contradictory and {len(unavailable)} unavailable observations. Missing factors contribute zero; weights are never redistributed. Relevance is not probability of profit.'}


analytics = Analytics()
