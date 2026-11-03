"""Real ASGI authentication tests with temporary storage and synthetic credentials."""
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import config, main
from app.admin_auth import AdminAuth, COOKIE, auth, digest, hash_password, verify_password
from app.logging_filters import CredentialFilter
from tests.auth_helpers import ORIGIN, PASSWORD, admin_environment, sign_in


class AdminAuthorizationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(admin_environment(folder.name))
        self.client = TestClient(main.app, base_url=ORIGIN, client=('198.51.100.10', 4000))
        self.addCleanup(self.client.close)
        self.scan = self.enterContext(patch.object(main.market, 'scan', return_value={'rows': []}))

    def bootstrap(self):
        response = self.client.get('/auth/admin/session')
        self.assertEqual(response.status_code, 200)
        self.client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']})
        return response

    def test_all_api_mutations_deny_anonymous_access(self):
        routes = [(r.path, m) for r in main.app.routes for m in getattr(r, 'methods', [])
                  if r.path.startswith('/api/') and m not in {'GET', 'HEAD', 'OPTIONS'}]
        self.assertGreater(len(routes), 12)
        for path, method in routes:
            path = path.replace('{job_id}', 'test').replace('{operation}', 'cancel').replace('{record_id}', 'test')
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, json={}).status_code, 401)

    def test_future_provider_settings_and_credential_routes_fail_closed(self):
        for path in ['/api/settings', '/api/connections/kite/credentials', '/api/providers/settings']:
            self.assertEqual(self.client.put(path, json={}).status_code, 401)

    def test_valid_login_cookie_flags_rotation_and_no_secret_disclosure(self):
        self.bootstrap()
        old = self.client.cookies[COOKIE]
        response = sign_in(self.client)
        self.assertNotEqual(old, self.client.cookies[COOKIE])
        for flag in ['HttpOnly', 'Secure', 'SameSite=lax', 'Path=/', 'Max-Age=300']:
            self.assertIn(flag, response.headers['set-cookie'])
        self.assertNotIn('Domain=', response.headers['set-cookie'])
        for secret in [config.ADMIN_TOKEN, config.ADMIN_PASSWORD_HASH, PASSWORD, self.client.cookies[COOKIE]]:
            self.assertNotIn(secret, response.text)
        self.assertTrue(self.client.get('/auth/admin/session').json()['authenticated'])
        self.assertEqual(self.client.post('/api/scan').status_code, 200)
        self.assertEqual(self.client.get('/auth/admin/session').headers['cache-control'], 'no-store')

    def test_wrong_credentials_are_generic(self):
        self.bootstrap()
        for user, password in [('wrong', PASSWORD), ('owner', 'wrong'), ('owner', {'bad': True}), ('owner', '\ud800'), ('\ud800', PASSWORD)]:
            response = self.client.post('/auth/admin/login', content=json.dumps({'username': user, 'password': password}), headers={'Content-Type': 'application/json'})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()['detail'], 'Invalid administrator credentials.')
        self.assertEqual(self.client.post('/api/scan').status_code, 401)

    def test_missing_configuration_fails_closed(self):
        for fields in [{'ADMIN_TOKEN': ''}, {'ADMIN_TOKEN': 'short'}, {'ADMIN_USERNAME': ''}, {'ADMIN_PASSWORD_HASH': 'invalid'}]:
            with self.subTest(fields=list(fields)), patch.multiple(config, **fields):
                self.assertEqual(self.client.get('/auth/admin/session').status_code, 503)
                self.assertEqual(self.client.post('/api/scan').status_code, 401)

    def test_login_requires_cookie_csrf_and_same_origin(self):
        body = {'username': 'owner', 'password': PASSWORD}
        self.assertEqual(self.client.post('/auth/admin/login', json=body).status_code, 403)
        self.bootstrap()
        for headers in [{'X-CSRF-Token': 'wrong'}, {'Origin': 'https://evil.example'}]:
            self.assertEqual(self.client.post('/auth/admin/login', json=body, headers=headers).status_code, 403)
        self.assertFalse(self.client.get('/auth/admin/session').json()['authenticated'])

    def test_login_throttled_using_peer_not_forwarded_headers(self):
        self.bootstrap()
        for number in range(5):
            response = self.client.post('/auth/admin/login', json={'username': 'owner', 'password': 'wrong'}, headers={'X-Forwarded-For': f'127.0.0.{number + 1}'})
            self.assertEqual(response.status_code, 401)
        blocked = self.client.post('/auth/admin/login', json={'username': 'owner', 'password': PASSWORD})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers['retry-after'], '900')

    def test_logout_revokes_cookie_and_server_session(self):
        sign_in(self.client)
        raw = self.client.cookies[COOKIE]
        self.assertEqual(self.client.post('/auth/admin/logout').status_code, 200)
        self.assertNotIn(COOKIE, self.client.cookies)
        self.client.cookies.set(COOKIE, raw)
        self.assertEqual(self.client.post('/api/scan').status_code, 401)
        self.scan.assert_not_called()

    def test_expiration_is_enforced_server_side_without_sliding(self):
        expires = sign_in(self.client).json()['expires_at']
        self.assertEqual(self.client.get('/auth/admin/session').json()['expires_at'], expires)
        with patch('app.admin_auth.time.time', return_value=expires + 1):
            self.assertEqual(self.client.post('/api/scan').status_code, 401)
        self.scan.assert_not_called()

    def test_expired_preauth_session_cannot_login(self):
        expires = self.bootstrap().json()['expires_at']
        with patch('app.admin_auth.time.time', return_value=expires + 1):
            self.assertEqual(self.client.post('/auth/admin/login', json={'username': 'owner', 'password': PASSWORD}).status_code, 403)

    def test_password_or_session_key_rotation_revokes_sessions(self):
        sign_in(self.client)
        for fields in [{'ADMIN_TOKEN': 'new-backend-key-' + 'x' * 32}, {'ADMIN_PASSWORD_HASH': hash_password('replacement-password-369')}]:
            with patch.multiple(config, **fields):
                self.assertEqual(self.client.post('/api/scan').status_code, 401)

    def test_anonymous_and_tampered_cookies_cannot_authenticate(self):
        self.bootstrap()
        self.assertEqual(self.client.post('/api/scan').status_code, 401)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE, 'a' * 43)
        self.assertEqual(self.client.post('/api/scan').status_code, 401)

    def test_csrf_enforced_on_all_administrative_mutation_types(self):
        sign_in(self.client)
        for method, path in [('POST', '/api/scan'), ('POST', '/api/connections/kite/disconnect'),
                             ('POST', '/api/connections/kite/recheck'), ('POST', '/api/ipo/verify'),
                             ('PUT', '/api/watchlist'), ('DELETE', '/api/journal/test'),
                             ('POST', '/auth/admin/logout'), ('POST', '/auth/kite/login')]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, json={}, headers={'X-CSRF-Token': 'invalid'}).status_code, 403)

    def test_csrf_from_another_session_cannot_be_reused(self):
        old = self.bootstrap().json()['csrf_token']
        sign_in(self.client)
        self.assertEqual(self.client.post('/api/scan', headers={'X-CSRF-Token': old}).status_code, 403)

    def test_missing_origin_wrong_scheme_and_cross_site_rejected(self):
        sign_in(self.client)
        for headers in [{'Origin': 'http://terminal.example'}, {'Origin': 'https://terminal.example.evil.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.client.post('/api/scan', headers=headers).status_code, 403)
        del self.client.headers['Origin']
        self.assertEqual(self.client.post('/api/scan').status_code, 403)

    def test_http_and_spoofed_localhost_do_not_bypass_authentication(self):
        for peer in ['198.51.100.2', '127.0.0.1', '::1', 'testclient']:
            client = TestClient(main.app, base_url='https://localhost', client=(peer, 4000))
            self.addCleanup(client.close)
            self.assertEqual(client.post('/api/scan', headers={'X-Forwarded-For': '127.0.0.1', 'X-Real-IP': '::1', 'Forwarded': 'for=127.0.0.1'}).status_code, 401)
        client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 4000))
        self.addCleanup(client.close)
        self.assertEqual(client.get('/auth/admin/session').status_code, 403)
        self.assertEqual(client.post('/api/scan', headers={'X-Forwarded-Proto': 'https'}).status_code, 403)

    def test_public_pages_and_readonly_apis_remain_public(self):
        for path in ['/', '/scanner', '/sectors', '/sectors/banking', '/ipo', '/ipo/gmp', '/settings', '/connections', '/api/quotes', '/api/calendar']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        with patch.object(main.connections, 'get_overview', return_value={'rows': [], 'meta': {}}):
            self.assertEqual(self.client.get('/api/ipo/overview').status_code, 200)
        self.assertEqual(self.client.get('/api/journal').status_code, 401)
        self.assertEqual(self.client.get('/api/intelligence/context/NSE:HDFCBANK').status_code, 401)

    def test_provider_actions_require_login_and_work_with_csrf(self):
        with patch.object(main.connections, 'disconnect_kite') as disconnect, patch.object(main.connections, 'snapshot', return_value={}), patch.object(main.connections.kite, 'next_check', 123):
            self.assertEqual(self.client.post('/api/connections/kite/disconnect').status_code, 401)
            disconnect.assert_not_called()
            sign_in(self.client)
            self.assertEqual(self.client.post('/api/connections/kite/recheck').status_code, 200)
            self.assertEqual(main.connections.kite.next_check, 0)
            self.assertEqual(self.client.post('/api/connections/kite/disconnect').status_code, 200)
            disconnect.assert_called_once()

    def test_ipo_provider_verification_uses_authenticated_request(self):
        sign_in(self.client)
        with patch.object(main.ipo_service.client, 'get', return_value={'meta': {'available': True}}) as verify, patch.object(main.ipo_service.client, 'status', return_value={'configured': True}):
            response = self.client.post('/api/ipo/verify')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['meta']['available'])
        verify.assert_called_once_with('/me', 'account', verify=True)

    def test_kite_start_and_callback_require_admin_and_single_use_state(self):
        with patch.multiple(config, KITE_API_KEY='test-kite-key', KITE_REDIRECT_URL=ORIGIN + '/auth/kite/callback'):
            self.assertEqual(self.client.get('/auth/kite/login', follow_redirects=False).status_code, 303)
            self.assertEqual(self.client.post('/auth/kite/login').status_code, 401)
            self.assertEqual(self.client.get('/auth/kite/callback?status=success&request_token=x&state=y').status_code, 401)
            sign_in(self.client)
            self.assertEqual(self.client.post('/auth/kite/login').status_code, 200)
            state = self.client.cookies['kite_oauth_state']
            params = {'request_token': 'test-request', 'status': 'success', 'state': state}
            with patch('app.provider.create_kite_session', return_value='provider-secret') as exchange, patch.object(main.connections, 'accept_kite') as accept:
                response = self.client.get('/auth/kite/callback', params=params, follow_redirects=False)
                self.assertEqual(response.status_code, 307)
                exchange.assert_called_once_with('test-request')
                accept.assert_called_once_with('provider-secret')
                self.client.cookies.set('kite_oauth_state', state)
                self.assertEqual(self.client.get('/auth/kite/callback', params=params).status_code, 400)
                self.assertEqual(exchange.call_count, 1)

    def test_cross_site_callback_fetch_and_iframe_are_rejected_without_consuming_state(self):
        with patch.multiple(config, KITE_API_KEY='test-kite-key', KITE_REDIRECT_URL=ORIGIN + '/auth/kite/callback'):
            sign_in(self.client)
            self.client.post('/auth/kite/login')
            state = self.client.cookies['kite_oauth_state']
            params = {'request_token': 'test-request', 'status': 'success', 'state': state}
            del self.client.headers['Origin']
            with patch('app.provider.create_kite_session', return_value='provider-secret') as exchange, patch.object(main.connections, 'accept_kite'):
                for mode, dest in [('cors', 'empty'), ('no-cors', 'empty'), ('navigate', 'iframe'), ('navigate', 'empty')]:
                    with self.subTest(mode=mode, dest=dest):
                        response = self.client.get('/auth/kite/callback', params=params,
                            headers={'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': mode, 'Sec-Fetch-Dest': dest})
                        self.assertEqual(response.status_code, 403)
                exchange.assert_not_called()
                response = self.client.get('/auth/kite/callback', params=params,
                    headers={'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}, follow_redirects=False)
                self.assertEqual(response.status_code, 307)
                exchange.assert_called_once()

    def test_cross_site_callback_still_requires_authentication_and_valid_state(self):
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
        params = {'request_token': 'test-request', 'status': 'success', 'state': 'invalid-state'}
        with patch('app.provider.create_kite_session') as exchange:
            self.assertEqual(self.client.get('/auth/kite/callback', params=params, headers=headers).status_code, 401)
            sign_in(self.client)
            del self.client.headers['Origin']
            self.assertEqual(self.client.get('/auth/kite/callback', params=params, headers=headers).status_code, 400)
            self.client.cookies.set('kite_oauth_state', 'invalid-state')
            # Matching cookie/query alone cannot create the server-side OAuth state.
            self.assertEqual(self.client.get('/auth/kite/callback', params=params, headers=headers).status_code, 400)
            exchange.assert_not_called()

    def test_cross_site_navigation_exception_does_not_apply_to_other_admin_routes(self):
        sign_in(self.client)
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
        for path in ['/auth/admin/session', '/api/journal', '/api/intelligence/context/NSE:HDFCBANK']:
            self.assertEqual(self.client.get(path, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/connections/kite/disconnect', headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/auth/kite/login', headers=headers).status_code, 403)

    def test_cross_site_callback_cannot_replay_or_ignore_origin_check(self):
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
        with patch.multiple(config, KITE_API_KEY='test-kite-key', KITE_REDIRECT_URL=ORIGIN + '/auth/kite/callback'):
            sign_in(self.client)
            self.client.post('/auth/kite/login')
            state = self.client.cookies['kite_oauth_state']
            params = {'request_token': 'test-request', 'status': 'success', 'state': state}
            del self.client.headers['Origin']
            with patch('app.provider.create_kite_session', return_value='provider-secret') as exchange, patch.object(main.connections, 'accept_kite'):
                result = self.client.get('/auth/kite/callback', params=params, headers={**headers, 'Origin': 'https://untrusted.example'})
                self.assertEqual(result.status_code, 403)
                exchange.assert_not_called()
                self.assertEqual(self.client.get('/auth/kite/callback', params=params, headers=headers, follow_redirects=False).status_code, 307)
                self.client.cookies.set('kite_oauth_state', state)
                self.assertEqual(self.client.get('/auth/kite/callback', params=params, headers=headers).status_code, 400)
                exchange.assert_called_once()

    def test_callback_rejected_after_logout(self):
        sign_in(self.client)
        self.client.post('/auth/admin/logout')
        with patch('app.provider.create_kite_session') as exchange:
            self.assertEqual(self.client.get('/auth/kite/callback?status=success&request_token=x&state=y').status_code, 401)
            exchange.assert_not_called()

    def test_kite_callback_accepts_cross_site_document_navigation(self):
        with patch.multiple(config, KITE_API_KEY='test-kite-key', KITE_REDIRECT_URL=ORIGIN + '/auth/kite/callback'):
            sign_in(self.client)
            self.client.post('/auth/kite/login')
            state = self.client.cookies['kite_oauth_state']
            del self.client.headers['Origin']
            with patch('app.provider.create_kite_session', return_value='provider-secret') as exchange, patch.object(main.connections, 'accept_kite') as accept:
                response = self.client.get('/auth/kite/callback', params={'request_token': 'test-request', 'status': 'success', 'state': state},
                    headers={'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}, follow_redirects=False)
                self.assertEqual(response.status_code, 307, response.text)
                exchange.assert_called_once_with('test-request')
                accept.assert_called_once_with('provider-secret')

    def test_oauth_state_is_bound_to_the_admin_session(self):
        with patch.multiple(config, KITE_API_KEY='test-kite-key', KITE_REDIRECT_URL=ORIGIN + '/auth/kite/callback'):
            sign_in(self.client)
            self.client.post('/auth/kite/login')
            state = self.client.cookies['kite_oauth_state']
            other = TestClient(main.app, base_url=ORIGIN, client=('198.51.100.20', 4000))
            self.addCleanup(other.close)
            sign_in(other)
            other.cookies.set('kite_oauth_state', state)
            with patch('app.provider.create_kite_session') as exchange:
                result = other.get('/auth/kite/callback', params={'request_token': 'test', 'status': 'success', 'state': state})
                self.assertEqual(result.status_code, 400)
                exchange.assert_not_called()

    def test_watchlist_update_uses_authenticated_admin_session(self):
        sign_in(self.client)
        with patch('app.main.save_watchlist', return_value=['NSE:RELIANCE']) as save:
            response = self.client.put('/api/watchlist', json={'symbols': 'NSE:RELIANCE'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['symbols'], ['NSE:RELIANCE'])
        save.assert_called_once_with('NSE:RELIANCE')

    def test_database_contains_hashes_and_no_raw_session_credentials(self):
        sign_in(self.client)
        raw = self.client.cookies[COOKIE]
        with auth.database() as db:
            self.assertEqual(db.execute('SELECT id FROM admin_sessions').fetchone()[0], digest(raw))
        for secret in [raw, PASSWORD, config.ADMIN_TOKEN]:
            self.assertNotIn(secret.encode(), Path(config.ADMIN_SESSION_DATABASE_PATH).read_bytes())

    def test_sessions_work_across_worker_instances(self):
        sign_in(self.client)
        with patch.object(main, 'admin_auth', AdminAuth()):
            self.assertEqual(self.client.post('/api/scan').status_code, 200)

    def test_admin_credentials_redacted_from_logs(self):
        record = logging.LogRecord('uvicorn.access', 20, 'test', 1, 'key %s hash %s Authorization: Bearer private', (config.ADMIN_TOKEN, config.ADMIN_PASSWORD_HASH), None)
        CredentialFilter().filter(record)
        for secret in [config.ADMIN_TOKEN, config.ADMIN_PASSWORD_HASH, 'private']:
            self.assertNotIn(secret, record.getMessage())

    def test_frontend_has_no_admin_bearer_flow(self):
        code = (config.ROOT / 'static/app.js').read_text(encoding='utf-8') + (config.ROOT / 'static/admin-auth.js').read_text(encoding='utf-8')
        for value in ['ADMIN_TOKEN', 'state.admin', 'adminToken', 'Bearer ']:
            self.assertNotIn(value, code)

    def test_nested_log_arguments_and_exception_text_redact_admin_key(self):
        try:
            raise RuntimeError(config.ADMIN_TOKEN)
        except RuntimeError:
            record = logging.LogRecord('test', 40, 'test', 1, 'failure %s', ({'nested': [config.ADMIN_TOKEN.encode()]},), sys.exc_info())
        CredentialFilter().filter(record)
        self.assertNotIn(config.ADMIN_TOKEN, logging.Formatter('%(message)s').format(record))

    def test_password_hashing_validation(self):
        encoded = hash_password(PASSWORD)
        self.assertTrue(verify_password(PASSWORD, encoded))
        self.assertFalse(verify_password('incorrect', encoded))
        self.assertFalse(verify_password(PASSWORD, 'scrypt$bad'))
        with self.assertRaises(ValueError):
            hash_password('short')
