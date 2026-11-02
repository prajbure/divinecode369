"""Completion regression tests. Fixtures are private to temporary test databases."""
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import config, provider
from app.calendar import session_state, completed_daily_date
from app.imports import ImportService
from app.reconciliation import reconciliation_report
from app.scanner import reference_groups, run_scan
from app.storage import Store

TZ = ZoneInfo('Asia/Kolkata')


class CalendarTests(unittest.TestCase):
    def test_official_holiday_amendment_and_no_bank_calendar_confusion(self):
        self.assertFalse(session_state(datetime(2026,1,15,11,tzinfo=TZ))['is_open'])
        self.assertTrue(session_state(datetime(2026,3,19,11,tzinfo=TZ))['is_open'])
        self.assertTrue(session_state(datetime(2026,4,1,11,tzinfo=TZ))['is_open'])
        self.assertTrue(session_state(datetime(2026,11,2,11,tzinfo=TZ))['calendar_verified'])

    def test_normal_session_phases(self):
        for hour, minute, expected in [(8,59,'closed'),(9,0,'pre_open'),(9,14,'pre_open'),(9,15,'open'),(15,29,'open'),(15,30,'closing'),(15,45,'post_close'),(16,1,'closed')]:
            with self.subTest(hour=hour,minute=minute):
                self.assertEqual(session_state(datetime(2026,11,2,hour,minute,tzinfo=TZ))['status'],expected)

    def test_official_sunday_sessions(self):
        self.assertTrue(session_state(datetime(2026,2,1,11,tzinfo=TZ))['is_open'])
        for hour,minute,expected in [(11,0,'closed'),(14,6,'pre_open'),(14,22,'open'),(15,40,'closing'),(15,55,'post_close'),(16,10,'closed')]:
            self.assertEqual(session_state(datetime(2026,11,8,hour,minute,tzinfo=TZ))['status'],expected)

    def test_unknown_year_fails_closed_without_fabricated_calendar(self):
        with patch.object(config,'MARKET_CALENDAR_VERIFIED_THROUGH',''),patch.object(config,'MARKET_SPECIAL_SESSIONS',{}):
            state=session_state(datetime(2027,1,4,11,tzinfo=TZ))
        self.assertEqual(state['status'],'unknown')
        self.assertFalse(state['is_open'])
        self.assertFalse(state['calendar_verified'])

    def test_timezone_and_completed_daily_boundary(self):
        self.assertTrue(session_state(datetime(2026,11,2,4,tzinfo=timezone.utc))['is_open'])
        self.assertEqual(completed_daily_date(datetime(2026,11,2,12,tzinfo=TZ)),date(2026,11,1))
        self.assertEqual(completed_daily_date(datetime(2026,11,2,16,16,tzinfo=TZ)),date(2026,11,2))


class StoreFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'completion.sqlite3')
        self.store.initialize(reference_groups())

    def tearDown(self):
        self.temp.cleanup()


class ImportTests(StoreFixture):
    @staticmethod
    def details(symbols):
        return [{'symbol':s,'is_equity':True,'instrument_token':123,'quote_symbol':s,'resolution_kind':'exact'} for s in symbols]

    @staticmethod
    def bar(day):
        return {'date':day.isoformat(),'open':100,'high':103,'low':99,'close':102,'volume':1000}

    def body(self,**changes):
        return {'symbol':'NSE:HDFCBANK','start':'2025-01-01','end':'2025-12-31',**changes}

    def test_retention_authorization_cannot_be_bypassed(self):
        service=ImportService(self.store)
        with patch.object(config,'DATA_RETENTION_AUTHORIZED',False),patch.object(config,'HISTORICAL_ENABLED',True),patch('app.imports.provider.historical_candles') as fetch:
            with self.assertRaisesRegex(ValueError,'explicit DATA_RETENTION_AUTHORIZED'):
                service.create(self.body())
            fetch.assert_not_called()
        self.assertEqual(self.store.import_summary()['jobs'],[])
        self.assertEqual(self.store.overview()['candles'],0)

    def test_resumable_batches_commit_cursor_and_preserve_prior_progress(self):
        service=ImportService(self.store)
        calls=[]
        failure=[True]
        def fetch(symbol,start,end,interval):
            calls.append(start)
            if start>date(2025,1,1) and failure[0]:
                failure[0]=False
                raise provider.ProviderError('Test-only interrupted connection')
            return [self.bar(start)]
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True,IMPORT_RETRY_LIMIT=1),patch('app.imports.provider.stock_names',side_effect=self.details),patch('app.imports.provider.historical_candles',side_effect=fetch):
            job=service.create(self.body())
            service.run_pending()
            partial=service.get(job['id'])
            self.assertEqual(partial['state'],'failed')
            self.assertEqual(partial['requests_completed'],1)
            self.assertEqual(partial['cursor_date'],'2025-06-30')
            resumed=ImportService(Store(self.store.path))
            resumed.control(job['id'],'resume')
            resumed.run_pending()
            result=resumed.get(job['id'])
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['requests_completed'],3)
        self.assertEqual(result['symbol_index'],1)
        self.assertEqual(calls.count(date(2025,1,1)),1)
        self.assertEqual(len(self.store.candles('NSE:HDFCBANK')),3)
        self.assertIsNotNone(self.store.import_summary()['last_successful_import'])

    def test_replaying_same_backfill_does_not_duplicate_candles(self):
        service=ImportService(self.store)
        def fetch(symbol,start,end,interval):return [self.bar(start)]
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True),patch('app.imports.provider.stock_names',side_effect=self.details),patch('app.imports.provider.historical_candles',side_effect=fetch):
            for _ in range(2):
                job=service.create(self.body())
                service.run_pending()
                self.assertEqual(service.get(job['id'])['state'],'completed')
        self.assertEqual(len(self.store.candles('NSE:HDFCBANK')),3)

    def test_incremental_update_uses_overlap_instead_of_full_backfill(self):
        self.store.save_candles('NSE:HDFCBANK',[self.bar(date(2025,12,29))],authorized=True)
        service=ImportService(self.store)
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True),patch('app.imports.provider.stock_names',side_effect=self.details),patch('app.imports.provider.historical_candles',side_effect=lambda s,start,end,i:[self.bar(start)]) as fetch:
            job=service.create(self.body(incremental=True))
            service.run_pending()
            self.assertEqual(service.get(job['id'])['state'],'completed')
        self.assertEqual(fetch.call_args.args[1],date(2025,12,27))

    def test_revoked_authorization_stops_before_any_write(self):
        service=ImportService(self.store)
        def fetch(symbol,start,end,interval):
            config.DATA_RETENTION_AUTHORIZED=False
            return [self.bar(start)]
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True),patch('app.imports.provider.stock_names',side_effect=self.details),patch('app.imports.provider.historical_candles',side_effect=fetch):
            job=service.create(self.body())
            service.run_pending()
            self.assertEqual(service.get(job['id'])['state'],'blocked_authorization')
        self.assertEqual(self.store.overview()['candles'],0)

    def test_cancellation_during_request_cannot_be_overwritten(self):
        service=ImportService(self.store)
        job=None
        def fetch(symbol,start,end,interval):
            service.control(job['id'],'cancel')
            return [self.bar(start)]
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True),patch('app.imports.provider.stock_names',side_effect=self.details),patch('app.imports.provider.historical_candles',side_effect=fetch):
            job=service.create(self.body())
            service.run_pending()
        self.assertEqual(service.get(job['id'])['state'],'cancelled')
        self.assertEqual(self.store.overview()['candles'],0)

    def test_auto_updates_respect_authorization_and_existing_universe(self):
        service=ImportService(self.store)
        self.store.save_candles('NSE:HDFCBANK',[self.bar(date(2025,12,29))],authorized=True)
        with patch.multiple(config,HISTORY_AUTO_UPDATE_ENABLED=True,DATA_RETENTION_AUTHORIZED=False,HISTORICAL_ENABLED=True):
            self.assertIsNone(service.schedule_incremental())
        with patch.multiple(config,HISTORY_AUTO_UPDATE_ENABLED=True,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True):
            job=service.schedule_incremental()
        self.assertEqual(job['request']['symbols'],['NSE:HDFCBANK'])
        self.assertTrue(job['incremental'])

    def test_unapproved_symbols_and_unfinished_ranges_are_rejected(self):
        service=ImportService(self.store)
        with patch.multiple(config,DATA_RETENTION_AUTHORIZED=True,HISTORICAL_ENABLED=True):
            with self.assertRaisesRegex(ValueError,'outside the approved'):
                service.create(self.body(symbol='NSE:UNAPPROVED'))
            with self.assertRaises(ValueError):
                service.create(self.body(end='2099-01-01'))


class ResolutionTests(StoreFixture):
    def master(self):
        return {symbol:{'tradingsymbol':symbol,'name':name,'instrument_token':str(index+1),'tick_size':'0.05'} for index,(symbol,name) in enumerate([('LTM','LTM'),('RECLTD','REC'),('HFCL-BE','HFCL'),('STLTECH-BE','STERLITE TECHNOLOGIES')])}

    def test_verified_aliases_keep_approved_membership_keys(self):
        with patch('app.provider._load_instrument_details',return_value=self.master()):
            details=provider.stock_names(['NSE:LTIM','NSE:REC','NSE:HFCL','NSE:STLTECH'])
        self.assertEqual([d['symbol'] for d in details],['NSE:LTIM','NSE:REC','NSE:HFCL','NSE:STLTECH'])
        self.assertEqual([d['quote_symbol'] for d in details],['NSE:LTM','NSE:RECLTD','NSE:HFCL-BE','NSE:STLTECH-BE'])
        self.assertTrue(all(d['is_equity'] and d['resolution_note'] for d in details))
        self.store.instrument_details(details)
        report=reconciliation_report(self.store)
        self.assertEqual((report['total_configured_entries'],report['unique_requested_instruments'],report['duplicate_membership_count']),(160,148,12))
        self.assertEqual(report['verified_aliases'],4)
        self.assertEqual(report['unresolved_aliases'],[])

    def test_different_issuer_cannot_be_substituted(self):
        master=self.master()
        master['LTM']['name']='UNRELATED ISSUER'
        with patch('app.provider._load_instrument_details',return_value=master):
            result=provider.resolve_instrument('NSE:LTIM')
        self.assertFalse(result['is_equity'])
        self.assertIsNone(result['instrument_token'])

    def test_provider_request_uses_verified_alias_and_returns_configured_key(self):
        payload={'data':{'NSE:LTM':{'ohlc':{'open':100,'close':100},'last_price':101}}}
        with patch('app.provider._load_instrument_details',return_value=self.master()),patch('app.provider._get') as get,patch('app.provider._json_payload',return_value=payload):
            quote=provider.live_quotes(['NSE:LTIM'])['data'][0]
        self.assertEqual(get.call_args.kwargs['params'],[('i','NSE:LTM')])
        self.assertEqual(quote['symbol'],'LTIM')
        self.assertEqual(quote['quote_symbol'],'NSE:LTM')

    def test_scanner_decimal_difference_does_not_make_false_exact_matches(self):
        payload={'data':[{'symbol':'HDFCBANK','exchange':'NSE','open':100.10,'prev_close':100.05,'ltp':101,'tick_size':.05}]}
        result=run_scan(['NSE:HDFCBANK'],quote_payload=payload)
        self.assertEqual(result['rows'][0]['difference_display'],'0.05')
        self.assertFalse(result['rows'][0]['match'])

    def test_auth_callback_tokens_are_removed_from_access_logs(self):
        from app.main import RedactAuthAccessLog
        record=logging.LogRecord('test',20,'test',1,'%s %s %s %s %s',('client','GET','/auth/kite/callback?request_token=test-secret','1.1',307),None)
        self.assertTrue(RedactAuthAccessLog().filter(record))
        self.assertNotIn('test-secret',record.getMessage())

    def test_trade_for_trade_instruments_are_excluded_from_intraday_backtest(self):
        from app.predictions import evaluate
        rows=[{'y':1,'as_of':'2025-01-01','label_date':'2025-01-02','target_return':.03,'backtest_eligible':False},
              {'y':0,'as_of':'2025-01-01','label_date':'2025-01-02','target_return':-.03,'backtest_eligible':False}]
        metrics=evaluate(rows,[.9,.1])
        self.assertEqual(metrics['trades'],0)
        self.assertEqual(metrics['backtest_return_after_costs'],0)
        self.assertEqual(metrics['directional_accuracy'],1)


if __name__=='__main__':
    unittest.main()
