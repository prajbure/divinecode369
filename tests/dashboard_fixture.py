"""Loopback-only dashboard fixture. Real scanner math; no provider traffic or workers."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest.mock import patch

import uvicorn
from app import config, main
from app.market import MarketService
from app.predictions import PredictionLab
from app.scanner import reference_groups, run_scan
from app.storage import Store
from tests.auth_helpers import admin_environment


@asynccontextmanager
async def lifespan(app):
    yield


def serve():
    scenario = {'value': 'initial', 'sequence': 1}
    groups = reference_groups()
    symbols = list(dict.fromkeys([stock[0] for group in groups for stock in group['stocks']]))
    selected = list(dict.fromkeys(symbols[:8] + ['BPCL', 'LODHA']))
    now = datetime.now(timezone.utc).isoformat()

    def snapshot():
        quotes = []
        pagination = scenario['value'].startswith('pagination')
        for i, symbol in enumerate(symbols[:11] if pagination else selected):
            # All data below is synthetic and exists only in this test server.
            difference = [0, 2, 20, -3][i % 4]
            if scenario['value'] == 'updated' and i == 0:
                difference = 25
            quotes.append({'symbol': symbol, 'exchange': 'NSE', 'open': 100 + difference,
                           'prev_close': 100, 'ltp': 101 if i % 2 == 0 else 99,
                           'change_pct': (1 if i < (10 if scenario['value'] == 'pagination-shrink' else 11) else -1) if pagination else (1 if i % 2 == 0 else -1),
                           'volume': 1000 + i * 100, 'quote_timestamp': now})
        result = run_scan(['NSE:' + quote['symbol'] for quote in quotes],
                          quote_payload={'data': quotes, 'meta': {'as_of': now}})
        for i, row in enumerate(result['rows']):
            row.update(quote_status=['live', 'stale', 'closed', 'unknown'][i % 4], opening_date=now[:10])
        rows = [] if scenario['value'] == 'empty' else result['rows']
        return {'sequence': scenario['sequence'], 'rows': deepcopy(rows), 'top_performers': [],
                'as_of': now, 'scan_as_of': now, 'opening_date': now[:10],
                'market': {'status': 'open', 'is_open': True, 'label': 'TEST FIXTURE', 'calendar_verified': True, 'trading_date': now[:10]},
                'transport': 'test-fixture', 'stream_connected': True, 'token_configured': True,
                'max_difference': config.MAX_DIFFERENCE, 'error': None, 'stream_error': None,
                'instrument_status': {}, 'instrument_resolutions': {}}

    with tempfile.TemporaryDirectory() as folder, admin_environment(folder, origin='https://localhost:8443'), patch.multiple(
        config, KITE_API_KEY='', KITE_API_SECRET='', KITE_ACCESS_TOKEN='', IPOGURU_API_KEY='', IPOGURU_ENABLED=False, MAX_DIFFERENCE=10,
        PLATFORM_DATABASE_PATH=Path(folder) / 'platform.sqlite3'):
        store = Store(Path(folder) / 'market.sqlite3')
        store.initialize(groups)
        market = MarketService(store)
        main.app.router.lifespan_context = lifespan
        with patch.multiple(main, market=market, store=store, lab=PredictionLab(store)), patch.object(market, 'snapshot', side_effect=snapshot), patch.object(
            market, 'scan', side_effect=snapshot), patch.object(main.connections, 'snapshot', return_value={
                'kite': {'name': 'Zerodha Kite', 'state': 'disconnected'},
                'ipoguru': {'name': 'IPO Guru', 'state': 'api_key_missing'}, 'summary': 'attention', 'ipo_generation': 0}):
            @main.app.post('/_test/dashboard/{value}', include_in_schema=False)
            def change_fixture(value: str):
                if value in {'initial', 'updated', 'empty', 'pagination', 'pagination-shrink'}:
                    scenario.update(value=value, sequence=scenario['sequence'] + 1)
                return {'scenario': scenario['value'], 'sequence': scenario['sequence']}

            uvicorn.run(main.app, host='127.0.0.1', port=8443,
                        ssl_keyfile='.qa/admin-auth/key.pem', ssl_certfile='.qa/admin-auth/cert.pem', access_log=False)


if __name__ == '__main__':
    serve()
