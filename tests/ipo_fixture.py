"""Generate labelled browser-test fixtures through the actual backend service.

Only this explicit test command creates the .qa file. No production fixture route.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock
from pathlib import Path
from app.ipo_service import IPOService
from app.ipoguru import STANDARD_SCOPES, IST


def fixture_data():
    now=datetime.now(timezone.utc)
    today=now.astimezone(IST).date()
    day=lambda delta:(today+timedelta(days=delta)).isoformat()
    stamp=now.isoformat()
    rows=[]
    for index,(name,board,status,listed,opening,closing,allotment,listing) in enumerate([
        ('Aster Engineering','Mainboard','Open',False,-1,2,5,8),
        ('Bluefield Logistics','SME','Upcoming',False,3,6,9,12),
        ('Cedar Technologies','Mainboard','Closed',False,-6,-2,1,4),
        ('Delta Manufacturing','Mainboard','Closed',True,-15,-12,-9,-6),
        ('Emerald Foods','SME','Open',False,0,3,6,9),
        ('Falcon Infrastructure','Mainboard','Upcoming',False,7,10,13,16),
        ('Granite Materials','SME','Closed',False,-7,-3,0,3)]):
        rows.append({'slug':name.lower().replace(' ','-')+'-test-ipo','name':'TEST FIXTURE · '+name,
            'type':board,'status':status,'is_listed':listed,'open_date':day(opening),'close_date':day(closing),
            'allotment_date':day(allotment),'listing_date':day(listing),'price_band':'190–200',
            'price_min':190,'price_max':200,'issue_price':'200','issue_size':'450.50','lot_size':75,'min_investment':15000,
            'gmp':{'price':str(40-index*8),'updated_at':stamp},'subscription_total':str(5.25+index),
            'listing_price':'244' if listed else None,'cmp':'251' if listed else None})
    def detail(row):
        raw=deepcopy(row)
        raw['issue']={key:row.get(key) for key in ('price_min','price_max','issue_price','issue_size','lot_size','min_investment','price_band')}
        raw['issue'].update({'face_value':'10','sale_type':'Fresh issue and OFS','listing_on':'NSE, BSE'})
        raw['timeline']={key:row.get(key) for key in ('open_date','close_date','allotment_date','listing_date')}
        raw['timeline'].update({'refund_date':day(6),'credit_to_demat_date':day(7)})
        raw['company']={'about':'TEST FIXTURE company used exclusively for automated interface validation. These are synthetic financial figures, not investment data.',
            'strengths':['TEST FIXTURE · Reported revenue growth','TEST FIXTURE · Diversified customer base'],
            'risks':['TEST FIXTURE · Customer concentration','TEST FIXTURE · Raw material price sensitivity'],
            'financials':{'headers':['31 Mar 2026','31 Mar 2025','31 Mar 2024'],'unit':'₹ crore (TEST FIXTURE)',
                'rows':[{'metric':'Revenue','data':['325.5','275.0','220.0']},{'metric':'Profit after tax','data':['32','26','20']},
                        {'metric':'Assets','data':['410','360','320']},{'metric':'Borrowings','data':['75','80','82']}]},
            'kpis':[{'metric':'EPS','value':'8.5'},{'metric':'P/E','value':'23.53'},{'metric':'ROE','value':'18%'}],
            'promoters':['TEST FIXTURE founder'],'objects_of_issue':{'items':['TEST FIXTURE · Capacity expansion','TEST FIXTURE · Debt repayment']}}
        raw['contacts']={'registrar':{'name':'Bigshare Services (test link validation)','status_page':'https://ipo.bigshareonline.com/ipo_status.html'}}
        raw['documents']={}
        return raw
    fixtures={}
    def get(path,scope,**kwargs):
        if path=='/ipos':data=rows
        elif path=='/gmp':data=rows
        else:
            slug=path.split('/')[2]
            row=next(v for v in rows if v['slug']==slug)
            if path.endswith('/gmp/history'):
                data={'summary':{'issue_price':200},'trend':[{'date':day((-13 if row['is_listed'] else -6)+i),'price_value':20+i*3,'price':str(20+i*3)} for i in range(7)],'timeline':[]}
            elif path.endswith('/subscription'):
                data={'summary':{'total':'5.25','updated_at':stamp},'applications_source':'TEST FIXTURE',
                    'categories':[{'key':key,'label':label,'times_value':value,'shares_offered':'1000000','shares_applied':str(int(value*1000000))} for key,label,value in [('QIB','Qualified Institutional Buyers',8.5),('NII','Non-Institutional Investors',6.2),('RETAIL','Retail',3.75),('EMPLOYEE','Employee',0),('SHAREHOLDER','Shareholder',1.25),('TOTAL','Total',5.25)]]}
            elif path.endswith('/anchors'):
                data={'summary':{'total_anchors':2,'total_amount_cr':125,'mutual_fund_count':1},'anchors':[{'name':'TEST FIXTURE Anchor Fund','group_entity':'TEST FIXTURE Fund Group','shares_allotted':100000,'amount_cr':20,'pct_allocated':16}]}
            else:data=detail(row)
        return {'data':deepcopy(data),'meta':{'available':True,'cache_stale':False,'cache_hit':True,'fetched_at':stamp,'cache_age_seconds':0,'error':None}}
    client=Mock()
    client.get.side_effect=get
    client.status.return_value={'enabled':True,'configured':True,'verified':True,'plan':'standard (TEST FIXTURE)',
        'scopes':sorted(STANDARD_SCOPES),'limits':{'per_day':1000,'per_minute':20},'quota':{'remaining':987},'cache_seconds':900}
    service=IPOService(client)
    fixtures['/api/ipo/overview']=service.overview()
    for row in rows:
        base='/api/ipo/details/'+row['slug']
        fixtures[base]=service.detail(row['slug'])
        for kind in ('history','subscription','anchors'):fixtures[base+'/'+kind]=service.resource(row['slug'],kind)
    return fixtures


if __name__=='__main__':
    destination=Path('.qa/ipo-fixtures.json')
    destination.write_text(json.dumps(fixture_data()),encoding='utf-8')
    print('Labelled TEST FIXTURE payloads generated; no real provider requests.')
