"""Only mocked provider traffic. Never consumes a real IPO Guru key."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import config, main
from app.ipoguru import IPOGuruClient, IPOError, STANDARD_SCOPES
from app.ipo_service import (IPOService,numeric,normalize_ipo,normalize_history,normalize_subscription,normalize_company,
                            registrar_url,research,freshness)
from app.ipo_routes import create_ipo_router

ACCOUNT={'plan':'standard','scopes':sorted(STANDARD_SCOPES),'limits':{'per_day':1000,'per_minute':20},'usage_today':{'remaining':999}}
IPO={'slug':'test-industries-ipo','name':'TEST FIXTURE Industries','type':'Mainboard','status':'Open',
     'price_min':90,'price_max':100,'issue_price':'95','lot_size':100,
     'gmp':{'price':'10','updated_at':'2026-11-02T05:00:00Z'},'subscription_total':'3.5'}


def response(data=None,status=200,headers=None,**error):
    body={'success':True,'data':data} if status==200 else {'success':False,**error}
    return Mock(status_code=status,headers=headers or {},content=json.dumps(body).encode(),json=lambda:body)


class IPOClientTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.now=[1793595600.0]
        self.session=Mock()
        self.client=IPOGuruClient(key='SECRET-IPO-TEST-KEY',enabled=True,session=self.session,
            quota_path=Path(self.folder.name)/'quota.sqlite3',clock=lambda:self.now[0],ttl=300)
        self.session.get.side_effect=[response(ACCOUNT),response([IPO]),response([])]

    def test_disabled_provider_never_makes_http_calls(self):
        self.client.enabled=False
        self.assertFalse(self.client.get('/ipos','calendar')['meta']['available'])
        self.session.get.assert_not_called()

    def test_plan_verified_before_calendar_and_bulk_gmp_and_cached(self):
        service=IPOService(self.client)
        first,second=service.overview(),service.overview()
        self.assertEqual(first['rows'],second['rows'])
        paths=[c.args[0].split('/api/v2')[1] for c in self.session.get.call_args_list]
        self.assertEqual(paths,['/me','/ipos','/gmp'])
        self.assertEqual(self.client.status()['quota']['remaining'],997)
        call=self.session.get.call_args_list[0]
        self.assertEqual(call.kwargs['headers']['X-API-KEY'],'SECRET-IPO-TEST-KEY')
        self.assertFalse(call.kwargs['allow_redirects'])
        self.assertNotIn('SECRET-IPO-TEST-KEY',json.dumps(second))

    def test_concurrent_requests_are_deduplicated(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda _:self.client.get('/ipos','calendar'),range(5)))
        self.assertTrue(all(r['meta']['available'] for r in results))
        self.assertEqual(self.session.get.call_count,2)

    def test_free_or_lapsed_account_does_not_call_standard_endpoint(self):
        self.session.get.side_effect=[response({'plan':'free','scopes':['calendar','gmp','details'],'limits':{'per_minute':1,'per_day':10}})]
        result=self.client.get('/ipos/test-ipo/subscription','subscription')
        self.assertEqual(result['meta']['error']['code'],'scope_unavailable')
        self.assertEqual(self.session.get.call_count,1)
        self.assertEqual(self.client.status()['limits']['per_day'],10)

    def test_402_latches_scope_without_repeated_calls(self):
        self.session.get.side_effect=[response(ACCOUNT),response(status=402,required_scope='anchors')]
        self.client.get('/ipos/test-ipo/anchors','anchors')
        self.client.get('/ipos/other-ipo/anchors','anchors')
        self.assertEqual(self.session.get.call_count,2)

    def test_401_and_403_stop_authentication_retries_and_redact_errors(self):
        for status in (401,403):
            self.client.auth_failed=False
            self.now[0]+=61
            self.session.get.side_effect=[response(status=status,message='SECRET-IPO-TEST-KEY')]
            value=self.client.get('/me','account')
            again=self.client.get('/me','account')
            self.assertEqual(again['meta']['error']['code'],'authentication_failed')
            self.assertNotIn('SECRET-IPO-TEST-KEY',json.dumps(value))

    def test_retry_after_is_honored(self):
        self.session.get.side_effect=[response(ACCOUNT),response(status=429,headers={'Retry-After':'120'},error='rate_limited')]
        value=self.client.get('/ipos','calendar')
        self.assertEqual(value['meta']['error']['retry_after'],120)
        self.now[0]+=60
        self.client.get('/gmp','gmp')
        self.assertEqual(self.session.get.call_count,2)

    def test_daily_quota_persists_across_restart(self):
        self.session.get.side_effect=[response(ACCOUNT),response(status=429,error='daily_quota_reached')]
        self.client.get('/ipos','calendar')
        restarted=IPOGuruClient(key='SECRET-IPO-TEST-KEY',enabled=True,session=self.session,
            quota_path=Path(self.folder.name)/'quota.sqlite3',clock=lambda:self.now[0]+61)
        result=restarted.get('/ipos','calendar')
        self.assertEqual(result['meta']['error']['code'],'daily_quota_reached')
        self.assertEqual(self.session.get.call_count,2)

    def test_exponential_outage_backoff_and_stale_cache(self):
        self.client.get('/ipos','calendar')
        self.now[0]+=301
        self.session.get.side_effect=requests.ConnectionError('SECRET-IPO-TEST-KEY')
        first=self.client.get('/ipos','calendar')
        self.assertTrue(first['meta']['cache_stale'])
        self.assertEqual(first['meta']['error']['retry_after'],15)
        self.now[0]+=16
        second=self.client.get('/ipos','calendar')
        self.assertEqual(second['meta']['error']['retry_after'],30)
        self.assertNotIn('SECRET-IPO-TEST-KEY',json.dumps(second))

    def test_burst_limit_and_midnight_ist_reset(self):
        self.client.get('/me','account')
        for _ in range(19):self.client.ledger.transact(self.now[0],20,1000,reserve=True)
        with self.assertRaises(IPOError):self.client.ledger.transact(self.now[0],20,1000,reserve=True)
        before=self.client.ledger.transact(self.now[0],20,1000)
        self.assertEqual(before['local_requests_today'],20)
        later=datetime(2026,11,3,0,0,tzinfo=__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).timestamp()
        after=self.client.ledger.transact(later,20,1000,reserve=True)
        self.assertEqual(after['local_requests_today'],1)

    def test_response_headers_override_remaining_budget(self):
        self.session.get.side_effect=[response(ACCOUNT),response([IPO],headers={'X-RateLimit-Remaining':'4','X-RateLimit-Limit':'1000'})]
        self.client.get('/ipos','calendar')
        self.assertEqual(self.client.status()['quota']['remaining'],4)

    def test_malformed_resources_do_not_look_like_empty_calendar(self):
        self.session.get.side_effect=[response(ACCOUNT),response('invalid')]
        value=self.client.get('/ipos','calendar')
        self.assertFalse(value['meta']['available'])

    def test_auth_failure_marks_previously_cached_resources_stale(self):
        self.client.get('/ipos','calendar')
        self.session.get.side_effect=[response(status=403)]
        self.client.get('/me','account',verify=True)
        resource=self.client.get('/ipos','calendar')
        self.assertFalse(self.client.status()['verified'])
        self.assertEqual(resource['meta']['error']['code'],'authentication_failed')

    def test_low_budget_reuses_shared_cache_for_an_hour(self):
        self.session.get.side_effect=[response(ACCOUNT),response([IPO],headers={'X-RateLimit-Remaining':'4'})]
        self.client.get('/ipos','calendar')
        self.now[0]+=600
        self.assertTrue(self.client.get('/ipos','calendar')['meta']['cache_hit'])
        self.assertEqual(self.session.get.call_count,2)

    def test_successful_payload_cannot_reflect_the_secret(self):
        self.session.get.side_effect=[response(ACCOUNT),response([{**IPO,'name':'Echo SECRET-IPO-TEST-KEY'}])]
        self.assertNotIn('SECRET-IPO-TEST-KEY',json.dumps(self.client.get('/ipos','calendar')))

    def test_redirect_or_foreign_base_cannot_leak_header(self):
        self.client.base='https://example.com/api/v2'
        self.client.get('/ipos','calendar')
        self.session.get.assert_not_called()

    def test_unsupported_endpoints_and_path_injection_never_call_provider(self):
        for path,scope in [('/unlisted','unlisted'),('/ipos/../me','details'),('/ipos/abc/subscription/history','subscription_history')]:
            with self.assertRaises(IPOError):self.client.get(path,scope)
        self.session.get.assert_not_called()


class IPONormalizationTests(unittest.TestCase):
    def test_numeric_strings_missing_zero_and_malformed(self):
        for value,expected in [('1,00,000.5',100000.5),('1,234,567',1234567),('0',0),(None,None),('',None),('10,,20',None),('NaN',None),(True,None),('1e5',None)]:
            self.assertEqual(numeric(value),expected)

    def test_cap_based_gmp_estimate_and_actual_final_issue_return_are_separate(self):
        ipo=normalize_ipo({**IPO,'listing_price':'110'})
        self.assertEqual(ipo['gmp']['percentage'],10)
        self.assertEqual(ipo['gmp']['estimate'],110)
        self.assertEqual(ipo['issue']['min_investment'],10000)
        self.assertAlmostEqual(ipo['listing']['gain'],15.7895)

    def test_missing_fields_do_not_turn_into_zeros_or_assumed_final_issue_price(self):
        ipo=normalize_ipo({'slug':'missing-ipo','price_max':100,'gmp':{'price':None},'listing_price':120})
        self.assertIsNone(ipo['gmp']['price']);self.assertIsNone(ipo['gmp']['percentage'])
        self.assertIsNone(ipo['listing']['gain'])
        self.assertEqual(normalize_ipo({'slug':'zero-ipo','price_max':100,'gmp':{'price':'0'}})['gmp']['percentage'],0)

    def test_daywise_history_excludes_pro_timeline_and_preserves_gaps(self):
        value=normalize_history({'trend':[{'date':'2026-11-02','price_value':0,'price':'invalid'},
            {'date':'2026-11-01','price':None},{'date':'bad','price':9}], 'timeline':[{'price':999}]})
        self.assertEqual([v['price'] for v in value['trend']],[None,0])
        self.assertNotIn('timeline',value)

    def test_category_mapping_preserves_zero_and_reserved_categories(self):
        value=normalize_subscription({'summary':{'total':'3.5','employee':'0'},'categories':[
            {'key':'QIB','times_value':10,'times':'broken','sub_categories':[{'key':'FII','times':'2'}]},
            {'key':'RETAIL','times':None},{'key':'SHAREHOLDER','times':'0.5'}]})
        rows={v['key']:v for v in value['categories']}
        self.assertEqual(rows['QIB']['times'],10)
        self.assertEqual(rows['EMPLOYEE']['times'],0)
        self.assertIsNone(rows['RETAIL']['times'])
        self.assertEqual(rows['SHAREHOLDER']['times'],0.5)

    def test_registrar_link_requires_verified_domain_and_https(self):
        self.assertEqual(registrar_url('https://ipo.bigshareonline.com/ipo_status.html'),'https://ipo.bigshareonline.com/ipo_status.html')
        for url in ('javascript:alert(1)','https://bigshareonline.com.evil.test/','http://ipo.bigshareonline.com/','https://user:password@kfintech.com/'):
            self.assertIsNone(registrar_url(url))

    def test_source_timestamp_is_not_fetch_time_and_future_is_unknown(self):
        now=datetime(2026,11,2,6,tzinfo=timezone.utc)
        self.assertEqual(freshness('2026-11-02T05:55:00Z',now)['status'],'recent')
        self.assertEqual(freshness('2026-11-02T07:00:00Z',now)['status'],'unknown')
        self.assertEqual(freshness(None,now)['status'],'unknown')

    def test_research_explains_missing_and_contradictory_data(self):
        ipo=normalize_ipo({**IPO,'gmp':{'price':'-5'},'subscription_total':'0.5'})
        score=research(ipo,{'risks':['High borrowing']})
        self.assertGreaterEqual(len(score['contradictory']),3)
        self.assertTrue(score['missing'])
        self.assertEqual(score['score'],5)

    def test_research_does_not_compare_quarter_to_annual_or_assume_row_order(self):
        ipo=normalize_ipo(IPO)
        company={'financials':{'headers':['30 Jun 2026','31 Mar 2025'],'rows':[{'metric':'Revenue','data':[200,100]}]}}
        self.assertTrue(any('comparable' in v for v in research(ipo,company)['missing']))

    def test_malformed_financial_arrays_cannot_create_fabricated_values(self):
        value=normalize_company({'about':123,'financials':{'headers':['31 Mar 2026'],
            'rows':[{'metric':'Revenue','data':'123'},{'metric':'PAT','data':['NaN']}]}})
        self.assertIsNone(value['about'])
        self.assertEqual(value['financials']['rows'][0]['data'],[])
        self.assertEqual(value['financials']['rows'][1]['data'],[None])


class IPORouteTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        client=IPOGuruClient(key='',enabled=False,quota_path=Path(self.folder.name)/'q.sqlite3')
        app=FastAPI();app.include_router(create_ipo_router(lambda request:None,lambda:'Existing UI',client))
        self.http=TestClient(app)

    def test_disabled_dashboard_still_opens_without_kite(self):
        self.assertEqual(self.http.get('/ipo').status_code,200)
        data=self.http.get('/api/ipo/overview').json()
        self.assertFalse(data['meta']['available'])
        self.assertIsNone(data['counts']['open'])

    def test_no_raw_account_secrets_and_standard_only_routes(self):
        data=self.http.post('/api/ipo/verify').json()
        self.assertNotIn('data',data)
        self.assertEqual(self.http.get('/api/ipo/details/test-ipo/subscription-history').status_code,404)
        self.assertEqual(self.http.get('/api/ipo/details/INVALID').status_code,422)

    def test_all_original_routes_and_scanner_artwork_and_universe_preserved(self):
        baseline=json.loads((config.ROOT/'reports/ipo-baseline.json').read_text(encoding='utf-8'))
        routes={}
        for route in main.app.routes:routes.setdefault(route.path,set()).update(getattr(route,'methods',[]) or [])
        for route in baseline['routes']:self.assertTrue(set(route['methods'])<=routes[route['path']])
        for path,expected in baseline['sha256'].items():
            # V2.1 explicitly upgrades provider/session lifecycle; scanner, storage,
            # mappings and original artwork remain protected byte-for-byte.
            if path in ('app/scanner.py','app/storage.py','static/sector-universe.json') or path.endswith(('.webp','.png','.svg','.jpg')):
                self.assertEqual(hashlib.sha256((config.ROOT/path).read_bytes()).hexdigest(),expected,path)
