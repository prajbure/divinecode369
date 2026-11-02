"""Remote scan authorization uses the browser's verified Kite login."""
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, main


class ScanAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(
            config, ADMIN_TOKEN='', KITE_API_KEY='test-api-key',
            KITE_ACCESS_TOKEN='test-kite-session',
            KITE_REDIRECT_URL='https://terminal.example/auth/kite/callback',
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)
        scan_patch = patch.object(main.market, 'scan', return_value={'rows': [], 'matches': []})
        self.scan = scan_patch.start()
        self.addCleanup(scan_patch.stop)
        self.client = TestClient(main.app, base_url='https://terminal.example', client=('198.51.100.10', 4000))
        self.addCleanup(self.client.close)

    def login(self):
        login = self.client.get('/auth/kite/login', follow_redirects=False)
        with patch('app.provider.create_kite_session', return_value='test-kite-session'), patch.object(main.connections,'accept_kite'):
            return self.client.get('/auth/kite/callback', params={
                'request_token': 'test-request', 'status': 'success',
                'state': login.cookies['kite_oauth_state'],
            }, follow_redirects=False)

    def test_verified_kite_browser_can_scan_after_navigation(self):
        response = self.login()
        self.assertEqual(response.status_code, 307)
        cookie = response.headers.get('set-cookie', '')
        self.assertIn('divine_scan_session=', cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('Secure', cookie)
        self.client.get('/scanner')
        result = self.client.post('/api/scan', headers={'Origin': 'https://terminal.example'})
        self.assertEqual(result.status_code, 200, result.text)
        self.scan.assert_called_once()

    def test_connected_server_does_not_authorize_another_browser(self):
        result = self.client.post('/api/scan')
        self.assertEqual(result.status_code, 403)
        self.scan.assert_not_called()

    def test_scan_session_does_not_authorize_administration(self):
        self.login()
        result = self.client.put('/api/watchlist', json={'symbols': 'NSE:RELIANCE'})
        self.assertEqual(result.status_code, 403)

    def test_cross_origin_scan_is_rejected_even_after_login(self):
        self.login()
        result = self.client.post('/api/scan', headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(result.status_code, 403)
        self.scan.assert_not_called()

    def test_changed_kite_session_revokes_browser_scan_access(self):
        self.login()
        with patch.object(config, 'KITE_ACCESS_TOKEN', 'another-kite-session'):
            result = self.client.post('/api/scan')
        self.assertEqual(result.status_code, 403)
        self.scan.assert_not_called()

    def test_expired_scan_session_is_rejected(self):
        self.login()
        with patch('app.main.time.time', return_value=time.time() + 86400):
            result = self.client.post('/api/scan')
        self.assertEqual(result.status_code, 403)
        self.scan.assert_not_called()

    def test_tampered_scan_session_is_rejected(self):
        self.login()
        self.client.cookies.set('divine_scan_session', 'invalid.signature', domain='terminal.example', path='/')
        self.assertEqual(self.client.post('/api/scan').status_code, 403)
        self.scan.assert_not_called()

    def test_invalid_kite_callback_cannot_grant_scan_access(self):
        result = self.client.get('/auth/kite/callback', params={
            'request_token': 'test-request', 'status': 'success', 'state': 'invalid',
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.client.post('/api/scan').status_code, 403)
        self.scan.assert_not_called()

    def test_remote_admin_token_still_authorizes_scanning(self):
        with patch.object(config, 'ADMIN_TOKEN', 'test-admin-token'):
            result = self.client.post('/api/scan', headers={'Authorization': 'Bearer test-admin-token'})
        self.assertEqual(result.status_code, 200)
        self.scan.assert_called_once()

    def test_localhost_still_authorizes_scanning(self):
        client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 4000))
        self.addCleanup(client.close)
        result = client.post('/api/scan')
        self.assertEqual(result.status_code, 200)


if __name__ == '__main__':
    unittest.main()
