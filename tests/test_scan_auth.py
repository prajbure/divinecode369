"""Scans require an administrator session; Kite and loopback grant no exemption."""
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import config, main
from tests.auth_helpers import ORIGIN, admin_environment, sign_in


class ScanAuthorizationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(admin_environment(folder.name))
        self.scan = self.enterContext(patch.object(main.market, 'scan', return_value={'rows': []}))
        self.client = TestClient(main.app, base_url=ORIGIN, client=('198.51.100.10', 4000))
        self.addCleanup(self.client.close)

    def test_authenticated_scan_survives_navigation(self):
        sign_in(self.client)
        self.client.get('/scanner')
        self.assertEqual(self.client.post('/api/scan').status_code, 200)
        self.scan.assert_called_once()

    def test_kite_cookie_and_backend_bearer_token_cannot_authorize_scan(self):
        self.client.cookies.set('divine_scan_session', 'legacy.signature')
        self.assertEqual(self.client.post('/api/scan', headers={'Authorization': 'Bearer ' + config.ADMIN_TOKEN}).status_code, 401)
        self.scan.assert_not_called()

    def test_actual_loopback_requires_authentication(self):
        client = TestClient(main.app, base_url='https://localhost', client=('127.0.0.1', 4000))
        self.addCleanup(client.close)
        self.assertEqual(client.post('/api/scan').status_code, 401)

    def test_scan_requires_csrf_and_same_origin(self):
        sign_in(self.client)
        self.assertEqual(self.client.post('/api/scan', headers={'Origin': 'https://evil.example'}).status_code, 403)
        del self.client.headers['X-CSRF-Token']
        self.assertEqual(self.client.post('/api/scan').status_code, 403)
        self.scan.assert_not_called()
