"""IPO Guru v2 read-only client. Docs checked 2026-11-02.

Shared memory cache holds permitted 5–15 minute views, not historical retention.
Only quota metadata is persisted, in a separate database. No credentials in errors.
"""
from collections import OrderedDict
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import threading
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import requests
from . import config

STANDARD_SCOPES = frozenset({'calendar','details','details_full','gmp','gmp_history','subscription','anchors'})
IST = ZoneInfo('Asia/Kolkata')


class IPOError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.message, self.retry_after = code, message, retry_after

    def public(self):
        return {'code': self.code, 'message': self.message, 'retry_after': self.retry_after}


class QuotaLedger:
    """Atomically reserve per-key requests across process restarts; no market data."""
    def __init__(self, path, key):
        self.path = path
        self.key = hashlib.sha256(key.encode()).hexdigest()

    def transact(self, now, minute=20, daily=1000, reserve=False, remaining=None):
        day = datetime.fromtimestamp(now, IST).date().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS quota (key TEXT, day TEXT, used INTEGER, remaining INTEGER, PRIMARY KEY(key,day))')
            db.execute('CREATE TABLE IF NOT EXISTS requests (key TEXT, at REAL)')
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM requests WHERE at <= ?', (now-60,))
            db.execute('DELETE FROM quota WHERE day < ?', (day,))
            row = db.execute('SELECT used,remaining FROM quota WHERE key=? AND day=?',(self.key,day)).fetchone()
            used, left = row if row else (0, daily)
            left = min(left, max(0, daily-used))
            if remaining is not None:
                left = min(left, max(0, remaining))
            if reserve:
                if used >= daily or left <= 0:
                    raise IPOError('daily_quota_reached','IPO Guru daily budget exhausted; resumes after midnight IST.')
                times = [r[0] for r in db.execute('SELECT at FROM requests WHERE key=? ORDER BY at',(self.key,))]
                if len(times) >= minute:
                    raise IPOError('rate_limited','IPO Guru request window is full.', max(1, int(61-(now-times[0]))))
                db.execute('INSERT INTO requests VALUES (?,?)', (self.key,now))
                used, left = used+1, left-1
            db.execute('INSERT OR REPLACE INTO quota VALUES (?,?,?,?)',(self.key,day,used,left))
            return {'local_requests_today':used, 'remaining':left, 'reset':'Midnight Asia/Kolkata'}


class IPOGuruClient:
    def __init__(self, *, key=None, enabled=None, base_url=None, ttl=None, quota_path=None, session=None, clock=None):
        self._key = config.IPOGURU_API_KEY if key is None else key
        self.enabled = config.IPOGURU_ENABLED if enabled is None else enabled
        self.base = config.IPOGURU_BASE_URL if base_url is None else base_url
        self.ttl = max(300, ttl or config.IPOGURU_CACHE_SECONDS)
        self.session = session or requests.Session()
        self.clock = clock or time.time
        self.ledger = QuotaLedger(quota_path or config.IPOGURU_QUOTA_PATH, self._key)
        self.lock = threading.RLock()
        self.cache = OrderedDict()
        self.account = None
        self.auth_failed = False
        self.blocked = set()
        self.last_error = None
        self.next_request = 0
        self.failures = 0
        self.daily_limit, self.minute_limit = 1000, 20
        self._quota = None
        self._day = None
        self.subscription_updates = {}

    @property
    def configured(self):
        url = urlsplit(self.base)
        return bool(self.enabled and self._key and url.scheme=='https' and url.netloc=='www.ipoguru.in'
                    and url.path=='/api/v2' and not url.query and not url.fragment)

    def status(self):
        # Metadata references are replaced atomically; never wait on the HTTP/cache
        # lock here. Health/SSE must keep running during a slow provider request.
        account=self.account or {}
        return {'enabled':bool(self.enabled), 'configured':self.configured, 'verified':bool(account) and not self.auth_failed,
                'plan':account.get('plan'),
                'scopes':sorted((set(account.get('scopes',[])) & STANDARD_SCOPES)-self.blocked.copy()),
                'limits':{'per_day':self.daily_limit,'per_minute':self.minute_limit},
                'quota':deepcopy(self._quota), 'error':deepcopy(self.last_error),
                'cache_seconds':self.ttl, 'retry_after':max(0,round(self.next_request-self.clock())),
                'message': 'Configure the backend key and enable IPO Guru to load verified IPO data.' if not self.configured else 'Shared backend cache; automatic refresh is managed by the backend.'}

    def _request(self, path, scope):
        now = self.clock()
        day = datetime.fromtimestamp(now, IST).date().isoformat()
        if self._day != day:
            self._day, self.next_request = day, 0
            self._quota = None
        if self.auth_failed:
            raise IPOError('authentication_failed','IPO Guru authentication failed. Correct the backend key, then verify again.')
        if now < self.next_request:
            raise IPOError('backoff','Provider retry is deferred to protect the request budget.',max(1,round(self.next_request-now)))
        self._quota = self.ledger.transact(now, self.minute_limit if self.account else 1,
                                          self.daily_limit, reserve=True)
        try:
            response = self.session.get(self.base+path, headers={'X-API-KEY':self._key,'Accept':'application/json'},
                                        timeout=(5,15), allow_redirects=False)
        except requests.RequestException:
            self.failures += 1
            delay = min(900, 15 * 2**min(self.failures-1,6))
            self.next_request = now + delay
            raise IPOError('provider_unavailable','IPO Guru is unreachable. Cached values may be shown as stale.',delay) from None
        # Never forward provider messages or transport exceptions: either can echo a key.
        try:
            body = response.json() if len(response.content) <= 2_000_000 else None
        except (ValueError, TypeError):
            body = None
        body = body if isinstance(body,dict) else {}
        remaining = response.headers.get('X-RateLimit-Remaining')
        cap = response.headers.get('X-RateLimit-Limit')
        if str(cap).isdigit():
            self.daily_limit = min(1000,max(1,int(cap)))
        if str(remaining).isdigit():
            self._quota = self.ledger.transact(now,self.minute_limit,self.daily_limit,remaining=int(remaining))
        code = body.get('error')
        if response.status_code in (401,403):
            self.auth_failed = True
            raise IPOError('authentication_failed','IPO Guru rejected the key. Correct backend credentials and verify again.')
        if response.status_code == 402:
            self.blocked.add(scope)
            raise IPOError('scope_unavailable',f'The verified plan does not authorize {scope}. Upgrade or renew access, then verify again.')
        if response.status_code == 429:
            if code == 'daily_quota_reached':
                self._quota = self.ledger.transact(now,self.minute_limit,self.daily_limit,remaining=0)
                raise IPOError('daily_quota_reached','Provider daily quota exhausted; resumes after midnight IST.')
            try:
                delay = max(1,min(86400,int(response.headers.get('Retry-After') or body.get('retry_after') or 60)))
            except (ValueError,TypeError):
                delay = 60
            self.next_request = now + delay
            raise IPOError('rate_limited','IPO Guru burst limit reached; retry is deferred.',delay)
        if response.status_code == 404:
            raise IPOError('not_found','This IPO resource is unavailable from IPO Guru.')
        if response.status_code != 200 or body.get('success') is not True or 'data' not in body:
            self.failures += 1
            delay = min(900,15*2**min(self.failures-1,6))
            self.next_request = now+delay
            raise IPOError('provider_response','IPO Guru returned an unavailable or malformed response.',delay)
        self.failures = 0
        # Also redact accidental reflections from successful payloads before caching.
        return json.loads(json.dumps(body['data']).replace(self._key,'[redacted]'))

    def get(self, path, scope, *, verify=False):
        if not self.configured:
            return {'data':None,'meta':{'available':False,'cache_stale':False,'error':{'code':'disabled','message':'IPO Guru is disabled or missing valid backend configuration.'}}}
        if scope not in STANDARD_SCOPES and path != '/me':
            raise IPOError('scope_unavailable','This endpoint is outside the Standard integration.')
        if not re.fullmatch(r'/me|/ipos|/gmp|/ipos/[a-z0-9]+(?:-[a-z0-9]+)*(?:/gmp/history|/subscription|/anchors)?',path):
            raise IPOError('invalid_resource','Invalid IPO resource.')
        with self.lock:
            now = self.clock()
            if path != '/me' and (not self.account or now-self.account.get('_verified_at',0)>21600):
                account = self.get('/me','account')
                if not account['meta']['available'] or account['meta'].get('error'):
                    return {'data':None,'meta':{**account['meta'],'available':False}}
            if path != '/me' and (scope in self.blocked or scope not in self.account.get('scopes',[])):
                return {'data':None,'meta':{'available':False,'error':{'code':'scope_unavailable','message':f'{scope} is unavailable on the verified plan; access may require an upgrade.'}}}
            cached = self.cache.get(path)
            if self.auth_failed and not verify:
                error=IPOError('authentication_failed','IPO Guru authentication failed. Correct the backend key, then verify again.').public()
                return self._result(cached,True,True,error) if cached else {'data':None,'meta':{'available':False,'error':error}}
            ttl = 21600 if path=='/me' else self.ttl
            if path!='/me' and self._quota and self._quota['remaining']<20:
                ttl=max(ttl,3600)
            if cached and now-cached[0] < ttl and not verify:
                self.cache.move_to_end(path)
                return self._result(cached,False,True)
            if verify:
                self.auth_failed = False
                self.blocked.clear()
            try:
                data = self._request(path,scope)
                if not isinstance(data,list if path in ('/ipos','/gmp') else dict):
                    self.next_request=now+30
                    raise IPOError('provider_response','IPO Guru returned an unexpected resource shape.',30)
                if path=='/me':
                    if not isinstance(data,dict) or not isinstance(data.get('scopes'),list) or not isinstance(data.get('plan'),str):
                        raise IPOError('provider_response','IPO Guru account response is missing plan or scopes.')
                    limits = data.get('limits') if isinstance(data.get('limits'),dict) else {}
                    for field,default in [('per_day',1000),('per_minute',20)]:
                        value = limits.get(field)
                        if isinstance(value,int) and not isinstance(value,bool) and value>0:
                            setattr(self,'daily_limit' if field=='per_day' else 'minute_limit', min(default,value))
                    self.account = {**data,'scopes':[v for v in data['scopes'] if isinstance(v,str)],'_verified_at':now}
                    usage = data.get('usage_today',{})
                    if isinstance(usage,dict) and isinstance(usage.get('remaining'),int):
                        self._quota=self.ledger.transact(now,self.minute_limit,self.daily_limit,remaining=usage['remaining'])
                cached = (now,data)
                self.cache[path] = cached
                if path.endswith('/subscription'):
                    summary=data.get('summary')
                    stamp=summary.get('updated_at') if isinstance(summary,dict) else None
                    if isinstance(stamp,str):self.subscription_updates[path]=stamp
                    while len(self.subscription_updates)>128:self.subscription_updates.pop(next(iter(self.subscription_updates)))
                self.cache.move_to_end(path)
                while len(self.cache)>256:
                    self.cache.popitem(last=False)
                self.last_error = None
                return self._result(cached,False,False)
            except IPOError as error:
                self.last_error = error.public()
                if cached:
                    return self._result(cached,True,True,error.public())
                return {'data':None,'meta':{'available':False,'cache_stale':False,'error':error.public()}}

    def _result(self, cached, stale, hit, error=None):
        return {'data':deepcopy(cached[1]),'meta':{'available':True,'cache_stale':stale,'cache_hit':hit,
                'cache_age_seconds':max(0,round(self.clock()-cached[0])),
                'fetched_at':datetime.fromtimestamp(cached[0],timezone.utc).isoformat(),'error':error}}
