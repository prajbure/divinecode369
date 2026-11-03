"""The existing archived-GMP comparison rule shared by both clients."""
from .ipo_service import positive,numeric,iso_date

def listing_comparison(ipo,history):
    actual=ipo.get('listing',{}).get('price');final=ipo.get('issue',{}).get('issue_price');cap=history.get('issue_price');day=ipo.get('timeline',{}).get('listing_date')
    if not ipo.get('is_listed') or not all(positive(v) is not None for v in (actual,final,cap)) or not day:
        return {'available':False,'reason':'Verified actual listing price, final issue price, archive price cap and listing date are required.'}
    current_cap=ipo.get('issue',{}).get('price_max')
    if positive(current_cap) is not None and current_cap!=cap:
        return {'available':False,'reason':'Archive and current issue price caps differ; estimates are not comparable.'}
    points=sorted([p for p in history.get('trend',[]) if iso_date(p.get('date')) and p['date']<day and numeric(p.get('price')) is not None],key=lambda p:p['date'])
    if not points or cap+points[-1]['price']<0:
        return {'available':False,'reason':'No valid daily GMP reading strictly before the listing date is available.'}
    point=points[-1];estimate=cap+point['price']
    return {'available':True,'date':point['date'],'estimate':estimate,'actual':actual,'estimate_gain':(estimate-final)/final*100,'actual_gain':(actual-final)/final*100}
