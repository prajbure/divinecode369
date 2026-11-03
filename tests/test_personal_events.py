from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import config,personal
from app.ipo_comparison import listing_comparison
from app.mobile_models import AlertRule
from app.market_intelligence import Analytics

class PersonalEventTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.enterContext(patch.object(config,'PLATFORM_DATABASE_PATH',Path(folder.name)/'platform.sqlite3'))
        self.now=datetime.now(timezone.utc);self.source=self.now.isoformat()
        self.ipo={'slug':'fixture-ipo','name':'Fixture','timeline':{},'gmp':{'price':10,'freshness':{'as_of':self.source,'status':'recent'}}}

    def test_gmp_change_needs_baseline_recent_source_and_threshold(self):
        personal.save_rule('owner',AlertRule(ipo_slug='fixture-ipo',event='gmp_change',threshold=5))
        snapshot={'rows':[self.ipo]};personal.evaluate(snapshot,self.now)
        self.assertEqual(personal.inbox('owner')['items'],[])
        self.ipo['gmp']['price']=12;personal.evaluate(snapshot,self.now)
        self.assertEqual(personal.inbox('owner')['items'],[])
        self.ipo['gmp']['price']=15;self.ipo['gmp']['freshness']['status']='stale';personal.evaluate(snapshot,self.now)
        self.assertEqual(personal.inbox('owner')['items'],[])
        self.ipo['gmp']['freshness']['status']='recent';personal.evaluate(snapshot,self.now);personal.evaluate(snapshot,self.now)
        self.assertEqual(len(personal.inbox('owner')['items']),1)

    def test_subscription_alert_uses_only_verified_cached_category_source(self):
        personal.save_rule('owner',AlertRule(ipo_slug='fixture-ipo',event='subscription_threshold',threshold=2))
        snapshot={'rows':[self.ipo]};personal.evaluate(snapshot,self.now)
        self.assertEqual(personal.inbox('owner')['items'],[])
        resource={'fixture-ipo':{'categories':[{'key':'TOTAL','times':3}],'freshness':{'status':'recent','as_of':self.source}}}
        personal.evaluate(snapshot,self.now,subscriptions=resource)
        events=personal.inbox('owner')['items'];self.assertEqual(len(events),1);self.assertEqual(events[0]['source_timestamp'],self.source)
        self.assertNotIn('times',events[0]);self.assertNotIn('price',events[0])

    def test_stock_alerts_use_fresh_server_classification_and_deduplicate(self):
        personal.save_rule('owner',AlertRule(kind='stock',symbol='NSE:RELIANCE',event='exact'))
        quote={'symbol':'NSE:RELIANCE','match':True,'near_match':False,'ltp':100,'quote_status':'stale','quote_timestamp':self.source}
        market={'rows':[quote],'market':{'is_open':True}}
        personal.evaluate({'rows':[]},self.now,market=market);self.assertEqual(personal.inbox('owner')['items'],[])
        quote['quote_status']='live';personal.evaluate({'rows':[]},self.now,market=market);personal.evaluate({'rows':[]},self.now,market=market)
        events=personal.inbox('owner')['items'];self.assertEqual(len(events),1);self.assertEqual(events[0]['symbol'],'NSE:RELIANCE')
        self.assertEqual(events[0]['kind'],'stock');self.assertNotIn('ltp',events[0])

    def test_alert_deletion_persists_tombstone_and_invalid_targets_fail(self):
        from fastapi import HTTPException
        created=personal.save_rule('owner',AlertRule(ipo_slug='fixture-ipo',event='opens'))['items'][0]
        personal.delete_rule('owner',created['id'])
        self.assertTrue(personal.rules('owner')['items'][0]['deleted'])
        self.assertRaises(HTTPException,personal.save_rule,'owner',AlertRule(kind='stock',symbol='NSE:FAKE',event='exact'))
        self.assertRaises(ValueError,AlertRule,ipo_slug='fixture-ipo',event='exact')

    def test_archived_listing_comparison_keeps_original_rules(self):
        ipo={'is_listed':True,'listing':{'price':120},'issue':{'issue_price':100,'price_max':105},'timeline':{'listing_date':'2026-11-03'}}
        history={'issue_price':105,'trend':[{'date':'2026-11-02','price':10},{'date':'2026-11-03','price':99}]}
        result=listing_comparison(ipo,history)
        self.assertTrue(result['available']);self.assertEqual(result['estimate'],115);self.assertEqual(result['actual_gain'],20)
        self.assertEqual(result['date'],'2026-11-02')
        history['issue_price']=100;self.assertFalse(listing_comparison(ipo,history)['available'])
        history['issue_price']=105;history['trend']=[{'date':'2026-11-03','price':10}]
        self.assertFalse(listing_comparison(ipo,history)['available'])

    def test_client_reads_do_not_change_sampling_windows(self):
        groups=[{'id':'fixture','name':'Fixture','stocks':[['A']]}]
        row={'symbol':'NSE:A','ltp':100,'open':100,'prev_close':100,'change_pct':0,'quote_status':'live','quote_timestamp':self.source,'volume':1000}
        snapshot={'rows':[row],'market':{},'transport':'streaming'};engine=Analytics();engine.observe_snapshot(snapshot)
        original=deepcopy(engine.samples)
        for _ in range(5):engine.build(groups,snapshot)
        self.assertEqual(original,engine.samples)

if __name__=='__main__':unittest.main()
