"""Additive upgrade invariants and optional provider capabilities."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import config, main, provider
from app.market import MarketService
from app.scanner import reference_groups
from app.storage import Store


class PreservationTests(unittest.TestCase):
    def test_every_protected_source_and_artwork_hash_matches_checkpoint(self):
        baseline=json.loads((config.ROOT/'reports/advanced-upgrade-baseline.json').read_text(encoding='utf-8'))
        for name,expected in baseline['protected_sha256'].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((config.ROOT/name).read_bytes()).hexdigest(),expected)

    def test_every_original_route_and_method_still_exists(self):
        baseline=json.loads((config.ROOT/'reports/advanced-upgrade-baseline.json').read_text(encoding='utf-8'))
        routes={}
        for route in main.app.routes:
            routes.setdefault(route.path,set()).update(getattr(route,'methods',[]) or [])
        for route in baseline['routes']:
            self.assertIn(route['path'],routes)
            self.assertTrue(set(route['methods'])<=routes[route['path']])

    def test_private_credential_file_matches_documented_configuration(self):
        checkpoint=config.ROOT/'.qa/advanced-private-baseline.json'
        if checkpoint.exists():
            baseline=json.loads(checkpoint.read_text(encoding='utf-8'))
            observation=config.ROOT/'.qa/v21-external-env.json'
            if observation.exists():
                external=json.loads(observation.read_text(encoding='utf-8'))
                self.assertEqual(external['source'],'external_configuration_change')
                self.assertEqual(external['original_env_sha256'],baseline['env_sha256'])
                expected=external['observed_env_sha256']
            else:expected=baseline['env_sha256']
            self.assertEqual(hashlib.sha256((config.ROOT/'.env').read_bytes()).hexdigest(),expected)

    def test_optional_quote_fields_use_provider_values_only(self):
        fields=provider.quote_intelligence({'average_price':123.4,'ohlc':{'high':130,'low':120}})
        self.assertEqual(fields['vwap'],123.4)
        self.assertEqual(fields['day_high'],130)
        self.assertIsNone(fields['best_bid'])
        self.assertIsNone(provider.quote_intelligence({'last_price':100})['vwap'])

    def test_depth_and_invalid_provider_fields_are_not_fabricated(self):
        fields=provider.quote_intelligence({'average_price':float('nan'),'depth':{'buy':[{'price':100,'quantity':20}], 'sell':[{'price':101,'quantity':10}]}})
        self.assertEqual(fields['best_bid'],100)
        self.assertEqual(fields['depth_bid_quantity'],20)
        self.assertIsNone(fields['vwap'])

    def test_exhausted_socket_retries_release_the_old_socket(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'stream.sqlite3');store.initialize(reference_groups())
            service=MarketService(store)
            service.details=[{'symbol':'NSE:HDFCBANK','is_equity':True,'instrument_token':123,'name':'HDFC Bank'}]
            old,new=MagicMock(),MagicMock()
            with patch('kiteconnect.KiteTicker',side_effect=[old,new]) as factory:
                service._start_stream();old.on_connect(old,None)
                self.assertEqual(service.subscription_count,1)
                old.on_noreconnect(old)
                self.assertIsNone(service.ticker);self.assertFalse(service.stream_connected)
                service._start_stream();new.on_connect(new,None)
                old.on_close(old,0,'old session closed')
                self.assertIs(service.ticker,new);self.assertTrue(service.stream_connected)
                self.assertEqual(factory.call_count,2)

    def test_special_session_open_does_not_freeze_a_preopen_quote(self):
        class Frozen(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,8,15,0,tzinfo=ZoneInfo('Asia/Kolkata'))
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'special.sqlite3');store.initialize(reference_groups())
            service=MarketService(store);service.details=[{'symbol':'NSE:HDFCBANK','is_equity':True}]
            quote={'symbol':'HDFCBANK','ltp':101,'open':100,'prev_close':100,'quote_timestamp':'2026-11-08T14:10:00+05:30'}
            with patch('app.market.datetime',Frozen):
                service.ingest([quote]);self.assertEqual(service.anchors,{})
                service.ingest([{**quote,'quote_timestamp':'2026-11-08T14:23:00+05:30'}])
            self.assertTrue(service.anchors['NSE:HDFCBANK']['match'])

    def test_closed_calendar_day_cannot_establish_a_new_official_open(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'holiday.sqlite3');store.initialize(reference_groups())
            service=MarketService(store);service.details=[{'symbol':'NSE:HDFCBANK','is_equity':True}]
            service.ingest([{'symbol':'HDFCBANK','ltp':100,'open':100,'prev_close':100,'quote_timestamp':'2026-11-01T10:00:00+05:30'}])
            self.assertFalse(service.anchors)


if __name__=='__main__':
    unittest.main()
