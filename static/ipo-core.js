// Pure display/alert helpers. No provider credentials or network calls.
export const validNumber = v => typeof v==='number'&&Number.isFinite(v);
export const escapeHTML = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const fmt = (v,suffix='',digits=2) => validNumber(v)?v.toLocaleString('en-IN',{maximumFractionDigits:digits})+suffix:'Unavailable';
export const rupees = v => validNumber(v)?'₹'+fmt(v):'Unavailable';
export const percent = v => validNumber(v)?(v>0?'+':'')+fmt(v,'%'):'Unavailable';
export const tone = v => !validNumber(v)||v===0?'neutral':v>0?'positive':'negative';
export function sourceFreshness(value,now=Date.now()){
  const time=typeof value==='string'?Date.parse(value):NaN,age=(Number(now)-time)/1000;
  return !Number.isFinite(age)||age < -60?'unknown':age<=1800?'recent':age<=86400?'delayed':'stale';
}
export function istStamp(value){
  if(!value)return 'Source time unavailable';
  const instant=new Date(value);
  return Number.isNaN(instant.getTime())?'Source time unavailable':new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(instant)+' IST';
}
export function dayLabel(value){
  if(!/^\d{4}-\d\d-\d\d$/.test(value||''))return 'Unannounced';
  return new Date(value+'T00:00:00+05:30').toLocaleDateString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric'});
}
export function dailyChart(trend){
  const points=Array.isArray(trend)?trend:[],values=points.map(p=>p.price).filter(validNumber);
  if(values.length<2)return '<p class="ipo-empty">At least two verified daily GMP readings are needed for the chart.</p>';
  const low=Math.min(...values),high=Math.max(...values),range=high-low||1;
  let pen=false;
  const path=points.map((p,i)=>{if(!validNumber(p.price)){pen=false;return '';}const move=pen?'L':'M';pen=true;return `${move}${(70+i/(points.length-1)*700).toFixed(2)},${(225-(p.price-low)/range*175).toFixed(2)}`;}).join(' ');
  const ticks=[0,Math.floor((points.length-1)/2),points.length-1].filter((v,i,a)=>a.indexOf(v)===i);
  return `<svg class="ipo-gmp-chart" viewBox="0 0 820 290" role="img" aria-label="Day-wise GMP in rupees. Missing daily readings are gaps."><line x1="70" x2="770" y1="225" y2="225" stroke="#485d83"/><text x="4" y="52">₹${escapeHTML(fmt(high))}</text><text x="4" y="228">₹${escapeHTML(fmt(low))}</text><path d="${path}" fill="none" stroke="#00d8ff" stroke-width="3"/>${ticks.map(i=>`<text x="${70+i/(points.length-1)*700}" y="265" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}">${escapeHTML(dayLabel(points[i].date))}</text>`).join('')}</svg>`;
}

export function listingComparison(ipo,history){
  const actual=ipo?.listing?.price,final=ipo?.issue?.issue_price,cap=history?.issue_price,date=ipo?.timeline?.listing_date;
  if(!ipo?.is_listed||!numPositive(actual)||!numPositive(final)||!numPositive(cap)||!date)return {available:false,reason:'Verified actual listing price, final issue price, archive price cap and listing date are required.'};
  if(numPositive(ipo.issue.price_max)&&ipo.issue.price_max!==cap)return {available:false,reason:'Archive and current issue price caps differ; estimates are not comparable.'};
  const points=(history.trend||[]).filter(p=>/^\d{4}-\d\d-\d\d$/.test(p.date)&&p.date<date&&validNumber(p.price)).sort((a,b)=>a.date.localeCompare(b.date));
  const point=points.at(-1);
  if(!point||cap+point.price<0)return {available:false,reason:'No valid daily GMP reading strictly before the listing date is available.'};
  return {available:true,date:point.date,estimate:cap+point.price,actual,estimate_gain:(cap+point.price-final)/final*100,actual_gain:(actual-final)/final*100};
}
function numPositive(value){return validNumber(value)&&value>0;}

export const DEFAULT_IPO_ALERTS={enabled:false,cooldown:900,gmp:20,subscription:2,events:['opening','closing','allotment','listing','gmp','subscription']};
// Values/fingerprints stay in memory; only preferences are saved locally.
export class IPOAlerts {
  constructor(){this.seen=new Map();this.previous=new Map();this.history=[];}
  evaluate(rows,prefs,now=Date.now()){
    if(!prefs.enabled)return [];
    const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
    const out=[],allowed=Array.isArray(prefs.events)?prefs.events:[];
    for(const ipo of rows){
      const triggers=[],previous=this.previous.get(ipo.slug);
      for(const [event,key] of [['opening','open_date'],['closing','close_date'],['allotment','allotment_date'],['listing','listing_date']]){
        if(allowed.includes(event)&&ipo.timeline?.[key]===today)triggers.push([event,today,`Expected ${event} date is today. Confirm the published schedule.`]);
      }
      const premium=ipo.gmp?.percentage;
      const fresh=ipo.gmp?.freshness?.status==='recent'&&sourceFreshness(ipo.gmp?.freshness?.as_of,now)==='recent';
      if(allowed.includes('gmp')&&fresh&&validNumber(premium)&&premium>=prefs.gmp&&(!previous||previous.gmp<prefs.gmp))triggers.push(['gmp',String(ipo.gmp.freshness.as_of),`Unofficial GMP reached ${fmt(premium,'%')} (threshold ${prefs.gmp}%).`]);
      // A current category response, not a calendar total without a source timestamp.
      const total=ipo.alert_subscription?.total;
      if(allowed.includes('subscription')&&ipo.alert_subscription?.freshness?.status==='recent'&&sourceFreshness(ipo.alert_subscription?.freshness?.as_of,now)==='recent'&&validNumber(total)&&total>=prefs.subscription&&(!previous||previous.subscription!==total))triggers.push(['subscription',String(ipo.alert_subscription.freshness.as_of),`Reported subscription is ${fmt(total,'×')}.`]);
      this.previous.set(ipo.slug,{gmp:premium,subscription:total});
      for(const [event,version,message] of triggers){
        const key=ipo.slug+':'+event,prior=this.seen.get(key);
        if(prior&&(prior.version===version||now-prior.at<Math.max(60,prefs.cooldown)*1000))continue;
        this.seen.set(key,{version,at:now});
        out.push({slug:ipo.slug,name:ipo.name,event,message,at:new Date(now).toISOString()});
      }
    }
    this.history.unshift(...out);this.history.length=Math.min(100,this.history.length);
    return out;
  }
}
