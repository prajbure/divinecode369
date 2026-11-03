import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from app import main, config, mobile_auth, personal
from app.mobile_models import SavedItem, AlertRule
from app.ipo_service import normalize_ipo
from tests.auth_helpers import ORIGIN, admin_environment, sign_in
from tests.test_ipo import IPO


class MobileTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.enterContext(admin_environment(folder.name))
        self.enterContext(patch.object(config,'PLATFORM_DATABASE_PATH',Path(folder.name)/'platform.sqlite3'))
        self.client=TestClient(main.app,base_url=ORIGIN,client=('198.51.100.15',4000));self.addCleanup(self.client.close)
        self.owner=TestClient(main.app,base_url=ORIGIN);self.addCleanup(self.owner.close)
        self.verifier='A'*64
        self.challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b'=').decode()

    def start(self):
        response=self.client.post('/auth/mobile/start',json={'device_name':'QA phone','code_challenge':self.challenge})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def approve(self,device):
        sign_in(self.owner)
        self.assertEqual(self.owner.post('/auth/mobile/requests/'+device['request_id']+'/approve').status_code,200)

    def grant(self):
        device=self.start();self.approve(device)
        response=self.client.post('/auth/mobile/token',json={'request_id':device['request_id'],'code_verifier':self.verifier})
        self.assertEqual(response.status_code,200,response.text)
        tokens=response.json();self.client.headers['Authorization']='Bearer '+tokens['access_token'];return tokens

    def test_owner_approval_and_pkce_are_required(self):
        device=self.start();url='/auth/mobile/requests/'+device['request_id']
        self.assertEqual(self.client.get(url).status_code,401)
        self.assertEqual(self.client.post(url+'/approve').status_code,401)
        self.assertEqual(self.client.post('/auth/mobile/token',json={'request_id':device['request_id'],'code_verifier':self.verifier}).status_code,428)
        self.assertEqual(self.client.post('/auth/mobile/token',json={'request_id':device['request_id'],'code_verifier':'B'*64}).status_code,401)

    def test_approval_requires_csrf(self):
        device=self.start();sign_in(self.owner)
        response=self.owner.post('/auth/mobile/requests/'+device['request_id']+'/approve',headers={'X-CSRF-Token':'wrong'})
        self.assertEqual(response.status_code,403)

    def test_scoped_mobile_session_cannot_administer_providers(self):
        tokens=self.grant()
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,200)
        for path in ['/api/scan','/api/connections/kite/disconnect','/api/connections/kite/recheck','/auth/kite/login']:
            self.assertEqual(self.client.post(path).status_code,401,path)
        self.assertEqual(self.client.put('/api/providers/settings',json={}).status_code,401)
        self.assertNotIn(config.ADMIN_TOKEN,json.dumps(tokens))

    def test_grant_is_single_use_and_database_has_only_hashed_tokens(self):
        device=self.start();self.approve(device)
        body={'request_id':device['request_id'],'code_verifier':self.verifier}
        tokens=self.client.post('/auth/mobile/token',json=body).json()
        self.assertEqual(self.client.post('/auth/mobile/token',json=body).status_code,401)
        database=config.PLATFORM_DATABASE_PATH.read_bytes()
        for value in tokens.values():
            if isinstance(value,str) and value.startswith('dc_'):self.assertNotIn(value.encode(),database)

    def test_rotation_reuse_revokes_entire_family(self):
        first=self.grant()
        second=self.client.post('/auth/mobile/refresh',json={'refresh_token':first['refresh_token']}).json()
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)
        self.client.headers['Authorization']='Bearer '+second['access_token']
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,200)
        self.assertEqual(self.client.post('/auth/mobile/refresh',json={'refresh_token':first['refresh_token']}).status_code,401)
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)

    def test_logout_and_owner_revocation(self):
        first=self.grant()
        self.assertEqual(self.client.post('/auth/mobile/logout').status_code,200)
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)
        self.assertEqual(self.client.post('/auth/mobile/refresh',json={'refresh_token':first['refresh_token']}).status_code,401)
        self.grant();family=self.client.get('/auth/mobile/session').json()['family']
        self.assertEqual(self.owner.delete('/auth/mobile/sessions/'+family).status_code,200)
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)

    def test_access_and_refresh_expiration(self):
        tokens=self.grant()
        with mobile_auth.database() as db:db.execute('UPDATE mobile_access SET expires=0')
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)
        self.assertEqual(self.client.post('/auth/mobile/refresh',json={'refresh_token':tokens['refresh_token']}).status_code,200)
        with mobile_auth.database() as db:db.execute('UPDATE mobile_families SET expires=0')
        self.assertEqual(self.client.get('/auth/mobile/session').status_code,401)

    def test_transport_origin_and_no_localhost_bypass(self):
        self.grant()
        for headers in [{'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.client.get('/auth/mobile/session',headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/scan',headers={'X-Forwarded-For':'127.0.0.1','Host':'localhost'}).status_code,401)
        insecure=TestClient(main.app,base_url='http://localhost')
        self.addCleanup(insecure.close)
        self.assertEqual(insecure.post('/auth/mobile/start',json={'device_name':'test','code_challenge':self.challenge}).status_code,403)

    def test_rate_limit_and_poll_interval(self):
        device=self.start();body={'request_id':device['request_id'],'code_verifier':self.verifier}
        self.assertEqual(self.client.post('/auth/mobile/token',json=body).status_code,428)
        self.assertEqual(self.client.post('/auth/mobile/token',json=body).status_code,429)
        for _ in range(4):self.start()
        self.assertEqual(self.client.post('/auth/mobile/start',json={'device_name':'test','code_challenge':self.challenge}).status_code,429)

    def test_validation_never_echoes_session_material(self):
        value='dc_refresh_secret-validation-value'
        response=self.client.post('/auth/mobile/refresh',json={'refresh_token':value})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(value,response.text)

    def test_watchlist_shared_with_website_and_tombstones(self):
        self.grant()
        body={'kind':'ipo','key':'test-ipo','label':'Test IPO','saved':True}
        self.assertEqual(self.client.put('/api/v1/mobile/watchlist',json=body).status_code,200)
        self.assertTrue(self.owner.get('/api/v1/mobile/watchlist').json()['items'][0]['saved'])
        body['saved']=False;self.owner.put('/api/v1/mobile/watchlist',json=body)
        self.assertFalse(self.client.get('/api/v1/mobile/watchlist').json()['items'][0]['saved'])
        self.assertEqual(self.owner.put('/api/v1/mobile/watchlist',json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.client.put('/api/v1/mobile/watchlist',json={**body,'kind':'stock','key':'NSE:FAKE'}).status_code,422)

    def test_preferences_alerts_and_inbox_persist(self):
        self.grant()
        self.assertEqual(self.client.put('/api/v1/mobile/preferences',json={'theme':'light','density':'compact','notifications':True}).status_code,200)
        self.assertEqual(self.owner.get('/api/v1/mobile/preferences').json()['theme'],'light')
        rule={'ipo_slug':'test-ipo','event':'gmp_threshold','threshold':5}
        self.assertEqual(self.client.put('/api/v1/mobile/alerts',json=rule).status_code,200)
        self.assertEqual(len(self.owner.get('/api/v1/mobile/alerts').json()['items']),1)
        self.assertEqual(self.client.get('/api/v1/mobile/alerts/inbox').status_code,200)
        self.assertEqual(self.client.put('/api/v1/mobile/alerts',json={**rule,'threshold':None}).status_code,422)

    def test_public_apis_preserve_universe_and_make_no_provider_requests(self):
        with patch('app.provider.live_quotes') as kite,patch.object(main.ipo_service.client,'get') as ipo:
            response=self.client.get('/api/v1/mobile/sectors')
            self.assertEqual(response.status_code,200,response.text)
            body=response.json();self.assertEqual(len(body['items']),16)
            self.assertEqual(sum(s['memberships'] for s in body['items']),160)
            self.assertEqual(body['unique_symbols'],148)
            for path in ['/api/v1/mobile/overview','/api/v1/mobile/scanner?match=universe','/api/v1/mobile/ipos','/api/v1/mobile/health']:
                self.assertEqual(self.client.get(path).status_code,200,path)
            kite.assert_not_called();ipo.assert_not_called()

    def test_ipo_filters_pagination_nulls_and_expected_dates(self):
        row=normalize_ipo(IPO);row['timeline']['allotment_date']='2020-01-01'
        rows=[row,{**deepcopy(row),'slug':'sme-ipo','type':'SME','status':'Upcoming'}, {**deepcopy(row),'slug':'closed-ipo','status':'Closed'}]
        with patch.object(main.connections,'get_overview',return_value={'rows':rows,'meta':{'available':True,'fetched_at':'2026-11-03T00:00:00Z'}}):
            self.assertEqual(self.client.get('/api/v1/mobile/ipos?phase=ongoing').json()['total'],1)
            self.assertEqual(self.client.get('/api/v1/mobile/ipos?phase=allotted').json()['total'],0)
            body=self.client.get('/api/v1/mobile/ipos?phase=all&board=SME&page_size=1').json()
            self.assertEqual(body['items'][0]['slug'],'sme-ipo')
            self.assertEqual(body['total'],1)
            self.assertIsNone(body['items'][0]['listing']['price'])
        self.assertEqual(self.client.get('/api/v1/mobile/ipos?page_size=1000').status_code,422)

    def test_public_pages_and_contract(self):
        for path in ['/','/ipo','/settings','/mobile/connect']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        contract=self.client.get('/openapi.json').json()
        self.assertIn('/api/v1/mobile/watchlist',contract['paths'])
        self.assertEqual(self.client.get('/.well-known/assetlinks.json').json(),[])

    def test_large_mobile_snapshot_is_compressed_and_auth_is_not(self):
        response=self.client.get('/api/v1/mobile/overview',headers={'Accept-Encoding':'gzip'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers.get('content-encoding'),'gzip')
        self.assertIn('accept-encoding',response.headers.get('vary','').lower())
        self.assertEqual(len(response.json()['sectors']),16)
        auth_response=self.client.get('/auth/admin/session',headers={'Accept-Encoding':'gzip'})
        self.assertNotIn('content-encoding',auth_response.headers)


if __name__=='__main__':unittest.main()
