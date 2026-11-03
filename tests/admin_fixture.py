"""Isolated HTTPS browser fixture. Never starts provider workers or uses live credentials."""
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import quote

import uvicorn
from fastapi.responses import HTMLResponse

from app import config, main
from app.market import MarketService
from app.ipoguru import IPOGuruClient
from app.predictions import PredictionLab
from app.scanner import reference_groups
from app.storage import Store
from tests.auth_helpers import admin_environment


@asynccontextmanager
async def fixture_lifespan(app):
    yield


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as folder, admin_environment(folder, origin='https://localhost:8443'), patch.multiple(config, KITE_API_KEY='synthetic-browser-fixture', KITE_REDIRECT_URL='https://localhost:8443/auth/kite/callback', KITE_API_SECRET='', KITE_ACCESS_TOKEN='', IPOGURU_API_KEY='', IPOGURU_ENABLED=False):
        store = Store(Path(folder) / 'market.sqlite3')
        store.initialize(reference_groups())
        market = MarketService(store)
        ipo_client = IPOGuruClient(key='', enabled=False, quota_path=Path(folder) / 'quota.sqlite3')
        main.app.router.lifespan_context = fixture_lifespan
        with patch.multiple(main, store=store, market=market, lab=PredictionLab(store)), patch.object(main.ipo_service, 'client', ipo_client), patch.object(main.connections, 'snapshot', return_value={'kite': {'name': 'Zerodha Kite', 'state': 'disconnected', 'authentication': 'unverified', 'network': 'unknown'}, 'ipoguru': {'name': 'IPO Guru', 'state': 'api_key_missing', 'authentication': 'unverified', 'network': 'unknown'}, 'summary': 'attention', 'ipo_generation': 0}), patch.object(market, 'scan', return_value={'rows': [], 'matches': []}), patch('app.provider.create_kite_session', return_value='synthetic-provider-session') as exchange, patch.object(main.connections, 'accept_kite') as accept:
            @main.app.get('/_test/provider-return', include_in_schema=False)
            def provider_return(state: str):
                target = 'https://localhost:8443/auth/kite/callback?status=success&request_token=synthetic-code&state=' + quote(state, safe='')
                return HTMLResponse('<a id="providerReturn" href="' + target + '">Return from simulated provider</a>')

            @main.app.get('/_test/provider-calls', include_in_schema=False)
            def provider_calls():
                return {'exchanges': exchange.call_count, 'accepted': accept.call_count}

            uvicorn.run(main.app, host='127.0.0.1', port=8443,
                        ssl_keyfile='.qa/admin-auth/key.pem', ssl_certfile='.qa/admin-auth/cert.pem',
                        access_log=False)
