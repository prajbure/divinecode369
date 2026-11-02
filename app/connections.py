"""One backend owner for provider authorization, refresh scheduling and health."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import logging
import random
import threading
import time
from zoneinfo import ZoneInfo
from . import config,provider
from .ipo_service import freshness
from .session_vault import SessionVault,VaultError
from .logging_filters import remember_secret

IST=ZoneInfo('Asia/Kolkata')
log=logging.getLogger('divine.connections')


def utcnow():return datetime.now(timezone.utc)
def iso(value):return value.isoformat() if value else None
def as_date(value):
    try:
        result=datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (ValueError,TypeError):return None


class KiteSessions:
    def __init__(self,vault=None,validator=None,clock=None):
        self.vault=vault or SessionVault(config.KITE_SESSION_PATH,config.KITE_API_KEY)
        self.validator=validator or provider.validate_session
        self.clock=clock or utcnow
        self.lock=threading.RLock()
        self.token=None
        self.authentication='unknown'
        self.network='unknown'
        self.last_authenticated=None
        self.last_validated=None
        self.expires_at=None
        self.last_error=None
        self.persistence='not_saved'
        self.generation=0
        self.failures=0
        self.next_check=0.0
        self.loaded=False
        self.candidate=None

    def is_valid(self):
        with self.lock:
            return self.authentication=='valid' and bool(self.token) and (self.expires_at is None or self.clock()<self.expires_at)

    def _save(self):
        try:
            self.vault.save({'token':self.token,'authenticated_at':self.last_authenticated,'expires_at':iso(self.expires_at)})
            self.persistence='encrypted'
        except (VaultError,OSError):
            self.persistence='memory_only'
            self.last_error='Session is active in memory; encrypted persistence is unavailable. A restart will require login.'

    def accept(self,token):
        if not isinstance(token,str) or not token or len(token)>8192:raise ValueError('Kite returned an invalid access token.')
        with self.lock:
            now=self.clock()
            self.generation+=1;self.token=token;self.candidate=token;self.loaded=True
            remember_secret(token)
            self.authentication='valid';self.network='reachable'
            self.last_authenticated=iso(now);self.last_validated=iso(now)
            tomorrow=now.astimezone(IST).date()+timedelta(days=1)
            self.expires_at=datetime.combine(tomorrow,datetime.min.time(),IST).replace(hour=6).astimezone(timezone.utc)
            self.last_error=None;self.failures=0;self.next_check=0
            config.set_kite_access_token(token)
            self._save()
            log.info('provider=kite event=authenticated persistence=%s',self.persistence)

    def load(self):
        with self.lock:
            if self.loaded:return
            self.loaded=True
            if not config.KITE_API_KEY or not config.KITE_API_SECRET:
                self.authentication='key_missing';return
            try:record=self.vault.load()
            except (VaultError,OSError):
                self.last_error='Saved session could not be unlocked. Use official Kite login.'
                self.authentication='login_required';config.set_kite_access_token('');return
            if record and record.get('disconnected'):
                self.authentication='disconnected';config.set_kite_access_token('');return
            token=record.get('token') if record else config.KITE_ACCESS_TOKEN
            self.last_authenticated=record.get('authenticated_at') if record else None
            self.expires_at=as_date(record.get('expires_at')) if record else None
            self.candidate=token if isinstance(token,str) else None
            remember_secret(self.candidate)
            config.set_kite_access_token('')
            if not self.candidate:self.authentication='login_required';return
            if self.expires_at and self.clock()>=self.expires_at:
                self.authentication='expired';self.candidate=None;self.last_error='Kite session expired. Official daily login is required.'
                return
            self.authentication='unverified'

    def validate(self):
        self.load()
        with self.lock:
            candidate=self.token or self.candidate
            if not candidate or self.authentication in ('expired','disconnected','key_missing','login_required'):return False
            generation=self.generation
            if self.expires_at and self.clock()>=self.expires_at:
                self.invalidate('Kite session expired. Official daily login is required.');return False
        try:self.validator(candidate)
        except provider.ProviderError as error:
            with self.lock:
                if generation!=self.generation:return False
                if error.code=='authentication_failed':self.invalidate('Kite rejected the saved session. Official login is required.')
                else:
                    self.network='rate_limited' if error.code=='rate_limited' else 'unreachable'
                    self.last_error='Kite validation rate limited.' if self.network=='rate_limited' else 'Kite validation is temporarily unavailable; recovery is deferred.'
                    self.failures+=1
                    self.next_check=time.monotonic()+min(900,15*2**min(self.failures-1,6))+random.uniform(0,3)
            return False
        except Exception:
            with self.lock:
                self.network='unreachable';self.last_error='Kite verification is temporarily unavailable.'
                self.failures+=1;self.next_check=time.monotonic()+60
            return False
        with self.lock:
            if generation!=self.generation:return False
            self.token=candidate;self.authentication='valid';self.network='reachable'
            self.last_validated=iso(self.clock());self.last_error=None;self.failures=0
            if self.expires_at is None:
                now=self.clock().astimezone(IST)
                boundary=now.replace(hour=6,minute=0,second=0,microsecond=0)
                self.expires_at=(boundary if now<boundary else boundary+timedelta(days=1)).astimezone(timezone.utc)
            config.set_kite_access_token(candidate)
            self._save()
            log.info('provider=kite event=session_validated')
            return True

    def invalidate(self,message):
        with self.lock:
            self.generation+=1;self.authentication='expired';self.token=None;self.candidate=None
            self.last_error=message;config.set_kite_access_token('')
            try:self.vault.disconnect()
            except (VaultError,OSError):self.last_error+=' Protected session cleanup needs attention.'
            log.info('provider=kite event=login_required')

    def disconnect(self):
        with self.lock:
            token=self.token or self.candidate or config.KITE_ACCESS_TOKEN
            self.generation+=1;self.token=None;self.candidate=None;self.authentication='disconnected';self.network='unknown'
            self.last_error=None;self.loaded=True;config.set_kite_access_token('')
            # Persist a tombstone so an old environment token cannot silently reconnect.
            self.vault.disconnect()
            self.persistence='cleared'
            log.info('provider=kite event=disconnected')
            return token

    def public(self):
        with self.lock:
            auth='expired' if self.authentication=='valid' and self.expires_at and self.clock()>=self.expires_at else self.authentication
            state='api_key_missing' if auth=='key_missing' or not config.KITE_API_KEY or not config.KITE_API_SECRET else 'expired' if auth=='expired' else 'disconnected' if auth=='disconnected' else 'degraded' if auth=='unverified' and self.network=='unreachable' else 'login_required' if auth in ('unknown','unverified','login_required') else 'rate_limited' if self.network=='rate_limited' else 'degraded' if self.network!='reachable' or self.persistence=='memory_only' else 'connected'
            return {'state':state,'authentication':auth,'network':self.network,'last_authenticated':self.last_authenticated,
                    'last_validated':self.last_validated,'expires_at':iso(self.expires_at),'last_error':self.last_error,
                    'persistence':self.persistence,'retry_after':max(0,round(self.next_check-time.monotonic()))}


class ConnectionManager:
    def __init__(self,market,ipo_service,kite=None):
        self.market=market;self.ipo=ipo_service;self.kite=kite or KiteSessions()
        self.lock=threading.RLock();self.stop_event=threading.Event();self.wake=threading.Event();self.threads=[]
        self.overview=None;self.ipo_generation=0;self.ipo_next=0.;self.subscription_interest={};self.ipo_failures=0
        self.market.authorization=self.kite.is_valid
        self.market.on_provider_error=self.market_error

    def start(self):
        with self.lock:
            if any(t.is_alive() for t in self.threads):return
            self.stop_event.clear();self.kite.load()
            self.threads=[threading.Thread(target=self._kite_loop,name='divine-kite-session',daemon=True),threading.Thread(target=self._ipo_loop,name='divine-ipo-scheduler',daemon=True)]
            for thread in self.threads:thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        with self.kite.lock:self.kite.generation+=1
        for thread in self.threads:thread.join(timeout=3)

    def _kite_loop(self):
        while not self.stop_event.is_set():
            if time.monotonic()>=self.kite.next_check:
                self.kite.validate()
                if self.kite.is_valid():
                    self.kite.next_check=time.monotonic()+(900 if self.market.snapshot()['market']['is_open'] else 3600)
                elif self.kite.authentication in ('expired','disconnected','key_missing','login_required'):
                    self.kite.next_check=time.monotonic()+3600
            self.stop_event.wait(2)

    def refresh_ipo(self):
        client=self.ipo.client
        if not client.configured or client.auth_failed:
            self.ipo_next=time.monotonic()+3600
            return False
        try:
            result=self.ipo.overview()
            if self.stop_event.is_set():return False
            with self.lock:
                self.overview=result;self.ipo_generation+=1
            errors=[m.get('error') for m in (result.get('meta',{}),result.get('gmp_meta',{})) if m.get('error')]
            if errors:
                self.ipo_failures+=1
                delay=max(60,client.status()['retry_after'],min(900,15*2**min(self.ipo_failures-1,6)))
            else:
                self.ipo_failures=0
                status=client.status();delay=max(client.ttl,3600 if status.get('quota') and status['quota']['remaining']<20 else 0)
                log.info('provider=ipoguru event=shared_refresh cache_seconds=%s',delay)
            # Refresh only recently viewed current-subscription resources, capped per cycle.
            now=time.monotonic()
            with self.lock:
                self.subscription_interest={slug:at for slug,at in self.subscription_interest.items() if now-at<1800}
                active=list(self.subscription_interest)[:3]
            if not errors:
                for slug in active:
                    if self.stop_event.is_set():break
                    self.ipo.resource(slug,'subscription')
            self.ipo_next=time.monotonic()+delay+random.uniform(0,min(15,delay*.05))
            return not errors
        except Exception:
            self.ipo_failures+=1;self.ipo_next=time.monotonic()+min(900,30*2**min(self.ipo_failures-1,5))
            log.warning('provider=ipoguru event=refresh_unavailable')
            return False

    def _ipo_loop(self):
        while not self.stop_event.is_set():
            if time.monotonic()>=self.ipo_next:self.refresh_ipo()
            self.wake.wait(2);self.wake.clear()

    def get_overview(self):
        with self.lock:result=deepcopy(self.overview)
        if result is None:
            return {'rows':[],'counts':{k:None for k in ('open','upcoming','closed','allotment','listings','listed','mainboard','sme')},
                    'meta':{'available':False,'error':{'code':'initializing' if self.ipo.client.configured else 'disabled','message':'IPO Guru is initializing automatically.' if self.ipo.client.configured else 'Configure the backend IPO Guru key and enable the integration.'}},
                    'gmp_meta':{},'provider':self.ipo.client.status(),'coverage':'Shared provider calendar. No fabricated IPO records.'}
        for row in result['rows']:row['gmp']['freshness']=freshness(row['gmp']['freshness']['as_of'])
        for key in ('meta','gmp_meta'):
            meta=result[key];stamp=as_date(meta.get('fetched_at'))
            if stamp:
                meta['cache_age_seconds']=max(0,round((utcnow()-stamp).total_seconds()))
                meta['cache_stale']=meta.get('cache_stale',False) or meta['cache_age_seconds']>self.ipo.client.ttl
        result['provider']=self.ipo.client.status()
        result['next_refresh_seconds']=max(0,round(self.ipo_next-time.monotonic()))
        return result

    def interest(self,slug,kind):
        if kind=='subscription':
            with self.lock:self.subscription_interest[slug]=time.monotonic()

    def accept_kite(self,token):
        self.kite.accept(token);self.market.reset_session();self.kite.next_check=time.monotonic()+900

    def market_error(self,error):
        if error.code=='authentication_failed':self.kite.invalidate('Kite session expired or was revoked. Official login is required.');self.market.close_stream()

    def disconnect_kite(self):
        try:token=self.kite.disconnect()
        finally:self.market.reset_session()
        if token:
            try:provider.revoke_session(token)
            except provider.ProviderError:self.kite.last_error='Local session cleared. Provider logout could not be confirmed.'

    def snapshot(self):
        market=self.market.snapshot();kite=self.kite.public();ipo=self.ipo.client.status();overview=self.get_overview()
        rows=market['rows'];stale=sum(r.get('quote_status')=='stale' for r in rows)
        kite.update({'name':'Zerodha Kite','last_data_update':market['as_of'],'last_tick':market['last_received_tick'],
                     'websocket_connected':market['stream_connected'],'active_subscriptions':market['active_subscriptions'],
                     'stale_instruments':stale,'unavailable_instruments':max(0,148-len(rows)),
                     'freshness':'unavailable' if not rows else 'closed' if not market['market']['is_open'] else 'stale' if stale or market['error'] else 'recent',
                     'last_error':kite['last_error'] or market['error'] or market['stream_error']})
        if kite['state']=='connected' and (market['error'] or (market['market']['is_open'] and (not market['stream_connected'] or stale))):kite['state']='degraded'
        if market['error'] and kite['network']=='reachable':kite['network']='degraded'
        if rows and market['market']['is_open'] and not stale and not market['error'] and not any(r.get('quote_status')=='live' for r in rows):kite['freshness']='unknown'
        error=ipo.get('error') or overview.get('meta',{}).get('error')
        account=self.ipo.client.account or {}
        rate_limited=error and (error.get('code') in ('rate_limited','daily_quota_reached') or (error.get('code')=='backoff' and self.ipo.client.failures==0))
        state='api_key_missing' if not self.ipo.client._key else 'disconnected' if not ipo['enabled'] else 'expired' if account.get('lapsed') is True else 'error' if error and error.get('code')=='authentication_failed' else 'rate_limited' if rate_limited else 'degraded' if error or not ipo['verified'] or overview.get('meta',{}).get('cache_stale') else 'connected'
        sources=[r['gmp']['freshness']['as_of'] for r in overview['rows'] if r['gmp']['freshness']['as_of']]
        subscription_times=list(self.ipo.client.subscription_updates.copy().values())
        code=error.get('code') if error else None
        network='unknown' if not ipo['configured'] else 'unreachable' if code=='provider_unavailable' or (code=='backoff' and self.ipo.client.failures>0) else 'reachable' if ipo['verified'] or code in ('authentication_failed','scope_unavailable','not_found','rate_limited','daily_quota_reached','provider_response') else 'unknown'
        ipo.update({'name':'IPO Guru','state':state,'authentication':'valid' if ipo['verified'] else 'invalid' if self.ipo.client.auth_failed else 'unverified',
                    'network':network,
                    'last_authenticated':iso(datetime.fromtimestamp(account['_verified_at'],timezone.utc)) if account.get('_verified_at') else None,
                    'last_data_update':overview.get('meta',{}).get('fetched_at'),'freshness':freshness(max(sources) if sources else None)['status'],
                    'gmp_source_timestamp':max(sources) if sources else None,'subscription_source_timestamp':max(subscription_times) if subscription_times else None,
                    'last_error':error.get('message') if error else None,'cache_stale':overview.get('meta',{}).get('cache_stale',False),
                    'next_refresh_seconds':max(0,round(self.ipo_next-time.monotonic()))})
        return {'kite':kite,'ipoguru':ipo,'market':market['market'],'ipo_generation':self.ipo_generation,
                'summary':'connected' if kite['state']=='connected' and ipo['state']=='connected' else 'attention',
                'as_of':iso(utcnow())}
