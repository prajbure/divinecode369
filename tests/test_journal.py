from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import config, main
from app.advanced import create_router
from app.journal import Journal, summary
from app.scanner import reference_groups
from app.storage import Store


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'private.sqlite3');self.store.initialize(reference_groups())
        self.journal=Journal(self.store)

    def body(self,**changes):
        return {'traded_at':'2026-11-02T10:00','symbol':'NSE:HDFCBANK','sector':'banking','setup':'Opening match',
                'side':'long','entry':'100','exit':'110','quantity':10,'charges':'10','notes':'Manual fixture','lessons':'',**changes}

    def test_realized_pnl_and_open_trades(self):
        self.assertEqual(self.journal.save(self.body())['realized_pnl'],'90.00')
        self.assertEqual(self.journal.save(self.body(side='short',exit='90'))['realized_pnl'],'90.00')
        self.assertIsNone(self.journal.save(self.body(exit=''))['realized_pnl'])

    def test_journal_analytics_use_closed_net_results(self):
        self.journal.save(self.body());self.journal.save(self.body(exit='95'));self.journal.save(self.body(exit=None))
        result=summary(self.journal.records())
        self.assertEqual(result['realized_pnl'],'30.00');self.assertEqual(result['win_rate'],50)
        self.assertEqual(result['expectancy'],'15.00');self.assertEqual(result['profit_factor'],1.5)
        self.assertEqual(result['open_trades'],1);self.assertEqual(result['by_trading_time'][0]['group'],'10:00 IST')

    def test_decimal_pnl_avoids_float_rounding(self):
        result=self.journal.save(self.body(entry='10.01',exit='10.03',quantity=3,charges='0.01'))
        self.assertEqual(result['realized_pnl'],'0.05')

    def test_idempotent_create_edit_delete_preserve_market_tables(self):
        row=self.journal.save(self.body());self.journal.save(self.body(id=row['id']))
        self.assertEqual(len(self.journal.records()),1)
        self.assertEqual(self.journal.save(self.body(exit='120'),row['id'])['realized_pnl'],'190.00')
        self.journal.delete(row['id']);self.assertEqual(self.journal.records(),[])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM instruments').fetchone()[0],148)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sector_memberships').fetchone()[0],160)
        self.assertEqual(self.store.overview()['candles'],0)

    def test_invalid_symbols_amounts_and_memberships_rejected(self):
        for change in [{'symbol':'NSE:NEWSTOCK'},{'entry':'NaN'},{'quantity':1.2},{'quantity':True},{'charges':'-1'},{'sector':'telecom'},{'entry':'0'},{'traded_at':'invalid'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):self.journal.save(self.body(**change))

    def test_journal_export_escapes_spreadsheet_formulas(self):
        self.journal.save(self.body(notes='=HYPERLINK("bad")'))
        self.assertIn("'=HYPERLINK",self.journal.export())

    def test_journal_and_context_routes_keep_access_and_retention_gates(self):
        from app.admin_auth import router as admin_router
        from tests.auth_helpers import ORIGIN, admin_environment, sign_in
        app=FastAPI();app.include_router(create_router(self.store,main.require_admin))
        app.include_router(admin_router)
        with admin_environment(self.temp.name),TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1000)) as client,patch.object(config,'DATA_RETENTION_AUTHORIZED',False):
            sign_in(client)
            self.assertEqual(client.post('/api/journal',json=self.body()).status_code,201)
            self.assertEqual(client.get('/api/journal').json()['analytics']['realized_pnl'],'90.00')
            self.assertEqual(client.get('/api/journal/export').status_code,200)
            with patch('app.provider.historical_candles') as download:
                self.assertFalse(client.get('/api/intelligence/context/NSE:HDFCBANK').json()['enabled']);download.assert_not_called()
        with TestClient(app,base_url='https://remote.example',client=('198.51.100.1',1000)) as client,patch.object(config,'ADMIN_TOKEN',''):
            self.assertEqual(client.get('/api/journal').status_code,401)
            self.assertEqual(client.post('/api/journal',json=self.body()).status_code,401)


if __name__=='__main__':unittest.main()
