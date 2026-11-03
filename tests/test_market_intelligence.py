from datetime import datetime,timedelta,timezone
import json
import random
import subprocess
import unittest
from app.market_intelligence import Analytics,DEFAULT_WEIGHTS,sector_metrics,regime,opening,opportunity
from app.mobile_auth import RequestLimits


class SharedAnalyticsTests(unittest.TestCase):
    def test_existing_javascript_numeric_rule_parity(self):
        rng=random.Random(369);fixtures=[]
        for case in range(20):
            groups=[{'id':'fixture','name':'Fixture','stocks':[['A'],['A'],['B'],['C'],['D']]}]
            rows=[]
            for i,symbol in enumerate('ABCD'):
                rows.append({'symbol':'NSE:'+symbol,'name':symbol,'ltp':100+rng.uniform(-4,4),'change_pct':rng.uniform(-3,3),'open':100+rng.uniform(-2,2),'prev_close':100,
                             'match':case%3==0,'near_match':case%3==1,'difference':case%3,'quote_status':'live' if case%4 else 'stale',
                             'quote_timestamp':'2026-11-02T10:00:00+05:30','opening_date':'2026-11-02','volume':1000+i*200,'day_high':105,'day_low':95,
                             'vwap':100 if case%2 else None,'vwap_source':'Kite average traded price','best_bid':99,'best_ask':100,'depth_bid_quantity':100,'depth_ask_quantity':150})
            start=datetime.fromisoformat('2026-11-02T09:15:00+05:30')
            bars=[{'timestamp':(start+timedelta(minutes=i)).isoformat(),'interval':'minute','source':'kite','open':100,'high':102+i*.1,'low':99+i*.1,'close':101+i*.1,'volume':100} for i in range(20 if case%2 else 4)]
            context={'session_date':'2026-11-02','previous_session_date':'2026-10-30','minutes':bars,'daily':[]}
            sequence=[{**rows[0],'quote_status':'live','volume':1000+i*i*100,'quote_timestamp':f'2026-11-02T10:00:{i*10:02d}+05:30'} for i in range(4)]
            fixtures.append({'groups':groups,'rows':rows,'context':context,'session':{'calendar_verified':True,'is_trading_day':True,'trading_date':'2026-11-02','opening_time':'09:15:00'},'now':'2026-11-02T10:00:00+05:30','weights':DEFAULT_WEIGHTS,'sequence':sequence})
        result=subprocess.run(['node','tests/analytics-parity.mjs'],input=json.dumps(fixtures),capture_output=True,text=True,check=True)
        expected=json.loads(result.stdout)
        for f,wanted in zip(fixtures,expected):
            sectors=[sector_metrics(g,f['rows']) for g in f['groups']]
            analyses=[opening(r,f['context'],f['session'],datetime.fromisoformat(f['now'])) for r in f['rows']]
            tracker=Analytics()
            actual={'sectors':sectors,'regime':regime(f['groups'],f['rows']),'openings':analyses,
                    'opportunities':[opportunity(r,f['groups'],sectors,a,{},DEFAULT_WEIGHTS) for r,a in zip(f['rows'],analyses)],'volumes':[tracker.volume(r) for r in f['sequence']]}
            self.compare_values(wanted,actual)

    def compare_values(self,wanted,actual,path=''):
        if isinstance(wanted,str):return # Narrative wording and ISO formatting may be shorter.
        if isinstance(wanted,dict):
            for k,v in wanted.items():self.assertIn(k,actual,path);self.compare_values(v,actual[k],path+'.'+k)
        elif isinstance(wanted,list):
            if wanted and isinstance(wanted[0],str):return
            self.assertEqual(len(wanted),len(actual),path)
            for i,(a,b) in enumerate(zip(wanted,actual)):self.compare_values(a,b,path+str(i))
        elif isinstance(wanted,(int,float)) and not isinstance(wanted,bool):self.assertAlmostEqual(wanted,actual,places=8,msg=path)
        else:self.assertEqual(wanted,actual,path)

    def test_bounded_peer_rate_limit_and_window_reset(self):
        limits=RequestLimits()
        self.assertTrue(all(limits.allow('peer',True,now=0) for _ in range(60)))
        self.assertFalse(limits.allow('peer',True,now=0))
        self.assertTrue(limits.allow('peer',True,now=60))
        self.assertTrue(all(limits.allow('peer',False,now=60) for _ in range(300)))
        self.assertFalse(limits.allow('peer',False,now=60))


if __name__=='__main__':unittest.main()
