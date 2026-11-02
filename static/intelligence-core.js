/* Pure, rule-based observations. No orders, predictions or retained tick data. */
export const finite = value => typeof value === 'number' && Number.isFinite(value);
export const positive = value => finite(value) && value > 0;
export function compareOpeningPriority(a,b){const rank=r=>r.match?0:r.near_match?1:2;const magnitude=r=>finite(r.difference)?Math.abs(r.difference):Infinity;return rank(a)-rank(b)||magnitude(a)-magnitude(b)||a.symbol.localeCompare(b.symbol);}
const clamp = (value,min,max) => Math.min(max,Math.max(min,value));
export function median(values){if(!values.length)return null;const sorted=[...values].sort((a,b)=>a-b),mid=Math.floor(sorted.length/2);return sorted.length%2?sorted[mid]:(sorted[mid-1]+sorted[mid])/2;}
export function gapPercent(row){return positive(row.open)&&positive(row.prev_close)?(row.open-row.prev_close)/row.prev_close*100:null;}
export function sectorMetrics(group,rows){
  const symbols=new Set(group.stocks.map(s=>'NSE:'+s[0]));
  const observed=[...new Map(rows.filter(r=>symbols.has(r.symbol)).map(r=>[r.symbol,r])).values()];
  const valid=observed.filter(r=>finite(r.change_pct)&&positive(r.ltp));
  const movements=valid.map(r=>r.change_pct),sum=movements.reduce((a,b)=>a+b,0);
  const advancing=movements.filter(v=>v>0).length,declining=movements.filter(v=>v<0).length;
  const absolute=movements.reduce((a,b)=>a+Math.abs(b),0),topTwo=[...movements].sort((a,b)=>Math.abs(b)-Math.abs(a)).slice(0,2).reduce((a,b)=>a+Math.abs(b),0);
  const average=valid.length?sum/valid.length:null,mid=median(movements),breadth=valid.length?advancing/valid.length:null;
  const concentration=absolute?topTwo/absolute:null;
  return {id:group.id,name:group.name,total:symbols.size,available:valid.length,advancing,declining,unchanged:valid.length-advancing-declining,
    average,median:mid,breadth,concentration,
    dispersion:movements.length>=2?Math.sqrt(movements.reduce((sum,value)=>sum+(value-average)**2,0)/movements.length):null,
    volume_participation:symbols.size?observed.filter(r=>positive(r.volume)).length/symbols.size:null,
    above_vwap:observed.filter(r=>positive(r.vwap)&&positive(r.ltp)&&positive(r.volume)&&r.vwap_source==='Kite average traded price'&&r.ltp>r.vwap).length,
    below_vwap:observed.filter(r=>positive(r.vwap)&&positive(r.ltp)&&positive(r.volume)&&r.vwap_source==='Kite average traded price'&&r.ltp<r.vwap).length,
    strength:valid.length?clamp(50+(advancing-declining)/valid.length*35+clamp(mid,-3,3)*5,0,100):null,
    participation:!valid.length?'Unavailable':breadth>=.65&&valid.length>=4&&concentration<.65?'Broad-based':concentration>=.65?'Concentrated in one or two stocks':'Mixed participation',
    strongest:[...valid].sort((a,b)=>b.change_pct-a.change_pct)[0]||null,weakest:[...valid].sort((a,b)=>a.change_pct-b.change_pct)[0]||null,
    gap_up:observed.filter(r=>gapPercent(r)>0).length,gap_down:observed.filter(r=>gapPercent(r)<0).length,
    flat:observed.filter(r=>gapPercent(r)===0).length,
    live:valid.filter(r=>r.quote_status==='live').length,stale:valid.filter(r=>r.quote_status==='stale').length,
    unavailable:symbols.size-valid.length,volume_available:observed.filter(r=>finite(r.volume)&&r.volume>=0).length,
    vwap_available:observed.filter(r=>positive(r.vwap)&&positive(r.volume)&&r.vwap_source==='Kite average traded price').length};
}
export function marketRegime(groups,rows,benchmark=null){
  const configured=new Set(groups.flatMap(g=>g.stocks.map(s=>'NSE:'+s[0])));
  const unique=[...new Map(rows.filter(r=>configured.has(r.symbol)&&finite(r.change_pct)&&positive(r.ltp)).map(r=>[r.symbol,r])).values()];
  const sectors=groups.map(g=>sectorMetrics(g,unique)),available=sectors.filter(s=>s.available);
  const coverage=configured.size?unique.length/configured.size:0;
  const advance=unique.length?unique.filter(r=>r.change_pct>0).length/unique.length:null;
  const avg=unique.length?unique.reduce((a,r)=>a+r.change_pct,0)/unique.length:null,mid=median(unique.map(r=>r.change_pct));
  const participation=available.length?available.filter(s=>s.median>0&&s.breadth>=.6).length/available.length:null;
  const bearishParticipation=available.length?available.filter(s=>s.median<0&&s.declining/s.available>=.6).length/available.length:null;
  let label='Mixed';const observations=[],contradictions=[],unavailable=[];
  if(coverage<.6||unique.length<Math.min(20,configured.size))label='Insufficient data';
  else if(advance>=.65&&participation>=.6&&avg>=.5&&mid>0)label='Bullish trend';
  else if(advance<=.35&&bearishParticipation>=.6&&avg<=-.5&&mid<0)label='Bearish trend';
  else if(Math.abs(avg)<.25&&Math.abs(mid)<.25&&advance>=.35&&advance<=.65)label='Range-bound';
  const benchmarkTime=instant(benchmark?.quote_timestamp),benchmarkAge=benchmarkTime===null?null:Date.now()-benchmarkTime;
  if(benchmark?.quote_status==='live'&&positive(benchmark.vix)&&benchmarkAge!==null&&benchmarkAge>=0&&benchmarkAge<=60000){
    observations.push(`Observed INDIA VIX ${benchmark.vix.toFixed(2)}`);
    if(label!=='Insufficient data'&&benchmark.vix>=25)label='High volatility';
    else if(label==='Range-bound'&&benchmark.vix<=12)label='Low volatility';
  }else unavailable.push('Verified benchmark/VIX and time-series volatility unavailable.');
  observations.push(`${unique.length}/${configured.size} unique configured stocks observed.`,`${advance===null?'Unavailable':(advance*100).toFixed(1)+'%'} advancing; median move ${mid===null?'unavailable':mid.toFixed(2)+'%'}.`,`${participation===null?'Unavailable':(participation*100).toFixed(1)+'%'} of observed custom baskets have positive median and ≥60% advancing.`);
  if(avg>0&&advance<.5||avg<0&&advance>.5)contradictions.push('Average movement and majority breadth point in opposing directions.');
  if(label==='Bullish trend'&&sectors.some(s=>s.median<0))contradictions.push('Some custom baskets still have negative median movement.');
  if(label==='Bearish trend'&&sectors.some(s=>s.median>0))contradictions.push('Some custom baskets still have positive median movement.');
  if(unique.some(r=>r.quote_status!=='live'))contradictions.push('Includes closed, stale or timestamp-unknown observations; this is not a live whole-market assessment.');
  return {label,coverage,average:avg,median:mid,advancing_fraction:advance,sector_participation:participation,observations,contradictions,unavailable,sectors,
    scope:`Approved ${configured.size}-symbol sector universe and custom baskets only; not the separate personal watchlist, the whole NSE market or official sector indices.`,
    rules:'Bull/bear: ≥65%/≤35% advancing, ≥60% aligned baskets, mean ≥+0.5%/≤−0.5% and aligned median. Range: |mean| and |median| <0.25%, breadth 35–65%. VIX ≥25 high; ≤12 plus range low. Minimum 60% coverage.'};
}

export function instant(raw){
  if(!raw)return null;
  const text=String(raw),stamp=Date.parse(/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d$/.test(text)?text.replace(' ','T')+'+05:30':text);
  return Number.isFinite(stamp)?stamp:null;
}
const indianDateFormat=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'});
export const indianDate=stamp=>indianDateFormat.format(new Date(stamp));
function validCandle(c){return c.source==='kite'&&[c.open,c.high,c.low,c.close].every(positive)&&finite(c.volume)&&c.volume>=0&&c.high>=Math.max(c.open,c.close)&&c.low<=Math.min(c.open,c.close)&&c.high>=c.low;}
export function openingRange(candles,start,minutes,asOf=Date.now()){
  const begins=instant(start),end=begins+minutes*60000;
  const missing={available:false,reason:'Requires every completed one-minute Kite candle from the official session open.'};
  if(begins===null||asOf<end||![5,15].includes(minutes))return missing;
  const map=new Map(candles.filter(c=>c.interval==='minute'&&validCandle(c)&&instant(c.timestamp)+60000<=asOf).map(c=>[instant(c.timestamp),c]));
  const bars=Array.from({length:minutes},(_,i)=>map.get(begins+i*60000));
  if(bars.some(c=>!c))return missing;
  const high=Math.max(...bars.map(c=>c.high)),low=Math.min(...bars.map(c=>c.low));
  const after=[];
  for(let t=end;map.has(t)&&t+60000<=asOf;t+=60000)after.push(map.get(t));
  const last=after.at(-1),earlier=after.slice(0,-1);
  const wasAbove=earlier.some(c=>c.close>high),wasBelow=earlier.some(c=>c.close<low);
  return {available:true,high,low,through:new Date(end).toISOString(),
    breakout:last?last.close>high:null,breakdown:last?last.close<low:null,
    failed_breakout:last?wasAbove&&last.close<=high&&last.close>=low:null,
    failed_breakdown:last?wasBelow&&last.close>=low&&last.close<=high:null,
    retest:last?wasAbove&&last.low<=high&&last.close>=high||wasBelow&&last.high>=low&&last.close<=low:null,
    event_through:last?.timestamp||null};
}
export class VolumeTracker{
  constructor(){this.samples=new Map();this.results=new Map();}
  observe(row){
    const timestamp=instant(row.quote_timestamp),previous=this.samples.get(row.symbol);
    const unavailable={rate:null,rate_ratio:null,acceleration:null,momentum:null,reason:'Needs fresh, ordered observations with comparable uninterrupted windows.'};
    if(row.quote_status!=='live'||timestamp===null||!finite(row.volume)||row.volume<0){this.samples.delete(row.symbol);this.results.set(row.symbol,unavailable);return unavailable;}
    if(previous&&timestamp<=previous.timestamp)return this.results.get(row.symbol)||unavailable;
    const elapsed=previous?(timestamp-previous.timestamp)/1000:null;
    if(!previous||elapsed>90||indianDate(timestamp)!==indianDate(previous.timestamp)||row.volume<previous.volume){this.samples.set(row.symbol,{timestamp,volume:row.volume,price:row.ltp,rate:null,momentum:null});this.results.set(row.symbol,unavailable);return unavailable;}
    if(elapsed<5)return this.results.get(row.symbol)||unavailable;
    const rate=(row.volume-previous.volume)/elapsed*60;
    const momentum=positive(previous.price)&&positive(row.ltp)?(row.ltp/previous.price-1)*100/elapsed*60:null;
    const result={rate,rate_ratio:previous.rate>0?rate/previous.rate:null,acceleration:finite(previous.rate)?rate-previous.rate:null,
      momentum,momentum_acceleration:finite(previous.momentum)&&momentum!==null?momentum-previous.momentum:null,
      reason:'Shares/minute over consecutive observed windows; not historical relative volume or institutional flow.'};
    this.samples.set(row.symbol,{timestamp,volume:row.volume,price:row.ltp,rate,momentum});this.results.set(row.symbol,result);return result;
  }
  reset(){this.samples.clear();this.results.clear();}
}
export function openingIntelligence(row,context={},session={},asOf=Date.now()){
  const gap=gapPercent(row),stamp=instant(row.quote_timestamp);
  const sameSession=stamp!==null&&row.opening_date===indianDate(stamp);
  const fill=gap!==null&&gap!==0&&positive(row.ltp)&&sameSession?clamp((row.open-row.ltp)/(row.open-row.prev_close)*100,0,100):gap===0?0:null;
  const validVWAP=positive(row.vwap)&&positive(row.volume)&&row.vwap_source==='Kite average traded price';
  const rangeValid=positive(row.day_high)&&positive(row.day_low)&&row.day_high>row.day_low&&positive(row.ltp)&&row.ltp>=row.day_low&&row.ltp<=row.day_high;
  const previous=context.session_date===row.opening_date?(context.daily||[]).find(c=>c.interval==='day'&&validCandle(c)&&String(c.timestamp).slice(0,10)===context.previous_session_date):null;
  const start=session.calendar_verified&&session.is_trading_day&&session.trading_date===row.opening_date?`${row.opening_date}T${session.opening_time}+05:30`:null;
  const ranges={five:openingRange(context.minutes||[],start,5,asOf),fifteen:openingRange(context.minutes||[],start,15,asOf)};
  const bars=start?(context.minutes||[]).filter(c=>c.interval==='minute'&&validCandle(c)&&instant(c.timestamp)>=instant(start)&&instant(c.timestamp)+60000<=asOf).sort((a,b)=>instant(a.timestamp)-instant(b.timestamp)):[];
  const recent=bars.slice(-4),continuous=recent.length>=3&&recent.every((c,i)=>i===0||instant(c.timestamp)-instant(recent[i-1].timestamp)===60000);
  let structure='Unavailable — complete consecutive candles required';
  if(continuous){const last=recent.slice(-3);if(last.every((c,i)=>!i||c.high>last[i-1].high&&c.low>last[i-1].low))structure='Higher highs and higher lows';else if(last.every((c,i)=>!i||c.high<last[i-1].high&&c.low<last[i-1].low))structure='Lower highs and lower lows';else if((Math.max(...last.map(c=>c.high))/Math.min(...last.map(c=>c.low))-1)*100<=.3)structure='Consolidation (three-candle range ≤0.3%)';else structure='Mixed completed-candle structure';}
  const spread=positive(row.best_bid)&&positive(row.best_ask)&&row.best_ask>=row.best_bid?row.best_ask-row.best_bid:null;
  const depthTotal=row.depth_bid_quantity+row.depth_ask_quantity;
  const imbalance=finite(row.depth_bid_quantity)&&finite(row.depth_ask_quantity)&&row.depth_bid_quantity>=0&&row.depth_ask_quantity>=0&&depthTotal>0?(row.depth_bid_quantity-row.depth_ask_quantity)/depthTotal:null;
  return {gap_pct:gap,opening_class:gap===null?'Unavailable':gap===0?'Flat opening':gap>0?'Gap up':'Gap down',gap_fill_pct:fill,
    vwap:validVWAP?row.vwap:null,vwap_distance_pct:validVWAP&&positive(row.ltp)?(row.ltp/row.vwap-1)*100:null,
    range_position:rangeValid?(row.ltp-row.day_low)/(row.day_high-row.day_low)*100:null,
    previous_high:previous?.high??null,previous_low:previous?.low??null,
    previous_high_breakout:previous&&positive(row.ltp)?row.ltp>previous.high:null,previous_low_breakdown:previous&&positive(row.ltp)?row.ltp<previous.low:null,
    ranges,structure,range_expansion:continuous&&recent.length===4?(recent.at(-1).high-recent.at(-1).low)>1.5*median(recent.slice(0,-1).map(c=>c.high-c.low)):null,
    spread,spread_pct:spread!==null?(spread/((row.best_bid+row.best_ask)/2))*100:null,depth_imbalance:imbalance,
    relative_volume:null,relative_volume_reason:'No licensed comparable same-time historical volume baseline loaded.'};
}

export const DEFAULT_WEIGHTS=Object.freeze({opening:20,sector:20,price:20,volume:15,liquidity:10,freshness:15});
export function validateWeights(raw={}){
  const weights={};for(const [key,value]of Object.entries(DEFAULT_WEIGHTS)){const n=raw[key]??value;if(!finite(n)||n<0||n>100)throw new Error('Weights must be numbers from 0 to 100.');weights[key]=n;}
  if(!Object.values(weights).some(v=>v>0))throw new Error('At least one weight must be positive.');return weights;
}
export function opportunity(row,groups,sectorResults,analysis,volume={},rawWeights=DEFAULT_WEIGHTS){
  const weights=validateWeights(rawWeights),supporting=[],contradictory=[],unavailable=[],factors={};
  const baskets=groups.filter(g=>g.stocks.some(s=>'NSE:'+s[0]===row.symbol));
  const direction=finite(row.change_pct)&&row.change_pct!==0?Math.sign(row.change_pct):null;
  if(row.match){factors.opening=1;supporting.push('Original exact opening match (₹0 difference).');}
  else if(row.near_match){factors.opening=.7;supporting.push('Original near opening match within the configured absolute difference.');}
  else if(analysis.gap_pct!==null){factors.opening=direction&&Math.sign(analysis.gap_pct)===direction?.5:0;contradictory.push('Opening is outside the original exact/near match conditions.');}
  else unavailable.push('Official opening reference unavailable.');
  const sector=baskets.map(g=>sectorResults.find(s=>s.id===g.id)).filter(s=>s&&s.available/s.total>=.6&&s.breadth!==null);
  if(sector.length&&direction){const aligned=sector.reduce((sum,s)=>sum+(direction>0?s.breadth:s.declining/s.available),0)/sector.length;factors.sector=aligned;if(aligned>=.6)supporting.push('At least 60% of observed sector constituents align with this stock’s direction.');else contradictory.push('Sector participation is weak or opposes the observed stock direction.');}
  else unavailable.push('Sufficient sector coverage or directional movement unavailable.');
  if(analysis.vwap_distance_pct!==null&&direction){factors.price=Math.sign(analysis.vwap_distance_pct)===direction?1:0;if(factors.price)supporting.push('Price is on the directionally aligned side of provider VWAP.');else contradictory.push('Price is on the opposing side of provider VWAP.');}
  else if(direction&&analysis.ranges.fifteen.available&&analysis.ranges.fifteen.breakout!==null){factors.price=(direction>0?analysis.ranges.fifteen.breakout:analysis.ranges.fifteen.breakdown)?1:0;if(factors.price)supporting.push('Completed 15-minute opening-range price confirmation.');else contradictory.push('No aligned completed-candle opening-range confirmation.');}
  else unavailable.push('Valid VWAP or completed-candle price confirmation unavailable.');
  if(volume.rate_ratio!==null&&finite(volume.rate_ratio)){factors.volume=volume.rate_ratio>=1.5?Math.min(1,volume.rate_ratio/2):0;if(factors.volume)supporting.push('Observed-window volume rate increased at least 1.5×; this is not historical RVOL.');else contradictory.push('Observed-window volume rate does not confirm acceleration.');}
  else unavailable.push('Consecutive fresh volume windows unavailable.');
  if(analysis.spread_pct!==null){factors.liquidity=analysis.spread_pct<=.25?1:analysis.spread_pct<1?(1-analysis.spread_pct)/.75:0;if(analysis.spread_pct>.5)contradictory.push('Wide supplied bid/ask spread reduces liquidity quality.');else supporting.push('Supplied bid/ask spread is no wider than 0.5%.');}
  else unavailable.push('Valid bid/ask spread unavailable; liquidity cannot be confirmed.');
  if(row.quote_status==='live'){factors.freshness=1;supporting.push('Provider timestamp passes the server freshness check.');}
  else{factors.freshness=0;contradictory.push(`Quote status is ${row.quote_status||'unknown'}; fresh confirmation is absent.`);}
  for(const r of Object.values(analysis.ranges))if(r.failed_breakout||r.failed_breakdown){contradictory.push('A completed-candle opening-range break failed.');factors.price=0;}
  const total=Object.values(weights).reduce((a,b)=>a+b,0),earned=Object.entries(factors).reduce((sum,[key,value])=>sum+value*weights[key],0);
  const coverage=Object.keys(factors).reduce((sum,key)=>sum+weights[key],0)/total*100;
  return {symbol:row.symbol,sectors:baskets.map(g=>g.name),sector_strength:sector.length?sector.reduce((a,s)=>a+s.strength,0)/sector.length:null,
    ltp:row.ltp,difference:row.difference,gap_pct:analysis.gap_pct,score:positive(row.ltp)?Math.round(earned/total*100):null,coverage,
    quality:row.quote_status||'unavailable',supporting,contradictory,unavailable,factors,
    explanation:`${supporting.length} supporting, ${contradictory.length} contradictory and ${unavailable.length} unavailable observations. Missing factors contribute zero; weights are never redistributed. Relevance is not probability of profit.`};
}

export function riskPlan(input){
  const cents=(raw,label,optional=false)=>{if(optional&&(raw===''||raw==null))return null;const n=Number(raw);if(!finite(n)||n<0||n>1e10||Math.abs(n*100-Math.round(n*100))>1e-5)throw new Error(label+' must be a nonnegative amount with at most two decimals.');return BigInt(Math.round(n*100));};
  const capital=cents(input.capital,'Capital'),entry=cents(input.entry,'Entry'),stop=cents(input.stop,'Stop'),fees=cents(input.brokerage??0,'Round-trip fees'),slip=cents(input.slippage??0,'Round-trip slippage/share'),target=cents(input.target,'Target',true);
  const risk=Number(input.risk_percent),side=input.side||'long';
  if(capital<=0n||entry<=0n||stop<=0n||!finite(risk)||risk<=0||risk>100||!['long','short'].includes(side)||entry===stop)throw new Error('Enter positive capital/prices, risk >0 and ≤100%, and a distinct valid stop.');
  if(side==='long'&&stop>=entry||side==='short'&&stop<=entry)throw new Error('Long stops must be below entry; short stops above entry.');
  if(target!==null&&(side==='long'&&target<=entry||side==='short'&&target>=entry))throw new Error('Target must be beyond entry in the planned direction.');
  const budget=capital*BigInt(Math.floor(risk*10000))/1000000n;
  const distance=entry>stop?entry-stop:stop-entry,unit=distance+slip;
  let quantity=budget>fees?(budget-fees)/unit:0n;
  const affordable=capital>fees?(capital-fees)/(entry+slip):0n;
  if(quantity>affordable)quantity=affordable;
  const costs=quantity>0n?fees+quantity*slip:0n,loss=quantity*distance+costs;
  const reward=target!==null?quantity*(target>entry?target-entry:entry-target)-costs:null;
  const amount=v=>Number(v)/100;
  return {planned_risk:amount(budget),quantity:Number(quantity),position_value:amount(quantity*entry),estimated_costs:amount(costs),estimated_loss_at_stop:amount(loss),reward_risk:reward!==null&&loss>0n?Number(reward)/Number(loss):null,
    estimated_reward:reward===null?null:amount(reward),note:'Cash-capital limit applied. Fees are your total round-trip estimate; slippage is your round-trip amount per share. Actual losses can exceed planned risk because of gaps and slippage.'};
}

export const DEFAULT_ALERTS=Object.freeze({enabled:false,cooldown:300,gap:1,sector_change:10,volume_ratio:2,types:['exact','near','gap','sector','breakout','breakdown','vwap','volume','stale','provider']});
export function validateAlerts(raw={}){
  const settings={...DEFAULT_ALERTS,...raw,enabled:raw.enabled===true};
  for(const [key,min,max]of [['cooldown',10,86400],['gap',0,100],['sector_change',1,100],['volume_ratio',1.1,100]])if(!finite(settings[key])||settings[key]<min||settings[key]>max)throw new Error('Invalid alert '+key+' threshold.');
  if(!Array.isArray(settings.types)||settings.types.some(t=>!DEFAULT_ALERTS.types.includes(t)))throw new Error('Unknown alert type.');return settings;
}
export class AlertEngine{
  constructor(settings={}){this.settings=validateAlerts(settings);this.active=new Set();this.last=new Map();this.history=[];this.sectors=new Map();this.vwapSides=new Map();this.session=null;}
  evaluate({rows=[],sectors=[],market={},error=null,providerDisconnected=false,analyses=new Map(),volumes=new Map()},now=Date.now()){
    if(!this.settings.enabled){this.active.clear();return [];}
    const day=market.trading_date||indianDate(now);if(this.session!==day){this.active.clear();this.vwapSides.clear();this.sectors.clear();this.last.clear();this.session=day;}
    if(providerDisconnected||error)this.vwapSides.clear();
    const candidates=[],consider=(type,key,message,symbol='System')=>{if(this.settings.types.includes(type))candidates.push({type,key:type+':'+day+':'+key,message,symbol});};
    if(error||providerDisconnected)consider('provider','connection','Provider disconnected or unavailable.');
    for(const row of rows){
      if(row.quote_status==='stale')consider('stale',row.symbol,`${row.symbol}: stale provider quote.`,row.symbol);
      if(row.quote_status!=='live'||!market.is_open){this.vwapSides.delete(row.symbol);continue;}
      const a=analyses.get(row.symbol)||openingIntelligence(row),v=volumes.get(row.symbol)||{};
      if(row.match)consider('exact',row.symbol,`${row.symbol}: original exact opening match.`,row.symbol);
      if(row.near_match)consider('near',row.symbol,`${row.symbol}: original near opening match.`,row.symbol);
      if(a.gap_pct!==null&&Math.abs(a.gap_pct)>=this.settings.gap)consider('gap',row.symbol,`${row.symbol}: opening gap threshold reached.`,row.symbol);
      if(Object.values(a.ranges).some(r=>r.available&&r.breakout))consider('breakout',row.symbol,`${row.symbol}: completed-candle opening-range breakout.`,row.symbol);
      if(Object.values(a.ranges).some(r=>r.available&&r.breakdown))consider('breakdown',row.symbol,`${row.symbol}: completed-candle opening-range breakdown.`,row.symbol);
      const side=a.vwap_distance_pct===null?null:Math.sign(a.vwap_distance_pct),prior=this.vwapSides.get(row.symbol),stamp=instant(row.quote_timestamp);
      if(side!==null&&stamp!==null&&(!prior||stamp>prior.stamp)){if(side>0&&prior?.side<0&&stamp-prior.stamp<=90000)consider('vwap',row.symbol,`${row.symbol}: observed VWAP reclaim.`,row.symbol);this.vwapSides.set(row.symbol,{side,stamp});}
      if(finite(v.rate_ratio)&&v.rate_ratio>=this.settings.volume_ratio)consider('volume',row.symbol,`${row.symbol}: consecutive-window volume activity threshold reached; not historical RVOL.`,row.symbol);
    }
    for(const s of sectors){const prior=this.sectors.get(s.id);if(finite(s.strength)&&market.is_open&&s.live/s.total>=.6){if(finite(prior)&&Math.abs(s.strength-prior)>=this.settings.sector_change){consider('sector',s.id,`${s.name}: observed basket strength changed by the configured threshold.`,s.name);this.sectors.set(s.id,s.strength);}else if(!finite(prior))this.sectors.set(s.id,s.strength);}}
    const next=new Set(candidates.map(c=>c.key)),events=[];
    for(const candidate of candidates){if(this.active.has(candidate.key)||now-(this.last.get(candidate.key)??-Infinity)<this.settings.cooldown*1000)continue;const event={...candidate,at:new Date(now).toISOString()};events.push(event);this.last.set(candidate.key,now);}
    this.active=next;this.history=[...events,...this.history].slice(0,200);return events;
  }
}
