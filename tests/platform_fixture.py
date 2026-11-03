"""Synthetic HTTPS platform fixture. No live provider calls or background workers."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
from unittest.mock import Mock,patch
import uvicorn
from app import main,config
from app.connections import ConnectionManager
from app.ipo_service import IPOService
from app.ipoguru import IPOGuruClient
from app.market import MarketService
from app.scanner import reference_groups
from app.storage import Store
from tests.auth_helpers import admin_environment
from tests.test_ipo import ACCOUNT,response

@asynccontextmanager
async def lifespan(app):yield

def fixture_rows():
    now=datetime.now(timezone.utc);day=now.date()
    rows=[]
    for i,(name,board,status,stage) in enumerate([('Atlas Industries','Mainboard','Open',None),('Aurora Engineering','SME','Open',None),('Vector Power','Mainboard','Upcoming',None),('Pioneer Components','SME','Upcoming',None),('Meridian Systems','Mainboard','Closed','Allotted'),('Terra Logistics','SME','Closed',None)]):
        rows.append({'slug':'fixture-ipo-'+str(i),'name':'TEST FIXTURE '+name,'type':board,'status':status,'stage':stage,
                     'issue':{'price_min':90,'price_max':100,'price_band':'₹90 – ₹100','issue_price':100,'lot_size':100,'listing_on':'NSE','issue_size':400},
                     'timeline':{'open_date':(day-timedelta(days=1) if status=='Open' else day+timedelta(days=4)).isoformat(),'close_date':(day+timedelta(days=1)).isoformat(),'allotment_date':(day+timedelta(days=4)).isoformat(),'listing_date':(day+timedelta(days=6)).isoformat()},
                     'gmp':{'price':10 if i else None,'updated_at':now.isoformat()},'subscription_total':3.5 if i else None,
                     'company':{'about':'Synthetic company information for deterministic QA.','financials':{'headers':['FY2025','FY2026'],'unit':'₹ crore','rows':[{'metric':'Revenue','data':[100,120]},{'metric':'Profit','data':[10,12]}]},'risks':['Synthetic risk fixture']},
                     'contacts':{'registrar':{'name':'Verified test registrar','status_page':'https://www.bigshareonline.com/ipo_Allotment.html'}}})
    return rows

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as folder,admin_environment(folder,origin='https://localhost:8443'),patch.multiple(config,PLATFORM_DATABASE_PATH=Path(folder)/'platform.sqlite3',KITE_API_KEY='',KITE_API_SECRET='',KITE_ACCESS_TOKEN='',IPOGURU_API_KEY='',IPOGURU_ENABLED=False):
        store=Store(Path(folder)/'market.sqlite3');store.initialize(reference_groups())
        market=MarketService(store);rows=fixture_rows();http=Mock()
        def provider(url,**kwargs):
            path=url.split('/api/v2')[-1]
            if path=='/me':return response(ACCOUNT)
            if path=='/ipos':return response(rows)
            if path=='/gmp':return response([])
            if path.endswith('/gmp/history'):return response({'trend':[{'date':(datetime.now(timezone.utc).date()-timedelta(days=i)).isoformat(),'price':10-i} for i in range(4)],'summary':{'issue_price':100}})
            if path.endswith('/subscription'):return response({'summary':{'qib':2,'nii':3,'retail':4,'total':3.5,'updated_at':datetime.now(timezone.utc).isoformat()}})
            return response(next((r for r in rows if r['slug']==path.split('/')[-1]),{}))
        http.get.side_effect=provider
        service=IPOService(IPOGuruClient(key='synthetic-ipo-key',enabled=True,session=http,quota_path=Path(folder)/'quota.sqlite3'))
        manager=ConnectionManager(market,service);manager.overview=service.overview()
        main.app.router.lifespan_context=lifespan
        with patch.object(main.ipo_service,'client',service.client),patch.object(main.connections,'overview',manager.overview),patch.multiple(main,store=store,market=market,ipo_service=service,connections=manager),patch.object(market,'scan',return_value={'rows':[]}):
            uvicorn.run(main.app,host='127.0.0.1',port=8443,ssl_keyfile='.qa/admin-auth/key.pem',ssl_certfile='.qa/admin-auth/cert.pem',access_log=False)
