"""Defensive normalization and transparent IPO research, independent of scanners."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit
from .ipoguru import IST


def mapping(value):
    return value if isinstance(value,dict) else {}


def sequence(value):
    return value if isinstance(value,list) else []


def numeric(value):
    if value is None or isinstance(value,bool):
        return None
    text = str(value).strip()
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?',text):
        return None
    try:
        result = float(Decimal(text.replace(',','')))
        return result if abs(result)<1e16 else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def nonnegative(value):
    result=numeric(value)
    return result if result is not None and result>=0 else None


def positive(value):
    result=numeric(value)
    return result if result is not None and result>0 else None


def parsed(data, key, parser=numeric):
    value=parser(data.get(key+'_value'))
    return value if value is not None else parser(data.get(key))


def plain(value):
    return value.strip()[:20000] if isinstance(value,str) else None


def iso_date(value):
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value,str) else None
    except ValueError:
        return None


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def freshness(value, now=None):
    stamp=timestamp(value)
    now=now or datetime.now(timezone.utc)
    age=(now-datetime.fromisoformat(stamp)).total_seconds() if stamp else None
    return {'as_of':stamp, 'age_seconds':round(age) if age is not None else None,
            'status':'unknown' if age is None or age < -60 else 'recent' if age<=1800 else 'delayed' if age<=86400 else 'stale'}


def safe_url(value):
    if not isinstance(value,str) or len(value)>2000:
        return None
    try:
        url=urlsplit(value)
        return value if url.scheme=='https' and url.hostname and not url.username and not url.password else None
    except ValueError:
        return None


# Provider-supplied status_page still has to point to an established registrar.
# Add another registrar only after verifying its official domain; never guess links.
REGISTRAR_HOSTS = {'bigshareonline.com','in.mpms.mufg.com','linkintime.co.in','kfintech.com',
                   'cameoindia.com','purvashare.com','masserv.com','skylinerta.com','maashitla.com',
                   'integratedregistry.in','adroitcorporate.com','satellitecorporate.com'}


def registrar_url(value):
    value=safe_url(value)
    if not value:
        return None
    host=urlsplit(value).hostname.lower()
    return value if any(host==root or host.endswith('.'+root) for root in REGISTRAR_HOSTS) else None


def normalize_ipo(raw, now=None):
    raw=mapping(raw)
    slug=raw.get('slug')
    if not isinstance(slug,str) or len(slug)>150 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):
        return None
    issue=mapping(raw.get('issue')) or raw
    timeline=mapping(raw.get('timeline')) or raw
    listing=mapping(raw.get('listing')) or raw
    gmp=mapping(raw.get('gmp'))
    cap=positive(issue.get('price_max'))
    final=positive(issue.get('issue_price'))
    premium=parsed(gmp,'price')
    # Provider defines GMP against cap price, not necessarily final issue price.
    base=cap or final
    percent=round(premium/base*100,4) if base and premium is not None else None
    estimate=round(base+premium,4) if base and premium is not None and base+premium>=0 else None
    lot=positive(issue.get('lot_size'))
    lot=lot if lot is not None and lot.is_integer() else None
    investment=positive(issue.get('min_investment'))
    if investment is None and lot and base:
        investment=round(lot*base,2)
    actual=positive(listing.get('listing_price'))
    current=positive(listing.get('cmp'))
    return {'slug':slug,'name':plain(raw.get('display_name')) or plain(raw.get('name')) or slug,
            'type':raw.get('type') if raw.get('type') in ('Mainboard','SME') else 'Unknown',
            'status':plain(raw.get('status')) or 'Unknown','stage':plain(raw.get('stage')),
            'dates_tba':raw.get('dates_tba') is True,'is_listed':raw.get('is_listed') is True,
            'logo':safe_url(mapping(raw.get('images')).get('logo') or raw.get('logo')),
            'timeline':{key:iso_date(timeline.get(key)) for key in ('open_date','close_date','allotment_date','refund_date','credit_to_demat_date','listing_date')},
            'issue':{'price_min':positive(issue.get('price_min')),'price_max':cap,'price_band':plain(issue.get('price_band')),
                     'issue_price':final,'issue_size':nonnegative(issue.get('issue_size')),
                     'face_value':positive(issue.get('face_value')),'lot_size':lot,'min_investment':investment,
                     'sale_type':plain(issue.get('sale_type')),'fresh_issue':issue.get('fresh_issue'),
                     'ofs':issue.get('ofs'),'listing_on':plain(issue.get('listing_on')),'nse_symbol':plain(issue.get('nse_symbol'))},
            'gmp':{'price':premium,'percentage':percent,'estimate':estimate,'estimate_basis':'Upper price band' if cap else 'Final issue price' if final else 'Unavailable',
                   'freshness':freshness(gmp.get('updated_at'),now)},
            'subscription_total':nonnegative(raw.get('subscription_total') if 'subscription_total' in raw else mapping(raw.get('subscription_summary')).get('total')),
            'listing':{'price':actual,'gain':round((actual/final-1)*100,4) if actual and final else None,
                       'cmp':current,'current_gain':round((current/final-1)*100,4) if current and final else None,
                       'freshness':freshness(listing.get('updated_at'),now)},
            'web_url':safe_url(raw.get('web_url'))}


def normalize_subscription(raw):
    raw=mapping(raw)
    def category(value,depth=0):
        value=mapping(value)
        return {'key':plain(value.get('key')),'label':plain(value.get('label')) or plain(value.get('key')),
                'times':parsed(value,'times',nonnegative),'shares_offered':nonnegative(value.get('shares_offered')),
                'shares_applied':nonnegative(value.get('shares_applied')),'applications':nonnegative(value.get('applications')),
                'sub_categories':[category(v,depth+1) for v in sequence(value.get('sub_categories')) if isinstance(v,dict)] if depth<2 else []}
    categories=[category(v) for v in sequence(raw.get('categories')) if isinstance(v,dict)]
    # If the provider supplied only flat totals, map only actual, non-null fields.
    summary=mapping(raw.get('summary'))
    known={v['key'] for v in categories}
    for key in ('QIB','NII','RETAIL','EMPLOYEE','SHAREHOLDER','ANCHOR','TOTAL'):
        if key not in known and nonnegative(summary.get(key.lower())) is not None:
            categories.append({'key':key,'label':key,'times':nonnegative(summary[key.lower()]),'sub_categories':[]})
    return {'categories':categories,'freshness':freshness(summary.get('updated_at')),
            'applications_source':plain(raw.get('applications_source'))}


def normalize_history(raw):
    rows={}
    for value in sequence(mapping(raw).get('trend')):
        value=mapping(value)
        day=iso_date(value.get('date'))
        if day:
            rows[day]={'date':day,'price':parsed(value,'price')}
    return {'trend':[rows[key] for key in sorted(rows)],'issue_price':positive(mapping(mapping(raw).get('summary')).get('issue_price')),
            'resolution':'Day-wise closing GMP; no intraday timeline.'}


def research(ipo, company):
    """Fixed denominator prevents missing data from inflating the research score."""
    company=mapping(company)
    supporting,contradictory,missing=[],[],[]
    score=0
    rows=sequence(mapping(company.get('financials')).get('rows'))
    def row_number(terms):
        for row in rows:
            row=mapping(row)
            if any(term in str(row.get('metric','')).lower() for term in terms):
                return [numeric(v) for v in sequence(row.get('data'))]
        return []
    # Compare only explicit dated columns and equal year-end reporting dates.
    headers=sequence(mapping(company.get('financials')).get('headers'))
    periods=[]
    for index,header in enumerate(headers):
        try:
            periods.append((datetime.strptime(str(header),'%d %b %Y').date(),index))
        except ValueError:
            pass
    periods.sort(reverse=True)
    comparable=len(periods)>=2 and periods[0][0].month==periods[1][0].month and periods[0][0].day==periods[1][0].day and periods[0][0].year-periods[1][0].year==1
    for terms,label,weight in [(['revenue'],'Revenue growth',25),(['profit after tax','pat'],'Positive profit after tax',25)]:
        values=row_number(terms)
        indices=[p[1] for p in periods[:2]]
        if not comparable or len(indices)<2 or any(i>=len(values) or values[i] is None for i in indices):
            missing.append(label+' requires comparable dated annual financials.');continue
        latest,prior=(values[i] for i in indices)
        passed=latest>prior if label=='Revenue growth' else latest>0
        (supporting if passed else contradictory).append(f'{label}: {latest:g} versus {prior:g} (reported units).')
        if passed: score+=weight
    for value,label,weight,threshold in [(ipo['subscription_total'],'Subscription demand',20,1),
                                       (ipo['gmp']['price'],'Unofficial GMP sentiment',10,0)]:
        if value is None:
            missing.append(label+' unavailable.');continue
        passed=value>=threshold if threshold else value>0
        (supporting if passed else contradictory).append(f'{label}: {value:g}'+('×.' if threshold else ' rupees.'))
        if passed:score+=weight
    completeness=sum(bool(company.get(key)) for key in ('about','risks','strengths','financials'))
    score+=completeness*5
    if sequence(company.get('risks')):
        contradictory.append('Reported business risks require review; this score does not price their severity.')
    else:missing.append('Business risk disclosures unavailable.')
    missing.append('Relative valuation requires a verified peer benchmark; no valuation points are assigned.')
    if ipo['gmp']['freshness']['status'] in ('stale','unknown'):
        contradictory.append('GMP source freshness is stale or unknown; sentiment is unconfirmed.')
        if ipo['gmp']['price'] is not None and ipo['gmp']['price']>0:score-=10
    return {'score':score,'supporting':supporting,'contradictory':contradictory,'missing':missing,
            'method':'100 points: comparable annual revenue growth 25; positive annual PAT 25; subscription ≥1× 20; positive, timestamped non-stale GMP 10; four reported company sections 5 each. Missing factors receive 0. Not a recommendation, AI prediction or probability of profit.'}


class IPOService:
    def __init__(self, client):
        self.client=client

    def overview(self):
        resource=self.client.get('/ipos','calendar')
        gmp=self.client.get('/gmp','gmp') if resource['meta']['available'] else {'data':None,'meta':{}}
        premiums={v.get('slug'):v for v in sequence(gmp['data']) if isinstance(v,dict)}
        rows=[]
        for raw in sequence(resource['data']):
            if not isinstance(raw,dict):continue
            raw={**raw}
            if raw.get('slug') in premiums:
                raw['gmp']=premiums[raw['slug']].get('gmp')
            ipo=normalize_ipo(raw)
            if ipo:rows.append(ipo)
        rows=list({row['slug']:row for row in rows}.values())
        today=datetime.now(IST).date().isoformat()
        recent=(datetime.now(IST).date()-timedelta(days=30)).isoformat()
        def classified(row,key):
            t=row['timeline']
            return {'open':row['status'].lower()=='open' and not row['is_listed'],
                    'upcoming':row['status'].lower()=='upcoming',
                    'closed':row['status'].lower()=='closed' and bool(t['close_date']) and recent<=t['close_date']<=today,
                    'allotment':row['status'].lower()=='closed' and not row['is_listed'] and bool(t['allotment_date']) and t['allotment_date']>=today,
                    'listings':not row['is_listed'] and bool(t['listing_date']) and t['listing_date']>=today,
                    'listed':row['is_listed'] and bool(t['listing_date']) and recent<=t['listing_date']<=today,
                    'mainboard':row['type']=='Mainboard','sme':row['type']=='SME'}[key]
        for row in rows:
            row['buckets']=[key for key in ('open','upcoming','closed','allotment','listings','listed','mainboard','sme') if classified(row,key)]
        return {'rows':rows,'counts':{key:sum(key in row['buckets'] for row in rows) if resource['meta']['available'] else None for key in ('open','upcoming','closed','allotment','listings','listed','mainboard','sme')},
                'meta':resource['meta'],'gmp_meta':gmp['meta'],'provider':self.client.status(),
                'coverage':'Provider calendar window: last 3 months; recently closed/listed cards: last 30 days. Expected dates are not confirmation of allotment.'}

    def detail(self, slug):
        resource=self.client.get('/ipos/'+slug,'details')
        raw=mapping(resource['data'])
        ipo=normalize_ipo(raw)
        company=normalize_company(raw.get('company'))
        registrar=mapping(mapping(raw.get('contacts')).get('registrar'))
        documents=mapping(raw.get('documents'))
        # No arbitrary HTML, sensitive contact fields or hidden provider blocks forwarded.
        return {'ipo':ipo,'company':{key:company.get(key) for key in ('about','description','strengths','risks','objects_of_issue','financials','kpis','promoters','promoter_holding')},
                'registrar':{'name':plain(registrar.get('name')),'url':registrar_url(registrar.get('status_page'))},
                'documents':{key:safe_url(value) for key,value in documents.items() if isinstance(key,str)},
                'allotment_confirmed':any(safe_url(value) for key,value in documents.items() if key in ('basis_of_allotment','boa')),
                'locked':sorted(mapping(raw.get('locked')).keys()),
                'research':research(ipo,company) if ipo else None,'meta':resource['meta'],'provider':self.client.status()}

    def resource(self,slug,kind):
        path,scope,normalizer={'history':('gmp/history','gmp_history',normalize_history),
                               'subscription':('subscription','subscription',normalize_subscription),
                               'anchors':('anchors','anchors',self.anchors)}[kind]
        resource=self.client.get(f'/ipos/{slug}/{path}',scope)
        return {'data':normalizer(resource['data']) if resource['data'] is not None else None,'meta':resource['meta'],'provider':self.client.status()}

    @staticmethod
    def anchors(raw):
        raw=mapping(raw)
        summary=mapping(raw.get('summary'))
        return {'summary':{key:nonnegative(summary.get(key)) for key in ('total_anchors','total_amount_cr','mutual_fund_count')},
                'document':safe_url(summary.get('anchor_document')),
                'anchors':[{'name':plain(v.get('name')),'group':plain(v.get('group_entity')),
                            **{key:nonnegative(v.get(key)) for key in ('shares_allotted','amount_cr','pct_allocated','pct_allotment_of_issue')}}
                           for v in sequence(raw.get('anchors')) if isinstance(v,dict)]}


def normalize_company(raw):
    company=mapping(raw)
    result={key:company.get(key) for key in ('about','description','strengths','risks','objects_of_issue','kpis','promoters','promoter_holding')}
    for key in ('about','description'):
        result[key]=plain(result[key])
    for key in ('strengths','risks'):
        result[key]=[plain(v) for v in sequence(result[key]) if plain(v)]
    financials=mapping(company.get('financials'))
    headers=[plain(v) for v in sequence(financials.get('headers'))]
    rows=[]
    for row in sequence(financials.get('rows')):
        row=mapping(row)
        values=sequence(row.get('data'))
        if plain(row.get('metric')):
            rows.append({'metric':plain(row['metric']), 'data':[v if numeric(v) is not None else None for v in values[:len(headers)]]})
    result['financials']={'headers':headers,'rows':rows,'unit':plain(financials.get('unit')),'text':plain(financials.get('text'))} if financials else None
    if result['promoters'] is None:
        result['promoters']=company.get('promoter_profiles')
    if result['promoter_holding'] is None:
        result['promoter_holding']=company.get('promoter_holding_pattern')
    return result
