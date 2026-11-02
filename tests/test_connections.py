"""Deterministic V2.1 lifecycle tests; credentials and databases are temporary."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock,Mock,patch
from app import config,provider
from app.connections import ConnectionManager,KiteSessions
from app.ipoguru import IPOGuruClient
from app.ipo_service import IPOService
from app.market import MarketService
from app.scanner import reference_groups
from app.session_vault import DPAPI,SessionVault,VaultError
from app.storage import Store
from app.logging_filters import CredentialFilter,remember_secret
from tests.test_ipo import ACCOUNT,IPO,response


class SessionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.settings=patch.multiple(config,KITE_API_KEY='TEST-API',KITE_API_SECRET='TEST-SECRET',KITE_ACCESS_TOKEN='')
        self.settings.start();self.addCleanup(self.settings.stop)
        self.now=[datetime(2026,11,2,12,tzinfo=timezone.utc)]
        self.vault=Mock();self.vault.load.return_value=None
        self.validator=Mock(return_value=True)
        self.sessions=KiteSessions(self.vault,self.validator,lambda:self.now[0])

    def test_a_stored_key_never_means_connected(self):
        self.sessions.load()
        self.assertEqual(self.sessions.public()['state'],'login_required')
        self.assertFalse(self.sessions.is_valid());self.validator.assert_not_called()

    def test_valid_saved_session_restores_only_after_profile_validation(self):
        self.vault.load.return_value={'token':'TEST-TOKEN','authenticated_at':'2026-11-02T05:00:00+00:00','expires_at':'2026-11-03T00:30:00+00:00'}
        self.sessions.load();self.assertEqual(config.KITE_ACCESS_TOKEN,'')
        self.assertTrue(self.sessions.validate());self.validator.assert_called_once_with('TEST-TOKEN')
        self.assertEqual(config.KITE_ACCESS_TOKEN,'TEST-TOKEN');self.assertEqual(self.sessions.public()['state'],'connected')

    def test_expired_saved_session_is_not_retried(self):
        self.vault.load.return_value={'token':'EXPIRED','expires_at':'2026-11-02T00:30:00+00:00'}
        self.assertFalse(self.sessions.validate());self.assertFalse(self.sessions.validate())
        self.assertEqual(self.sessions.public()['state'],'expired');self.validator.assert_not_called()

    def test_revoked_session_requires_login_and_clears_stored_token(self):
        self.vault.load.return_value={'token':'REVOKED'}
        self.validator.side_effect=provider.ProviderError('Rejected',code='authentication_failed')
        self.sessions.validate();self.sessions.validate()
        self.assertEqual(self.validator.call_count,1);self.vault.disconnect.assert_called_once()
        self.assertEqual(config.KITE_ACCESS_TOKEN,'');self.assertEqual(self.sessions.public()['state'],'expired')

    def test_network_outage_is_distinct_from_invalid_authentication(self):
        self.sessions.accept('VALID')
        self.validator.side_effect=provider.ProviderError('Unavailable')
        self.assertFalse(self.sessions.validate())
        status=self.sessions.public();self.assertEqual(status['authentication'],'valid')
        self.assertEqual(status['network'],'unreachable');self.assertEqual(status['state'],'degraded')
        self.assertTrue(self.sessions.is_valid())

    def test_validation_recovery_restores_network_dimension(self):
        self.sessions.accept('VALID');self.validator.side_effect=[provider.ProviderError('offline'),True]
        self.sessions.validate();self.sessions.validate()
        self.assertEqual(self.sessions.public()['state'],'connected')

    def test_daily_expiry_does_not_extend_when_revalidating(self):
        self.sessions.accept('DAILY')
        expiry=self.sessions.expires_at
        self.now[0]+=timedelta(hours=1);self.sessions.validate()
        self.assertEqual(self.sessions.expires_at,expiry)
        self.now[0]=expiry
        self.assertFalse(self.sessions.is_valid());self.assertEqual(self.sessions.public()['state'],'expired')

    def test_manual_disconnect_prevents_environment_token_restoration(self):
        self.sessions.accept('TOKEN');self.sessions.disconnect()
        self.assertEqual(config.KITE_ACCESS_TOKEN,'');self.vault.disconnect.assert_called_once()
        self.vault.load.return_value={'disconnected':True}
        config.set_kite_access_token('OLD-ENV-TOKEN')
        restored=KiteSessions(self.vault,self.validator,lambda:self.now[0]);restored.validate()
        self.assertEqual(config.KITE_ACCESS_TOKEN,'');self.assertEqual(restored.public()['state'],'disconnected')

    def test_disconnect_during_verification_cannot_resurrect_token(self):
        self.vault.load.return_value={'token':'OLD'}
        self.validator.side_effect=lambda token:self.sessions.disconnect()
        self.assertFalse(self.sessions.validate());self.assertIsNone(self.sessions.token)

    def test_public_diagnostics_never_include_access_token(self):
        self.sessions.accept('DO-NOT-EXPOSE')
        self.assertNotIn('DO-NOT-EXPOSE',json.dumps(self.sessions.public()))

    def test_rotated_credentials_and_query_parameters_are_redacted_from_sdk_logs(self):
        remember_secret('OLD-ROTATED-TOKEN')
        record=logging.LogRecord('test',20,'test',1,'Socket error %s',('OLD-ROTATED-TOKEN ?access_token=unknown-value&api_key=TEST-API',),None)
        CredentialFilter().filter(record)
        self.assertNotIn('OLD-ROTATED-TOKEN',record.getMessage());self.assertNotIn('unknown-value',record.getMessage());self.assertNotIn('TEST-API',record.getMessage())

    def test_redaction_preserves_uvicorn_access_formatter_contract(self):
        from uvicorn.logging import AccessFormatter
        record=logging.LogRecord('uvicorn.access',20,'test',1,'%s - "%s %s HTTP/%s" %d',('127.0.0.1','GET','/auth/kite/callback?request_token=PRIVATE','1.1',200),None)
        CredentialFilter().filter(record)
        self.assertEqual(len(record.args),5)
        self.assertNotIn('PRIVATE',AccessFormatter('%(message)s').format(record))

    def test_unavailable_encryption_uses_memory_without_plaintext_fallback(self):
        self.vault.save.side_effect=VaultError('unsupported')
        self.sessions.accept('TOKEN')
        self.assertTrue(self.sessions.is_valid());self.assertEqual(self.sessions.persistence,'memory_only')
        self.assertEqual(self.sessions.public()['state'],'degraded')


class VaultTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows-specific user-bound encryption')
    def test_real_dpapi_roundtrip_and_private_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'private'/'kite-session.bin'
            vault=SessionVault(path,'TEST-PUBLIC-KEY')
            vault.save({'token':'SYNTHETIC-SECRET-FOR-ENCRYPTION-TEST'})
            self.assertNotIn(b'SYNTHETIC-SECRET-FOR-ENCRYPTION-TEST',path.read_bytes())
            self.assertEqual(vault.load()['token'],'SYNTHETIC-SECRET-FOR-ENCRYPTION-TEST')
            with self.assertRaises(VaultError):SessionVault(path,'DIFFERENT-KEY').load()
            vault.disconnect();self.assertTrue(vault.load()['disconnected'])

    def test_unsupported_crypto_never_creates_a_plaintext_token_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session.bin'
            codec=Mock();codec.encrypt.side_effect=VaultError('Unavailable')
            with self.assertRaises(VaultError):SessionVault(path,'TEST',codec=codec).save({'token':'SECRET'})
            self.assertFalse(path.exists())


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.settings=patch.multiple(config,KITE_API_KEY='TEST-API',KITE_API_SECRET='TEST-SECRET',KITE_ACCESS_TOKEN='')
        self.settings.start();self.addCleanup(self.settings.stop)
        store=Store(Path(self.folder.name)/'market.sqlite3');store.initialize(reference_groups())
        self.market=MarketService(store)
        vault=Mock();vault.load.return_value=None
        self.kite=KiteSessions(vault,Mock(return_value=True))
        self.http=Mock();self.http.get.side_effect=[response(ACCOUNT),response([IPO]),response([])]
        client=IPOGuruClient(key='TEST-IPO-KEY',enabled=True,session=self.http,quota_path=Path(self.folder.name)/'quota.sqlite3')
        self.manager=ConnectionManager(self.market,IPOService(client),self.kite)
        self.addCleanup(self.manager.stop)

    def test_automatic_start_is_idempotent_and_initializes_provider(self):
        self.manager.start();self.manager.start()
        for _ in range(100):
            if self.manager.overview is not None:break
            time.sleep(.01)
        self.assertEqual(len(self.manager.threads),2)
        self.assertTrue(self.manager.get_overview()['meta']['available'])
        self.assertEqual(self.http.get.call_count,3)

    def test_many_tabs_read_shared_snapshot_without_provider_calls(self):
        self.assertTrue(self.manager.refresh_ipo())
        with ThreadPoolExecutor(max_workers=8) as pool:
            values=list(pool.map(lambda _:self.manager.get_overview(),range(40)))
        self.assertTrue(all(v['rows'] for v in values));self.assertEqual(self.http.get.call_count,3)

    def test_health_does_not_wait_for_a_slow_ipo_http_request(self):
        entered=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):entered.set();release.wait(3);return response(ACCOUNT)
        self.http.get.side_effect=slow
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.manager.ipo.client.get,'/me','account')
            self.assertTrue(entered.wait(2))
            started=time.monotonic()
            try:self.manager.snapshot()
            finally:release.set()
            self.assertLess(time.monotonic()-started,.5)
            future.result()

    def test_closed_market_is_not_a_disconnected_authenticated_session(self):
        self.kite.accept('VALID')
        self.manager.refresh_ipo()
        with patch('app.market.session_state',return_value={'is_open':False,'status':'closed'}):
            self.assertEqual(self.manager.snapshot()['kite']['state'],'connected')

    def test_invalid_ipo_key_stops_automatic_authentication_retries(self):
        self.http.get.side_effect=[response(status=403)]
        self.manager.refresh_ipo();self.manager.refresh_ipo()
        self.assertEqual(self.http.get.call_count,1)
        self.assertEqual(self.manager.snapshot()['ipoguru']['state'],'error')

    def test_unconfigured_ipo_never_calls_network(self):
        self.manager.ipo.client.enabled=False
        self.manager.refresh_ipo();self.http.get.assert_not_called()

    def test_lapsed_ipo_subscription_is_reported_as_expired(self):
        self.http.get.side_effect=[response({**ACCOUNT,'lapsed':True}),response([IPO]),response([])]
        self.manager.refresh_ipo();self.assertEqual(self.manager.snapshot()['ipoguru']['state'],'expired')

    def test_ipo_rate_limit_is_visible_in_unified_health(self):
        self.http.get.side_effect=[response(ACCOUNT),response(status=429,headers={'Retry-After':'120'},error='rate_limited')]
        self.manager.refresh_ipo();self.assertEqual(self.manager.snapshot()['ipoguru']['state'],'rate_limited')

    def test_data_health_never_contains_either_provider_secret(self):
        self.kite.accept('TEST-KITE-SECRET');self.manager.refresh_ipo()
        value=json.dumps(self.manager.snapshot())
        self.assertNotIn('TEST-IPO-KEY',value);self.assertNotIn('TEST-KITE-SECRET',value)

    def test_repeated_stream_start_and_connect_does_not_duplicate_subscription(self):
        self.kite.accept('VALID')
        self.market.details=[{'symbol':'NSE:HDFCBANK','instrument_token':123,'is_equity':True,'name':'HDFC Bank'}]
        ticker=MagicMock()
        with patch('kiteconnect.KiteTicker',return_value=ticker) as factory:
            self.market._start_stream();self.market._start_stream()
            ticker.on_connect(ticker,None);ticker.on_connect(ticker,None)
            self.assertEqual(factory.call_count,1);ticker.subscribe.assert_called_once_with([123])
            self.assertEqual(self.market.subscription_count,1)
        self.market.close_stream()

    def test_invalidated_session_never_resubscribes(self):
        self.kite.accept('VALID');self.market.details=[{'symbol':'NSE:HDFCBANK','instrument_token':123,'is_equity':True}]
        ticker=MagicMock()
        with patch('kiteconnect.KiteTicker',return_value=ticker):
            self.market._start_stream();self.kite.invalidate('Expired');ticker.on_connect(ticker,None)
        ticker.subscribe.assert_not_called();self.assertFalse(self.market.stream_connected)

    def test_disconnect_clears_saved_session_and_feed_even_if_network_logout_fails(self):
        self.kite.accept('VALID');ticker=MagicMock();self.market.ticker=ticker
        with patch('app.provider.revoke_session',side_effect=provider.ProviderError('offline')):self.manager.disconnect_kite()
        self.kite.vault.disconnect.assert_called_once();self.assertIsNone(self.market.ticker)
        self.assertEqual(config.KITE_ACCESS_TOKEN,'');self.assertEqual(self.kite.public()['state'],'disconnected')

    def test_rest_call_with_invalid_auth_is_blocked_before_provider(self):
        with patch('app.provider.live_quotes') as quotes:
            with self.assertRaises(provider.ProviderError):self.market.refresh()
        quotes.assert_not_called()

    def test_late_rest_response_after_disconnect_is_not_ingested(self):
        self.kite.accept('VALID');self.market.details=[{'symbol':'NSE:HDFCBANK','is_equity':True}]
        def delayed(symbols):self.manager.disconnect_kite();return {'data':[{'symbol':'HDFCBANK','ltp':123}]}
        with patch('app.provider.live_quotes',side_effect=delayed),patch('app.provider.revoke_session'):
            self.market.refresh()
        self.assertEqual(self.market.rows,{})

    def test_unauthorized_cached_quote_cannot_be_labelled_live(self):
        self.market.rows={'NSE:HDFCBANK':{'symbol':'NSE:HDFCBANK','ltp':100,'change_pct':1,'quote_timestamp':datetime.now(timezone.utc).isoformat()}}
        with patch('app.market.session_state',return_value={'is_open':True,'status':'open'}):
            self.assertEqual(self.market.snapshot()['rows'][0]['quote_status'],'stale')

    def test_tick_in_flight_during_logout_is_not_ingested(self):
        self.kite.accept('VALID');self.market.details=[{'symbol':'NSE:HDFCBANK','instrument_token':123,'is_equity':True,'name':'HDFC Bank'}]
        ticker=MagicMock()
        def normalize(*args,**kwargs):self.kite.disconnect();self.market.close_stream();return {}
        with patch('kiteconnect.KiteTicker',return_value=ticker),patch('app.provider.quote_intelligence',side_effect=normalize):
            self.market._start_stream();ticker.on_ticks(ticker,[{'instrument_token':123,'last_price':123}])
        self.assertEqual(self.market.rows,{})
