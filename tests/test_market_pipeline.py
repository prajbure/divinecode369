"""Isolated synthetic fixtures exercise the pipeline; never served as market data."""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app import config
from app.market import MarketService, session_state
from app.predictions import PredictionLab, feature_rows
from app.scanner import reference_groups, run_scan
from app.storage import Store

TZ = ZoneInfo(config.APP_TIMEZONE)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.store.initialize(reference_groups())

    def tearDown(self):
        self.tmp.cleanup()


class StorageTests(StoreCase):
    def test_memberships_keep_duplicates_and_suspension(self):
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sector_memberships').fetchone()[0], 160)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM instruments').fetchone()[0], 148)
            self.assertEqual(db.execute("SELECT status FROM instruments WHERE symbol='NSE:TV18BRDCST'").fetchone()[0], 'suspended')

    def test_persistence_deduplication_validation_and_authorization(self):
        bar = {'date':'2025-01-02','open':100,'high':104,'low':99,'close':102,'volume':1000}
        self.store.save_candles('NSE:HDFCBANK',[bar,bar],authorized=True)
        self.assertEqual(len(Store(self.store.path).candles('NSE:HDFCBANK')),1)
        with self.assertRaises(ValueError):
            self.store.save_candles('NSE:HDFCBANK',[bar],authorized=False)
        with self.assertRaises(ValueError):
            self.store.save_candles('NSE:HDFCBANK',[{**bar,'high':90}],authorized=True)
        with self.assertRaises(ValueError):
            self.store.save_candles('NSE:UNAPPROVED',[bar],authorized=True)
        self.assertEqual(self.store.overview()['candles'],1)

    def test_scan_first_open_is_immutable_and_survives_restart(self):
        row={'symbol':'NSE:HDFCBANK','prev_close':100,'open':100,'difference':0,'status':'MATCH'}
        with patch.object(config,'DATA_RETENTION_AUTHORIZED',True):
            self.store.save_scan('2025-01-02',{'as_of':'2025-01-02T10:00:00+05:30','rows':[row]})
            self.store.save_scan('2025-01-02',{'as_of':'2025-01-02T10:01:00+05:30','rows':[{**row,'open':101}]})
            self.assertEqual(Store(self.store.path).opening_anchors('2025-01-02')[0]['opening_price'],100)


class MarketTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.service=MarketService(self.store)
        self.service.details=[{'symbol':'NSE:HDFCBANK','name':'HDFC Bank','is_equity':True}, {'symbol':'NSE:INFY','name':'Infosys','is_equity':True}]

    def quote(self,symbol='HDFCBANK',**changes):
        return {'symbol':symbol,'exchange':'NSE','name':symbol,'open':100,'prev_close':100,'ltp':101,'quote_timestamp':datetime.now(TZ).replace(hour=10,minute=0,second=0,microsecond=0).isoformat(),**changes}

    def test_ticks_update_prices_but_never_recompute_official_open(self):
        # Use a known trading day, rather than yesterday (which may be Sunday).
        stamp=datetime(2026,10,30,tzinfo=TZ)
        stamp=stamp.replace(hour=10,minute=0,second=0,microsecond=0).isoformat()
        with patch('app.market.run_scan',wraps=run_scan) as scan:
            self.service.ingest([self.quote(quote_timestamp=stamp)])
            self.service.ingest([self.quote(open=105,ltp=98,quote_timestamp=stamp)])
            self.assertEqual(scan.call_count,1)
        row=self.service.snapshot()['rows'][0]
        self.assertEqual(row['open'],100)
        self.assertTrue(row['match'])
        self.assertEqual(row['ltp'],98)
        self.assertEqual(row['change_pct'],-2)

    def test_performers_sort_actual_percentage_and_reject_unknown_universe(self):
        stamp=(datetime.now(TZ)-timedelta(days=1)).replace(hour=11).isoformat()
        self.service.ingest([self.quote(ltp=101,quote_timestamp=stamp),self.quote('INFY',ltp=104,quote_timestamp=stamp),self.quote('UNAPPROVED',quote_timestamp=stamp)])
        snap=self.service.snapshot()
        self.assertEqual([r['symbol'] for r in snap['top_performers']],['NSE:INFY','NSE:HDFCBANK'])
        self.assertEqual(len(snap['rows']),2)

    def test_timestamp_missing_is_never_live_or_opening_match(self):
        self.service.ingest([self.quote(quote_timestamp=None)])
        row=self.service.snapshot()['rows'][0]
        self.assertEqual(row['quote_status'],'unknown')
        self.assertFalse(row['match'])
        self.assertIsNone(row['open'])

    def test_stale_and_closed_are_never_live(self):
        now=datetime.now(TZ)
        stamp=(now-timedelta(days=2)).replace(hour=10).isoformat()
        self.service.ingest([self.quote(quote_timestamp=stamp)])
        with patch('app.market.session_state',return_value={'is_open':True,'status':'open'}):
            self.assertEqual(self.service.snapshot()['rows'][0]['quote_status'],'stale')
        with patch('app.market.session_state',return_value={'is_open':False,'status':'closed'}):
            self.assertEqual(self.service.snapshot()['rows'][0]['quote_status'],'closed')

    def test_session_rollover_restores_new_open_and_rejects_old_packets(self):
        before=datetime(2026,10,29,10,tzinfo=TZ)
        after=before+timedelta(days=1)
        self.service.ingest([self.quote(quote_timestamp=before.isoformat())])
        self.service.ingest([self.quote(open=102,quote_timestamp=after.isoformat())])
        self.service.ingest([self.quote(open=999,quote_timestamp=before.isoformat())])
        self.assertEqual(self.service.snapshot()['rows'][0]['open'],102)

    def test_market_weekends_and_configured_holidays(self):
        self.assertFalse(session_state(datetime(2026,11,1,11,tzinfo=TZ))['is_open'])
        with patch.object(config,'MARKET_HOLIDAYS',{'2026-11-02'}):
            self.assertEqual(session_state(datetime(2026,11,2,11,tzinfo=TZ))['reason'],'Exchange holiday')

    def test_explicit_special_session_can_override_weekend(self):
        with patch.object(config,'MARKET_SPECIAL_SESSIONS',{'2026-11-01':{'open':'18:00','close':'19:00'}}):
            self.assertTrue(session_state(datetime(2026,11,1,18,30,tzinfo=TZ))['is_open'])
            self.assertFalse(session_state(datetime(2026,11,1,11,tzinfo=TZ))['is_open'])


class PredictionTests(StoreCase):
    def fixture(self,n=1000):
        import numpy as np
        rng=np.random.default_rng(369)
        bars=[]
        previous=100.0
        for i in range(n):
            # Test-only repeating directional structure, never production data.
            direction=1 if i%40<20 else -1
            opening=previous*(1+rng.normal(0,.0002))
            close=opening*(1+direction*.006+rng.normal(0,.001))
            bars.append({'symbol':'NSE:HDFCBANK','timestamp':(datetime(2020,1,1)+timedelta(days=i)).date().isoformat(), 'open':opening,'high':max(opening,close)*1.002,'low':min(opening,close)*.998,'close':close,'volume':100000+i*100})
            previous=close
        return bars

    def test_feature_prefix_invariant_proves_no_future_features(self):
        bars=self.fixture(130)
        prefix=feature_rows(bars[:110],[('NSE:HDFCBANK','banking')])
        full=feature_rows(bars,[('NSE:HDFCBANK','banking')])
        lookup={(r['symbol'],r['as_of']):r for r in full}
        for row in prefix:
            self.assertEqual(row['x'],lookup[(row['symbol'],row['as_of'])]['x'])
        self.assertIsNone(prefix[-1]['y'])
        self.assertTrue(all(r['label_date']>r['as_of'] for r in full if r['y'] is not None))
        # Even an invalid future candle cannot change the feature prefix.
        corrupt=[{**b} for b in bars]
        corrupt[110]['close']*=4
        corrupted=feature_rows(corrupt,[('NSE:HDFCBANK','banking')])
        self.assertEqual(prefix[-1]['x'],next(r['x'] for r in corrupted if r['as_of']==prefix[-1]['as_of']))

    def test_unavailable_before_validated_training(self):
        lab=PredictionLab(self.store)
        with patch.object(config,'DATA_RETENTION_AUTHORIZED',True):
            with self.assertRaisesRegex(ValueError,'insufficient validated'):
                lab.train()
        self.assertEqual(lab.status()['predictions'],[])
        self.assertIsNone(lab.status()['model'])

    def test_training_walk_forward_oos_artifact_inference_and_version(self):
        bars=self.fixture()
        self.store.save_candles('NSE:HDFCBANK',[{**b,'date':b['timestamp']} for b in bars],authorized=True)
        lab=PredictionLab(self.store)
        with patch.object(config,'DATA_RETENTION_AUTHORIZED',True), patch.object(config,'MODEL_DIRECTORY',Path(self.tmp.name)/'models'):
            result=lab.train()
            self.assertEqual(result['state'],'ready',result.get('message'))
            status=lab.status()
            model=status['model']
            self.assertIn('out_of_sample',model['metrics'])
            self.assertEqual(len(model['payload']['comparison']),2)
            for candidate in model['payload']['comparison'].values():
                self.assertEqual(len(candidate['walk_forward']),3)
                for fold in candidate['walk_forward']:
                    self.assertLess(fold['end'],model['payload']['test_start'])
            p=status['predictions'][0]
            self.assertAlmostEqual(p['probability_up']+p['probability_down'],1)
            self.assertEqual(p['version'],model['version'])
            self.assertEqual(lab.infer()['count'],1)
            self.assertEqual(len(self.store.predictions()),1)
            with self.assertRaisesRegex(ValueError,'sufficient new sessions'):
                lab.train()


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app import main
        cls.main=main
        cls.tmp=tempfile.TemporaryDirectory()
        cls.store=Store(Path(cls.tmp.name)/'api.sqlite3')
        cls.market=MarketService(cls.store)
        cls.lab=PredictionLab(cls.store)
        cls.patches=[patch.object(main,'store',cls.store),patch.object(main,'market',cls.market),patch.object(main,'lab',cls.lab),patch.object(cls.market,'start'),patch.object(config,'KITE_ACCESS_TOKEN',''),patch.object(config,'DATA_RETENTION_AUTHORIZED',False),patch.object(config,'HISTORICAL_ENABLED',False)]
        for p in cls.patches:p.start()
        cls.client=TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)
        for p in reversed(cls.patches):p.stop()
        cls.tmp.cleanup()

    def test_all_pages_and_assets(self):
        for path in ['/','/scanner','/live-market','/ai-predictions','/history','/settings']+['/sectors/'+g['id'] for g in reference_groups()]:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertIn('DIVINE CODE',response.text)
        self.assertEqual(self.client.get('/sectors/not-approved').status_code,404)
        self.assertEqual(self.client.get('/stocks/UNKNOWN').status_code,404)
        self.assertEqual(self.client.get('/static/terminal.css').status_code,200)

    def test_empty_api_has_no_invented_quotes_or_predictions(self):
        self.assertEqual(self.client.get('/api/quotes').json()['rows'],[])
        self.assertEqual(self.client.get('/api/ai/status').json()['predictions'],[])
        self.assertEqual(self.client.post('/api/history/import',json={'symbol':'NSE:HDFCBANK'}).status_code,409)

    def test_import_progress_route_is_not_interpreted_as_stock_symbol(self):
        with patch('app.provider.daily_history') as historical:
            response=self.client.get('/api/history/imports')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['jobs'],[])
            historical.assert_not_called()

    def test_auth_state_and_session_exchange(self):
        with patch.object(config,'KITE_API_KEY','test-public-id'),patch.object(config,'KITE_REDIRECT_URL','http://localhost/auth/kite/callback'):
            login=self.client.get('/auth/kite/login',follow_redirects=False)
            self.assertEqual(login.status_code,307)
            cookie=login.cookies['kite_oauth_state']
            self.assertIn('redirect_params=state%3D',login.headers['location'])
            self.assertEqual(self.client.get('/auth/kite/callback?request_token=test&status=success&state=invalid').status_code,400)
            with patch('app.provider.create_kite_session',return_value='server-only') as exchange:
                response=self.client.get('/auth/kite/callback',params={'request_token':'test','status':'success','state':cookie},follow_redirects=False)
                self.assertEqual(response.status_code,307)
                exchange.assert_called_once_with('test')
                self.assertNotIn('server-only',response.text)

    def test_cross_origin_mutations_are_rejected(self):
        self.assertEqual(self.client.post('/api/scan',headers={'Origin':'https://untrusted.invalid'}).status_code,403)

    def test_sse_emits_updates_and_heartbeat_without_rescanning(self):
        async def check():
            request=type('Request',(),{'is_disconnected':AsyncMock(return_value=False)})()
            response=await self.main.stream(request)
            iterator=response.body_iterator
            self.assertIn('retry:',await anext(iterator))
            first=await anext(iterator)
            self.assertIn('event: quotes',first)
            self.assertIn('event: heartbeat',await anext(iterator))
            self.market.sequence+=1
            with patch('app.main.asyncio.sleep',new=AsyncMock()):
                update=await anext(iterator)
            self.assertIn(f'id: {self.market.sequence}',update)
            await iterator.aclose()
        asyncio.run(check())


if __name__=='__main__':
    unittest.main()
