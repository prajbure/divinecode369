"""User-owned records only. No provider feed or secret persistence in this store."""
from datetime import datetime, timedelta
import json
import secrets
import threading
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from . import config
from .mobile_auth import database, digest
from .mobile_models import AlertRule, SavedItem

_event_lock=threading.RLock()
_gmp_baselines={}
_stock_conditions={}


def stamp():
    return datetime.now(ZoneInfo('UTC')).isoformat()


def initialize(db):
    for statement in [
        'CREATE TABLE IF NOT EXISTS personal_saved(owner TEXT, kind TEXT, key TEXT, label TEXT NOT NULL, saved INTEGER NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(owner,kind,key))',
        'CREATE TABLE IF NOT EXISTS personal_alerts(owner TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(owner,id))',
        'CREATE TABLE IF NOT EXISTS personal_events(owner TEXT, id TEXT, payload TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(owner,id))',
        'CREATE TABLE IF NOT EXISTS personal_preferences(owner TEXT PRIMARY KEY, payload TEXT NOT NULL)']:
        db.execute(statement)


def saved_items(owner):
    with database() as db:
        initialize(db)
        rows = db.execute('SELECT * FROM personal_saved WHERE owner=? ORDER BY updated DESC', (owner,)).fetchall()
    return {'items': [{'kind': r['kind'], 'key': r['key'], 'label': r['label'], 'saved': bool(r['saved']), 'updated_at': r['updated']} for r in rows], 'updated_at': stamp()}


def save_item(owner, body: SavedItem):
    from .scanner import reference_groups
    approved = {'NSE:' + s[0] for g in reference_groups() for s in g['stocks']}
    if body.kind == 'stock' and body.key not in approved:
        raise HTTPException(422, 'Choose an approved instrument.')
    if body.kind == 'ipo':
        import re
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', body.key):
            raise HTTPException(422, 'Invalid IPO identifier.')
    with database() as db:
        initialize(db)
        count = db.execute('SELECT COUNT(*) FROM personal_saved WHERE owner=? AND saved=1', (owner,)).fetchone()[0]
        existing = db.execute('SELECT saved FROM personal_saved WHERE owner=? AND kind=? AND key=?', (owner, body.kind, body.key)).fetchone()
        if not existing and db.execute('SELECT COUNT(*) FROM personal_saved WHERE owner=?',(owner,)).fetchone()[0]>=1000:
            raise HTTPException(409,'Saved instrument history limit reached.')
        if body.saved and count >= 500 and not (existing and existing['saved']):
            raise HTTPException(409, 'Watchlist limit reached.')
        db.execute('INSERT OR REPLACE INTO personal_saved VALUES(?,?,?,?,?,?)', (owner, body.kind, body.key, body.label, int(body.saved), stamp()))
    return saved_items(owner)


def rules(owner):
    with database() as db:
        initialize(db)
        rows = db.execute('SELECT payload FROM personal_alerts WHERE owner=?', (owner,)).fetchall()
    return {'items': [json.loads(r['payload']) for r in rows], 'delivery': 'inbox'}


def save_rule(owner, body: AlertRule):
    if (body.event.endswith('_threshold') or body.event in ('gmp_change','price_above','price_below')) and body.threshold is None:
        raise HTTPException(422, 'A threshold is required.')
    if body.kind=='stock':
        from .scanner import reference_groups
        if body.symbol not in {'NSE:'+s[0] for g in reference_groups() for s in g['stocks']}:
            raise HTTPException(422,'Choose an approved instrument.')
    body.id = body.id or secrets.token_hex(12)
    with database() as db:
        initialize(db)
        if db.execute('SELECT COUNT(*) FROM personal_alerts WHERE owner=?', (owner,)).fetchone()[0] >= 100 and not db.execute('SELECT 1 FROM personal_alerts WHERE owner=? AND id=?', (owner, body.id)).fetchone():
            raise HTTPException(409, 'Alert limit reached.')
        db.execute('INSERT OR REPLACE INTO personal_alerts VALUES(?,?,?)', (owner, body.id, body.model_dump_json()))
    return rules(owner)


def delete_rule(owner, rule_id):
    with database() as db:
        initialize(db)
        row=db.execute('SELECT payload FROM personal_alerts WHERE owner=? AND id=?',(owner,rule_id)).fetchone()
        if row:
            payload={**json.loads(row['payload']),'deleted':True,'enabled':False}
            db.execute('UPDATE personal_alerts SET payload=? WHERE owner=? AND id=?',(json.dumps(payload),owner,rule_id))
    return rules(owner)


def inbox(owner):
    with database() as db:
        initialize(db)
        rows = db.execute('SELECT payload FROM personal_events WHERE owner=? ORDER BY created DESC LIMIT 100', (owner,)).fetchall()
    return {'items': [json.loads(r['payload']) for r in rows]}


def preferences(owner, body=None):
    with database() as db:
        initialize(db)
        if body is not None:
            db.execute('INSERT OR REPLACE INTO personal_preferences VALUES(?,?)', (owner, body.model_dump_json()))
        row = db.execute('SELECT payload FROM personal_preferences WHERE owner=?', (owner,)).fetchone()
    return json.loads(row['payload']) if row else {'theme': 'dark', 'density': 'comfortable', 'notifications': False}


def evaluate(overview, now=None, subscriptions=None, market=None):
    """Run once on the backend scheduler, reading its cached overview only."""
    now = now or datetime.now(ZoneInfo(config.APP_TIMEZONE))
    today, tomorrow = now.date().isoformat(), (now.date()+timedelta(days=1)).isoformat()
    by_slug = {r['slug']: r for r in overview.get('rows', [])}
    with _event_lock,database() as db:
        initialize(db)
        active=db.execute('SELECT owner,id,payload FROM personal_alerts').fetchall()
        keys={(r['owner'],r['id']) for r in active}
        for key in list(_gmp_baselines):
            if key not in keys:_gmp_baselines.pop(key,None)
        for key in list(_stock_conditions):
            if key[:2] not in keys or key[2]!=today:_stock_conditions.pop(key,None)
        for row in active:
            rule = json.loads(row['payload'])
            if rule.get('kind')=='stock':
                quote=next((q for q in (market or {}).get('rows',[]) if q['symbol']==rule.get('symbol')),None)
                if not rule['enabled'] or rule.get('deleted') or not quote or quote.get('quote_status')!='live' or not quote.get('quote_timestamp') or not (market or {}).get('market',{}).get('is_open'):
                    continue
                event=rule['event'];price=quote.get('ltp');threshold=rule.get('threshold')
                matched=bool(quote.get('match')) if event=='exact' else bool(quote.get('near_match')) if event=='near' else price is not None and threshold is not None and (price>=threshold if event=='price_above' else price<=threshold)
                key=(row['owner'],row['id'],today);previous=_stock_conditions.get(key,False);_stock_conditions[key]=matched
                if not matched or previous:continue
                source=quote['quote_timestamp'];event_id=digest(row['id']+'\n'+today+'\n'+source)
                payload={'id':event_id,'rule_id':row['id'],'ipo_slug':'','kind':'stock','symbol':quote['symbol'],'event':event,'title':quote['symbol']+' · '+event.replace('_',' '),'created_at':stamp(),'source_timestamp':source}
                db.execute('INSERT OR IGNORE INTO personal_events VALUES(?,?,?,?)',(row['owner'],event_id,json.dumps(payload),payload['created_at']))
                continue
            ipo = by_slug.get(rule['ipo_slug'])
            if not rule['enabled'] or rule.get('deleted') or not ipo:
                continue
            event, timeline, source = rule['event'], ipo['timeline'], None
            matched = {'opens': timeline.get('open_date') == today, 'closes_tomorrow': timeline.get('close_date') == tomorrow,
                       'allotment': timeline.get('allotment_date') == today, 'listing': timeline.get('listing_date') == today}.get(event, False)
            if event == 'gmp_threshold':
                gmp = ipo['gmp']
                source = gmp['freshness'].get('as_of')
                matched = source is not None and gmp['freshness'].get('status') in ('fresh', 'recent') and gmp.get('price') is not None and gmp['price'] >= rule['threshold']
            if event == 'subscription_threshold':
                subscription = (subscriptions or {}).get(ipo['slug'], {})
                freshness = subscription.get('freshness', {})
                source = freshness.get('as_of')
                total = next((c.get('times') for c in subscription.get('categories', []) if (c.get('key') or '').upper() == 'TOTAL'), None)
                matched = source is not None and freshness.get('status') == 'recent' and total is not None and total >= rule['threshold']
            if event == 'gmp_change':
                gmp=ipo['gmp'];source=gmp['freshness'].get('as_of');value=gmp.get('price');key=(row['owner'],row['id'])
                if source and gmp['freshness'].get('status')=='recent' and value is not None:
                    baseline=_gmp_baselines.get(key)
                    matched=baseline is not None and abs(value-baseline)>=rule['threshold'] and value!=baseline
                    if baseline is None or matched:_gmp_baselines[key]=value
            if not matched:
                continue
            event_id = digest(row['id']+'\n'+today+'\n'+event+('\n'+source if event=='gmp_change' and source else ''))
            label={'allotment':'expected allotment date','listing':'scheduled listing day','opens':'scheduled opening','closes_tomorrow':'scheduled close tomorrow','gmp_change':'unofficial GMP change'}.get(event,event.replace('_',' '))
            payload = {'id': event_id, 'rule_id': row['id'], 'ipo_slug': ipo['slug'], 'event': event,
                       'title': ipo['name'] + ' · ' + label, 'created_at': stamp(), 'source_timestamp': source}
            db.execute('INSERT OR IGNORE INTO personal_events VALUES(?,?,?,?)', (row['owner'], event_id, json.dumps(payload), payload['created_at']))
        db.execute('DELETE FROM personal_events WHERE created < ?', ((now.astimezone(ZoneInfo('UTC'))-timedelta(days=30)).isoformat(),))
