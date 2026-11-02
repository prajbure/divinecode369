import {validNumber as num,escapeHTML as esc,fmt,rupees,percent,tone,istStamp,dayLabel,dailyChart,IPOAlerts,DEFAULT_IPO_ALERTS,sourceFreshness,listingComparison} from './ipo-core.js';

const tabs=[['','Overview'],['gmp','GMP Tracker'],['subscription','Subscription'],['allotment','Allotment'],['listings','Listing Performance'],['compare','Compare'],['calendar','Calendar'],['research','Research Radar'],['alerts','Alerts']];
const buckets=[['open','Open IPOs'],['upcoming','Upcoming IPOs'],['closed','Recently closed'],['allotment','Awaiting allotment'],['listings','Upcoming listings'],['listed','Recently listed'],['mainboard','Mainboard IPOs'],['sme','SME IPOs']];
const alerts=new IPOAlerts();
let selected=readLocal('divine-ipo-compare',[]).filter(v=>typeof v==='string'&&/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v)).slice(0,5);
let preferences={...DEFAULT_IPO_ALERTS,...readLocal('divine-ipo-alerts',{})};
if(!Array.isArray(preferences.events))preferences.events=[...DEFAULT_IPO_ALERTS.events];
for(const key of ['cooldown','gmp','subscription'])if(!num(preferences[key])||preferences[key]<0)preferences[key]=DEFAULT_IPO_ALERTS[key];
const pending=new Map();
const isSlug=v=>typeof v==='string'&&/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v)&&v.length<=150;
function readLocal(key,fallback){try{const result=JSON.parse(localStorage.getItem(key));return result&&typeof result===typeof fallback&&Array.isArray(result)===Array.isArray(fallback)?result:fallback;}catch{return fallback;}}
function saveLocal(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch{/* Current visit remains usable. */}}
const link=ipo=>`<a data-route href="/ipo/details/${esc(ipo.slug)}">${esc(ipo.name)}</a>`;
const badge=ipo=>`<span class="ipo-badge ${['open','upcoming','closed'].includes(ipo.status.toLowerCase())?ipo.status.toLowerCase():''}">${esc(ipo.is_listed?'Listed':ipo.status)}</span><span class="ipo-badge">${esc(ipo.type)}</span>`;
const empty=message=>`<div class="ipo-empty">${esc(message)}</div>`;
const warning='<div class="ipo-warning"><strong>GMP is unofficial and speculative.</strong> It is not a guaranteed listing-price forecast. An estimated listing price is arithmetic from the price cap and reported GMP. This terminal provides research, not an investment recommendation.</div>';
const facts=entries=>`<dl class="ipo-facts">${entries.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value??'Unavailable')}</dd></div>`).join('')}</dl>`;
const list=values=>Array.isArray(values)&&values.length?`<ul class="ipo-evidence">${values.map(v=>`<li>${esc(typeof v==='string'?v:JSON.stringify(v))}</li>`).join('')}</ul>`:empty('Unavailable from the provider.');
const safeLink=(url,label)=>{try{const parsed=new URL(url);return parsed.protocol==='https:'&&!parsed.username&&!parsed.password?`<a class="secondary" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`:'Unavailable';}catch{return 'Unavailable';}};
function readable(value){
  if(value==null||value==='')return 'Unavailable';
  if(typeof value==='string'||typeof value==='number')return esc(value);
  if(Array.isArray(value))return value.length?list(value):'Unavailable';
  return `<dl>${Object.entries(value).filter(([,v])=>v!=null).map(([k,v])=>`<dt>${esc(k.replaceAll('_',' '))}</dt><dd>${readable(v)}</dd>`).join('')}</dl>`;
}
function freshnessMarkup(value){return `<span class="ipo-badge" data-ipo-asof="${esc(value?.as_of||'')}">${sourceFreshness(value?.as_of)} source freshness</span><small>${esc(istStamp(value?.as_of))}</small>`;}
let freshnessMinute=-1;
export function updateIPOFreshness(now=new Date()){
  if(!document.getElementById('ipoTerminal'))return;
  const minute=Math.floor(Number(now)/60000);if(minute===freshnessMinute)return;freshnessMinute=minute;
  for(const node of document.querySelectorAll('[data-ipo-asof]'))node.textContent=sourceFreshness(node.dataset.ipoAsof,now)+' source freshness';
}
function resourceNotice(resource){return resource?.meta?.error?`<div class="notice error">${esc(resource.meta.error.message)}${resource.meta.cache_stale?' Showing stale cached data.':''}</div>`:'';}

export function ipoShell(){
  const screen=location.pathname.split('/')[2]||'';
  return `<div id="ipoTerminal" class="ipo-terminal"><div class="ipo-topline"><div><p class="kicker">DIVINE CODE 369 · PRIMARY MARKETS</p><h1>IPO Intelligence</h1><p>Your dedicated IPO research terminal. Mainboard &amp; SME.</p></div><div class="ipo-actions"><button class="primary" id="ipoRefresh">Refresh data</button></div></div><nav class="ipo-nav" aria-label="IPO screens">${tabs.map(([path,label])=>`<a href="/ipo${path?'/'+path:''}" data-route class="${screen===path?'active':''}" ${screen===path?'aria-current="page"':''}>${label}</a>`).join('')}</nav>${warning}<div id="ipoHealth" class="ipo-health" role="status">Checking IPO provider configuration…</div><div id="ipoContent">${empty('Loading the IPO workspace…')}</div><footer class="ipo-credit"><a href="https://www.ipoguru.in/" target="_blank" rel="noopener noreferrer">Data by IPO Guru — https://www.ipoguru.in/</a><span>Developed by ER PRAJWAL AMBURE · Personal research</span></footer></div>`;
}

let refreshCurrentIPO=null;
export function refreshIPOFromBackend(){refreshCurrentIPO?.();}
export function mountIPO({api,notice}){
  const root=document.getElementById('ipoTerminal');
  if(!root){refreshCurrentIPO=null;return;}
  const screen=location.pathname.split('/')[2]||'';
  const content=root.querySelector('#ipoContent');
  let overview,focusSlug='',filter='',query='',board='',sort='schedule',generation=0;
  const alive=()=>root.isConnected;
  async function get(path){
    if(!pending.has(path))pending.set(path,api(path).finally(()=>pending.delete(path)));
    return pending.get(path);
  }
  function health(provider,meta){
    if(!alive())return;
    root.querySelector('#ipoHealth').innerHTML=`<span><strong>${provider?.verified?'Verified '+esc(provider.plan||'plan'):provider?.configured?'Awaiting account verification':'Provider not configured'}</strong></span><span>${provider?.quota?`${esc(provider.quota.remaining)} requests remaining · ${esc(provider.limits.per_day)}/day · ${esc(provider.limits.per_minute)}/minute`:'Request budget available after /me verification'}</span><span>${meta?.fetched_at?'Last successful fetch: '+esc(istStamp(meta.fetched_at)):'No successful IPO data refresh yet'}</span><span>${meta?.cache_stale?'Stale cached response':meta?.cache_hit?'Shared cached response':'Automatic backend refresh'} · ${esc(Math.round((provider?.cache_seconds||900)/60))} min baseline cache</span>`;
  }
  function runAlerts(rows){
    const updates=alerts.evaluate(rows,preferences);
    if(updates.length){notice(`${updates.length} IPO alert${updates.length===1?'':'s'} · ${updates[0].name}: ${updates[0].message}`);if(globalThis.Notification?.permission==='granted')for(const item of updates)new Notification('DIVINE CODE 369 · '+item.name,{body:item.message,tag:item.slug+':'+item.event});}
  }
  function pick(label='Select an IPO'){
    if(!overview?.rows?.length)return empty('No IPO records are available. Configure the backend provider and refresh.');
    return `<div class="ipo-controls"><label>${esc(label)}<select id="ipoSelect">${overview.rows.map(ipo=>`<option value="${esc(ipo.slug)}"${ipo.slug===focusSlug?' selected':''}>${esc(ipo.name)} · ${esc(ipo.type)}</option>`).join('')}</select></label></div><div id="ipoSelectedContent">${empty('Loading selected IPO…')}</div>`;
  }
  function table(rows,kind='overview'){
    if(!rows.length)return empty(overview?.meta?.available?'No IPOs match your filters.':'IPO data is unavailable. Configure and verify the backend provider.');
    const cols=kind==='listings'?['Company','Final issue price','Actual listing price','Actual listing gain/loss','Current listed price','Since issue price','GMP comparison']:kind==='gmp'?['Company','Price band / final price','Current GMP','GMP %','Estimated listing price','Source update']:['Company','Schedule','Price band','Current GMP','Subscription total','Minimum investment'];
    return `<div class="ipo-table-wrap" tabindex="0" aria-label="Scrollable IPO ${esc(kind)} results"><table class="ipo-table"><thead><tr>${cols.map(c=>`<th scope="col">${c}</th>`).join('')}</tr></thead><tbody>${rows.map(ipo=>`<tr><td>${link(ipo)}${badge(ipo)}<label class="ipo-compare-check"><input type="checkbox" data-ipo-compare="${esc(ipo.slug)}"${selected.includes(ipo.slug)?' checked':''}> Compare (up to 5)</label></td>${kind==='listings'?`<td>${rupees(ipo.issue.issue_price)}</td><td><strong>${rupees(ipo.listing.price)}</strong><small>Actual reported exchange listing price</small></td><td class="${tone(ipo.listing.gain)}"><strong>${percent(ipo.listing.gain)}</strong></td><td>${rupees(ipo.listing.cmp)}${freshnessMarkup(ipo.listing.freshness)}</td><td class="${tone(ipo.listing.current_gain)}">${percent(ipo.listing.current_gain)}</td><td><button class="secondary" data-ipo-listing="${esc(ipo.slug)}">Compare archived GMP</button><div id="ipoListing-${esc(ipo.slug)}"><small>Load a verified pre-listing daily snapshot. Current GMP is not a historical forecast.</small></div></td>`:kind==='gmp'?`<td>${esc(ipo.issue.price_band||'Unavailable')}<small>Final issue: ${rupees(ipo.issue.issue_price)}</small></td><td class="${tone(ipo.gmp.price)}"><strong>${rupees(ipo.gmp.price)}</strong></td><td class="${tone(ipo.gmp.percentage)}"><strong>${percent(ipo.gmp.percentage)}</strong></td><td><strong>${rupees(ipo.gmp.estimate)}</strong><small>Unofficial arithmetic · ${esc(ipo.gmp.estimate_basis)}</small></td><td>${freshnessMarkup(ipo.gmp.freshness)}</td>`:`<td>Opens ${dayLabel(ipo.timeline.open_date)}<small>Closes ${dayLabel(ipo.timeline.close_date)}</small></td><td>${esc(ipo.issue.price_band||'Unavailable')}<small>Final issue: ${rupees(ipo.issue.issue_price)}</small></td><td class="${tone(ipo.gmp.price)}"><strong>${rupees(ipo.gmp.price)}</strong><small>${percent(ipo.gmp.percentage)}</small>${freshnessMarkup(ipo.gmp.freshness)}</td><td>${fmt(ipo.subscription_total,'×')}<small>Calendar summary; open Subscription for category source time.</small></td><td>${rupees(ipo.issue.min_investment)}<small>Lot size ${fmt(ipo.issue.lot_size,'',0)}</small></td>`}</tr>`).join('')}</tbody></table></div>`;
  }
  function controls(){return `<div class="ipo-controls"><label>Search company<input id="ipoSearch" type="search" placeholder="Company name or IPO slug" value="${esc(query)}"></label><label>Board<select id="ipoBoard"><option value="">All boards</option><option${board==='Mainboard'?' selected':''}>Mainboard</option><option${board==='SME'?' selected':''}>SME</option></select></label><label>Status<select id="ipoBucket"><option value="">All statuses</option>${buckets.slice(0,6).map(([key,label])=>`<option value="${key}"${filter===key?' selected':''}>${label}</option>`).join('')}</select></label><label>Sort by<select id="ipoSort">${[['schedule','Opening date'],['name','Company name'],['gmp','GMP % (high first)'],['subscription','Subscription (high first)']].map(([key,label])=>`<option value="${key}"${sort===key?' selected':''}>${label}</option>`).join('')}</select></label><button class="secondary" id="ipoClear">Clear filters</button></div>`;}
  function filtered(){return overview.rows.filter(ipo=>(!query||(ipo.name+' '+ipo.slug).toLowerCase().includes(query.toLowerCase()))&&(!board||ipo.type===board)&&(!filter||ipo.buckets.includes(filter))).sort((a,b)=>{if(sort==='name')return a.name.localeCompare(b.name);const x=sort==='gmp'?a.gmp.percentage:sort==='subscription'?a.subscription_total:a.timeline.open_date,y=sort==='gmp'?b.gmp.percentage:sort==='subscription'?b.subscription_total:b.timeline.open_date;if(x==null)return y==null?0:1;if(y==null)return -1;return typeof x==='string'?y.localeCompare(x):y-x;});}
  function renderResults(){const results=root.querySelector('#ipoResults');if(results)results.innerHTML=table(screen==='listings'?filtered().filter(ipo=>ipo.is_listed):filtered(),screen==='gmp'?'gmp':screen==='listings'?'listings':'overview');}
  function overviewView(){
    const summary=screen===''?`<div class="ipo-summary">${buckets.map(([key,label])=>`<button data-ipo-bucket="${key}" aria-pressed="${filter===key}"><span>${label}</span><strong>${num(overview.counts[key])?fmt(overview.counts[key],'',0):'—'}</strong><small>${['closed','listed'].includes(key)?'Within the last 30 days':key==='allotment'?'Expected schedule · unlisted':'In the provider calendar window'}</small></button>`).join('')}</div>`:'';
    const headings={'':'IPO overview','gmp':'GMP Intelligence Tracker','listings':'Actual listing performance'};
    content.innerHTML=resourceNotice(overview)+resourceNotice({meta:overview.gmp_meta})+summary+`<section class="ipo-panel"><h2>${headings[screen]}</h2><p>${esc(overview.coverage)}</p>${screen==='listings'?'<p>Actual listing returns use the final issue price. Current listed prices have separate source freshness.</p>':''}${controls()}<div id="ipoResults"></div><p class="ipo-disclosure"><a href="/ipo/compare" data-route>Compare selected IPOs →</a> · ${selected.length}/5 selected</p></section>`+(screen==='gmp'?`<section class="ipo-panel ipo-chart-panel"><h2>Day-wise GMP history</h2><p>One closing reading per reported day. Gaps stay visible; no intraday data is requested.</p>${pick('IPO for GMP history')}</section>`:'');
    renderResults();if(screen==='gmp'&&focusSlug)loadSelection();
  }
  function financials(company){
    const f=company?.financials;
    if(!f)return empty('Company financials are unavailable.');
    if(!Array.isArray(f.rows)||!f.rows.length)return `<p>${esc(f.text||'Structured financial figures unavailable.')}</p>`;
    const headers=Array.isArray(f.headers)?f.headers:[];
    return `<p>Reported units: ${esc(f.unit||'Not supplied')}</p><div class="ipo-table-wrap" tabindex="0" aria-label="Scrollable company financials"><table class="ipo-table"><thead><tr><th>Reported metric</th>${headers.map(v=>`<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${f.rows.filter(v=>v&&typeof v==='object').map(row=>`<tr><td>${esc(row.metric||'Unnamed metric')}</td>${headers.map((_,index)=>`<td>${esc(row.data?.[index]??'Unavailable')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function researchPanel(detail){const r=detail.research;return r?`<div class="ipo-panel"><h2>Explainable Research Radar</h2><p><strong class="ipo-score">${fmt(r.score,' / 100',0)}</strong> · Research relevance, not a probability of profit.</p><p class="ipo-disclosure">${esc(r.method)}</p><div class="ipo-grid"><section><h3 class="positive">Supporting factors</h3>${list(r.supporting)}</section><section><h3 class="negative">Contradictory factors</h3>${list(r.contradictory)}</section></div><h3>Missing information</h3>${list(r.missing)}</div>`:empty('Research score unavailable without a verified IPO detail record.');}
  function allotmentPanel(detail){const ipo=detail.ipo;return `<section class="ipo-panel"><h2>Allotment center · ${esc(ipo.name)}</h2>${facts([['Registrar',detail.registrar.name||'Unavailable'],['Expected allotment',dayLabel(ipo.timeline.allotment_date)],['Announcement',detail.allotment_confirmed?'Basis-of-allotment document supplied':'Not verified']])}<p>Check personal allotment on the official registrar website. This application does not request or store PAN, application secrets, bank credentials or OTPs.</p><div class="ipo-actions">${detail.registrar.url?safeLink(detail.registrar.url,'Open official registrar'):'<span>Verified registrar link unavailable. No guessed link is provided.</span>'}</div></section>`;}
  function detailView(detail){
    if(!detail.ipo)return resourceNotice(detail)+empty('IPO details are unavailable.');
    const ipo=detail.ipo,c=detail.company||{};
    return `${resourceNotice(detail)}<section class="ipo-panel"><div class="ipo-detail-head">${ipo.logo?`<img src="${esc(ipo.logo)}" alt="${esc(ipo.name)} logo" referrerpolicy="no-referrer">`:''}<div><p class="kicker">COMPANY RESEARCH</p><h2>${esc(ipo.name)}</h2>${badge(ipo)}</div></div>${facts([['Price band',ipo.issue.price_band||'Unavailable'],['Final issue price',rupees(ipo.issue.issue_price)],['Issue size (₹ crore)',fmt(ipo.issue.issue_size)],['Face value',rupees(ipo.issue.face_value)],['Lot size',fmt(ipo.issue.lot_size,' shares',0)],['Minimum investment',rupees(ipo.issue.min_investment)],['Fresh / OFS composition',ipo.issue.sale_type||'Unavailable'],['Exchange listing',ipo.issue.listing_on||'Unavailable']])}<div class="ipo-grid"><section><h3>Issue composition</h3><div class="ipo-disclosure">Fresh issue: ${readable(ipo.issue.fresh_issue)}<br>OFS: ${readable(ipo.issue.ofs)}</div></section><section><h3>GMP · unofficial</h3>${facts([['Current GMP',rupees(ipo.gmp.price)],['GMP / estimated gain',percent(ipo.gmp.percentage)],['Arithmetic listing estimate',rupees(ipo.gmp.estimate)]])}${freshnessMarkup(ipo.gmp.freshness)}</section></div></section><section class="ipo-panel"><h2>IPO schedule</h2>${facts(Object.entries(ipo.timeline).map(([key,value])=>[key.replaceAll('_',' '),dayLabel(value)]))}<p>Dates are expected unless the provider supplies a confirming announcement.</p></section><section class="ipo-panel"><h2>Company fundamentals</h2><p>${esc(c.about||c.description||'Business description unavailable.')}</p>${financials(c)}<h3>Reported KPIs · EPS, P/E, ROE and other metrics</h3><div class="ipo-disclosure">${readable(c.kpis)}</div><details class="ipo-disclosure"><summary>Promoters and holding pattern</summary>${readable(c.promoters)}${readable(c.promoter_holding)}</details><details class="ipo-disclosure"><summary>Objects of the issue</summary>${readable(c.objects_of_issue)}</details></section><div class="ipo-grid"><section class="ipo-panel"><h2>Reported strengths</h2>${list(c.strengths)}</section><section class="ipo-panel"><h2>Reported risks</h2>${list(c.risks)}</section></div><section class="ipo-panel ipo-chart-panel"><h2>GMP history, subscription &amp; anchors</h2><div class="ipo-actions"><button class="secondary" data-ipo-resource="history">Load daily GMP history</button><button class="secondary" data-ipo-resource="subscription">Load current subscription</button><button class="secondary" data-ipo-resource="anchors">Load anchor allocations</button></div><div id="ipoDetailResource"></div></section>${allotmentPanel(detail)}<section class="ipo-panel"><h2>Official documents</h2><div class="ipo-actions">${Object.entries(detail.documents||{}).filter(([,url])=>url).map(([key,url])=>safeLink(url,key.replaceAll('_',' '))).join('')||'<p>DRHP, RHP and other prospectus links are unavailable from the provider.</p>'}</div>${detail.locked?.length?`<p>Unavailable on verified plan: ${esc(detail.locked.join(', '))}.</p>`:''}</section>${researchPanel(detail)}`;
  }
  function historyView(resource){const rows=resource.data?.trend;const valid=(rows||[]).filter(p=>num(p.price)),movement=valid.length>=2?valid.at(-1).price-valid.at(-2).price:null;return `${resourceNotice(resource)}${rows?`<p class="ipo-disclosure">${esc(resource.data.resolution)} · Latest daily movement: <strong class="${tone(movement)}">${rupees(movement)}</strong></p><div class="ipo-chart-scroll">${dailyChart(rows)}</div><details class="ipo-disclosure"><summary>Daily readings and dates</summary><div class="ipo-table-wrap" tabindex="0"><table class="ipo-table"><thead><tr><th>Date (IST)</th><th>GMP (₹)</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${dayLabel(p.date)}</td><td>${rupees(p.price)}</td></tr>`).join('')}</tbody></table></div></details>`:empty('Daily GMP history is unavailable or requires Standard access.')}`;}
  function subscriptionView(resource){
    const rows=resource.data?.categories||[],max=Math.max(1,...rows.map(v=>num(v.times)?v.times:0));
    return `${resourceNotice(resource)}<h3>Current category subscription</h3><p>Reported subscription in times; bars compare available categories against the largest reading. They do not show the probability of allotment.</p>${resource.data?freshnessMarkup(resource.data.freshness):''}${rows.length?rows.map(row=>`<div class="ipo-subscription-row"><div><span>${esc(row.label||row.key)} ${row.key==='NII'?' / HNI':''}</span><strong>${fmt(row.times,'×')}</strong></div><div class="ipo-subscription-track" aria-hidden="true"><span style="width:${num(row.times)?Math.min(100,row.times/max*100):0}%"></span></div><small>Shares offered: ${fmt(row.shares_offered,'',0)} · Shares applied: ${fmt(row.shares_applied,'',0)}</small>${row.sub_categories?.length?`<details class="ipo-disclosure"><summary>Reported subcategories</summary>${row.sub_categories.map(v=>`<p>${esc(v.label||v.key)}: ${fmt(v.times,'×')}</p>`).join('')}</details>`:''}</div>`).join(''):empty('No category figures are available. Missing values remain unavailable.')}<p class="ipo-disclosure">Source for applications: ${esc(resource.data?.applications_source||'Unavailable')}. Historical subscription charts require separate access and are not requested.</p>`;
  }
  function anchorsView(resource){const data=resource.data;return resourceNotice(resource)+(data?`<h3>Anchor investor allocations</h3>${facts([['Anchor entities',fmt(data.summary.total_anchors,'',0)],['Allocation (₹ crore)',fmt(data.summary.total_amount_cr)],['Mutual fund count',fmt(data.summary.mutual_fund_count,'',0)]])}${data.anchors.length?`<div class="ipo-table-wrap" tabindex="0"><table class="ipo-table"><thead><tr><th>Investor</th><th>Fund group</th><th>Shares allotted</th><th>Amount (₹ crore)</th><th>Allocation %</th></tr></thead><tbody>${data.anchors.map(v=>`<tr><td>${esc(v.name||'Unavailable')}</td><td>${esc(v.group||'Unavailable')}</td><td>${fmt(v.shares_allotted,'',0)}</td><td>${fmt(v.amount_cr)}</td><td>${fmt(v.pct_allocated,'%')}</td></tr>`).join('')}</tbody></table></div>`:empty('Anchor allocations are not reported for this IPO.')}${data.document?safeLink(data.document,'Filed anchor document'):''}`:empty('Anchor allocations are unavailable or require Standard access.'));}
  async function loadResource(slug,kind,target){
    const version=++generation;target.innerHTML=empty('Loading authorized '+kind+' data…');
    try{const resource=await get(`/api/ipo/details/${slug}/${kind}`);if(!alive()||version!==generation)return;target.innerHTML=({history:historyView,subscription:subscriptionView,anchors:anchorsView}[kind])(resource);health(resource.provider,resource.meta);if(kind==='subscription'&&overview){const ipo=overview.rows.find(v=>v.slug===slug);if(ipo){const total=resource.data?.categories?.find(v=>v.key==='TOTAL')?.times;runAlerts([{...ipo,alert_subscription:{total,freshness:resource.data?.freshness}}]);}}}catch(error){if(alive()&&version===generation)target.innerHTML=empty(error.message);}
  }
  async function loadSelection(){
    const target=root.querySelector('#ipoSelectedContent');if(!target||!isSlug(focusSlug))return;
    if(screen==='gmp'||screen==='subscription')return loadResource(focusSlug,screen==='gmp'?'history':'subscription',target);
    const version=++generation;
    try{const detail=await get('/api/ipo/details/'+focusSlug);if(!alive()||version!==generation)return;health(detail.provider,detail.meta);target.innerHTML=resourceNotice(detail)+(detail.ipo?(screen==='allotment'?allotmentPanel(detail):researchPanel(detail)):empty('Selected IPO details are unavailable.'));}catch(error){if(alive()&&version===generation)target.innerHTML=empty(error.message);}
  }
  function calendarView(){
    const events=[];
    for(const ipo of overview.rows)for(const [label,key] of [['Opening','open_date'],['Closing','close_date'],['Expected allotment','allotment_date'],['Expected listing','listing_date']])if(ipo.timeline[key])events.push({day:ipo.timeline[key],label,ipo});
    events.sort((a,b)=>a.day.localeCompare(b.day));
    const groups=Map.groupBy(events,e=>e.day.slice(0,7));
    content.innerHTML=`<section class="ipo-panel"><h2>IPO schedule calendar</h2><p>Published dates from the provider calendar window. Allotment and listing dates remain expected until confirmed.</p><div class="ipo-calendar">${[...groups].map(([month,entries])=>`<article><h3>${esc(month)}</h3>${entries.map(e=>`<div class="ipo-event">${link(e.ipo)}${dayLabel(e.day)} · ${esc(e.label)}</div>`).join('')}</article>`).join('')||empty('No verified IPO schedule is available.')}</div></section>`;
  }
  async function comparisonView(){
    content.innerHTML=`<section class="ipo-panel"><h2>Compare up to five IPOs</h2><p>Select companies in Overview, GMP Tracker or Listing Performance. Comparison highlights reported differences and does not recommend an investment.</p><div class="ipo-actions">${selected.filter(isSlug).map(slug=>`<button class="secondary" data-ipo-remove="${esc(slug)}">Remove ${esc(overview.rows.find(v=>v.slug===slug)?.name||slug)}</button>`).join('')}</div><div id="ipoComparison">${empty(selected.length?'Loading selected company details within the shared quota…':'No IPOs selected. Add up to five from the Overview table.')}</div></section>`;
    const target=root.querySelector('#ipoComparison'),details=[];
    // Sequential detail requests avoid a five-way burst on a constrained plan.
    for(const slug of selected.filter(isSlug)){try{details.push(await get('/api/ipo/details/'+slug));}catch(error){details.push({error:error.message});}if(!alive())return;}
    const available=details.filter(v=>v.ipo);if(!available.length){target.innerHTML=empty(selected.length?'Selected details are currently unavailable.':'Select IPOs to compare.');return;}
    const fields=[['GMP',v=>rupees(v.ipo.gmp.price)],['GMP %',v=>percent(v.ipo.gmp.percentage)],['Subscription',v=>fmt(v.ipo.subscription_total,'×')],['Price band',v=>v.ipo.issue.price_band||'Unavailable'],['Final issue',v=>rupees(v.ipo.issue.issue_price)],['Lot size',v=>fmt(v.ipo.issue.lot_size,'',0)],['Minimum investment',v=>rupees(v.ipo.issue.min_investment)],['Issue size (₹ crore)',v=>fmt(v.ipo.issue.issue_size)],['Listing date',v=>dayLabel(v.ipo.timeline.listing_date)],['Research relevance',v=>fmt(v.research?.score,' / 100',0)]];
    target.innerHTML=details.map(resourceNotice).join('')+`<div class="ipo-table-wrap" tabindex="0"><table class="ipo-table"><thead><tr><th>Metric</th>${available.map(v=>`<th>${link(v.ipo)}</th>`).join('')}</tr></thead><tbody>${fields.map(([label,value])=>{const values=available.map(value);return `<tr><td>${label}</td>${values.map(text=>`<td${new Set(values).size>1?' class="neutral"':''}>${esc(text)}</td>`).join('')}</tr>`;}).join('')}<tr><td>Reported financials · revenue, profitability</td>${available.map(v=>`<td><details class="ipo-disclosure"><summary>View financials</summary>${readable(v.company?.financials)}</details></td>`).join('')}</tr><tr><td>Valuation / reported KPIs</td>${available.map(v=>`<td>${readable(v.company?.kpis)}</td>`).join('')}</tr><tr><td>Reported strengths</td>${available.map(v=>`<td>${list(v.company?.strengths)}</td>`).join('')}</tr><tr><td>Reported risks</td>${available.map(v=>`<td>${list(v.company?.risks)}</td>`).join('')}</tr></tbody></table></div>`;
  }
  function alertsView(){content.innerHTML=`<section class="ipo-panel"><h2>Personal IPO alerts</h2><p>Off by default. Alerts evaluate only verified data loaded while you use the terminal or refresh it. No background polling. Preferences are local; session alert history is kept in memory.</p><form id="ipoAlertForm"><div class="ipo-preferences"><label><input name="enabled" type="checkbox"${preferences.enabled?' checked':''}> Enable IPO alerts</label><label>Cooldown (seconds)<input name="cooldown" type="number" min="60" max="86400" value="${esc(preferences.cooldown)}" required></label><label>GMP threshold (%)<input name="gmp" type="number" min="0" max="1000" step="0.1" value="${esc(preferences.gmp)}" required></label><label>Subscription threshold (×)<input name="subscription" type="number" min="0.1" max="100000" step="0.1" value="${esc(preferences.subscription)}" required></label>${DEFAULT_IPO_ALERTS.events.map(event=>`<label><input type="checkbox" name="event" value="${event}"${preferences.events?.includes(event)?' checked':''}> ${esc(event==='allotment'?'Expected allotment date':event==='gmp'?'GMP threshold change':event==='subscription'?'Subscription updates':event[0].toUpperCase()+event.slice(1))}</label>`).join('')}</div><button class="primary" type="submit">Save alert preferences</button></form><button class="secondary" id="ipoNotifications">Enable browser notifications</button><p class="ipo-disclosure">Subscription alerts use current category responses with a recent source timestamp. They do not invent missing figures. This terminal never applies for an IPO or places orders.</p><h3>Session alert history · IST</h3>${alerts.history.length?alerts.history.map(v=>`<div class="ipo-history-item"><strong>${esc(v.name)}</strong><p>${esc(v.message)}</p><small>${esc(istStamp(v.at))}</small></div>`).join(''):empty('No IPO alerts in this session.')}</section>`;}
  async function render(){
    if(['','gmp','listings'].includes(screen))return overviewView();
    if(['subscription','allotment','research'].includes(screen)){content.innerHTML=`<section class="ipo-panel"><h2>${screen==='subscription'?'Subscription dashboard':screen==='allotment'?'Official allotment links':'IPO Research Radar'}</h2>${pick()}</section>`;return focusSlug?loadSelection():undefined;}
    if(screen==='calendar')return calendarView();
    if(screen==='compare')return comparisonView();
    if(screen==='alerts')return alertsView();
    content.innerHTML=empty('This IPO screen is unavailable. Choose a tab above.');
  }
  async function load(){
    const version=++generation;
    try{
      if(screen==='details'){
        const slug=decodeURIComponent(location.pathname.split('/')[3]||'');
        if(!isSlug(slug)){content.innerHTML=empty('Invalid IPO identifier.');return;}
        focusSlug=slug;const detail=await get('/api/ipo/details/'+slug);if(!alive()||version!==generation)return;
        content.innerHTML=detailView(detail);health(detail.provider,detail.meta);return;
      }
      overview=await get('/api/ipo/overview');if(!alive()||version!==generation)return;
      health(overview.provider,overview.meta);focusSlug=overview.rows.some(v=>v.slug===focusSlug)?focusSlug:overview.rows[0]?.slug||'';
      runAlerts(overview.rows);await render();
    }catch(error){if(alive()&&version===generation)content.innerHTML=empty(error.message);}
  }
  root.onclick=async event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.id==='ipoRefresh'){button.disabled=true;await load();if(alive())button.disabled=false;}
    if(button.id==='ipoVerify'){button.disabled=true;try{const result=await api('/api/ipo/verify',{method:'POST'});health(result.provider,result.meta);notice(result.meta.error?.message||'IPO Guru plan and scopes verified.',!!result.meta.error);}catch(error){notice(error.message,true);}finally{if(alive())button.disabled=false;}}
    if(button.dataset.ipoBucket){filter=filter===button.dataset.ipoBucket?'':button.dataset.ipoBucket;overviewView();}
    if(button.id==='ipoClear'){filter=query=board='';sort='schedule';overviewView();}
    if(button.dataset.ipoListing){
      const slug=button.dataset.ipoListing,ipo=overview.rows.find(v=>v.slug===slug),target=root.querySelector('#ipoListing-'+slug);button.disabled=true;
      try{const resource=await get('/api/ipo/details/'+slug+'/history');if(!alive())return;const result=listingComparison(ipo,resource.data);target.innerHTML=resourceNotice(resource)+(result.available?'<p>Unofficial GMP arithmetic from '+esc(dayLabel(result.date))+': <strong>'+rupees(result.estimate)+'</strong> ('+percent(result.estimate_gain)+').</p><p>Actual exchange listing: <strong>'+rupees(result.actual)+'</strong> ('+percent(result.actual_gain)+').</p><small>Archived daily reading; not a forecast captured by this app. Provider corrections may revise archived values.</small>':empty(result.reason));health(resource.provider,resource.meta);}catch(error){if(alive())target.innerHTML=empty(error.message);}finally{if(alive())button.disabled=false;}
    }
    if(button.dataset.ipoResource)loadResource(focusSlug,button.dataset.ipoResource,root.querySelector('#ipoDetailResource'));
    if(button.dataset.ipoRemove){selected=selected.filter(v=>v!==button.dataset.ipoRemove);saveLocal('divine-ipo-compare',selected);comparisonView();}
    if(button.id==='ipoNotifications'){if(!globalThis.Notification){notice('Browser notifications are unavailable.');return;}try{const permission=await Notification.requestPermission();notice('Browser notification permission: '+permission+'.');}catch{notice('Browser notification permission is unavailable.');}}
  };
  root.oninput=event=>{if(event.target.id==='ipoSearch'){query=event.target.value;renderResults();}};
  root.onchange=event=>{
    const control=event.target;
    if(control.id==='ipoBoard'){board=control.value;renderResults();}
    if(control.id==='ipoBucket'){filter=control.value;renderResults();}
    if(control.id==='ipoSort'){sort=control.value;renderResults();}
    if(control.id==='ipoSelect'){focusSlug=control.value;loadSelection();}
    if(control.dataset.ipoCompare){const slug=control.dataset.ipoCompare;if(control.checked){if(selected.length>=5){control.checked=false;notice('Compare supports up to five IPOs. Remove one before adding another.');return;}selected=[...new Set([...selected,slug])];}else selected=selected.filter(v=>v!==slug);saveLocal('divine-ipo-compare',selected);}
  };
  root.onsubmit=event=>{
    if(event.target.id!=='ipoAlertForm')return;
    event.preventDefault();const data=new FormData(event.target);
    preferences={enabled:data.has('enabled'),cooldown:Number(data.get('cooldown')),gmp:Number(data.get('gmp')),subscription:Number(data.get('subscription')),events:data.getAll('event')};
    if(![preferences.cooldown,preferences.gmp,preferences.subscription].every(num)||preferences.cooldown<60){notice('Provide valid alert thresholds.',true);return;}
    saveLocal('divine-ipo-alerts',preferences);notice('IPO alert preferences saved.');runAlerts(overview.rows);alertsView();
  };
  refreshCurrentIPO=()=>{if(root.isConnected&&!document.hidden)load();};
  load();
}
