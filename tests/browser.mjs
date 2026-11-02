// Real-browser integration checks using installed Chrome and Node's native CDP client.
// Runs against the actual FastAPI server; no fabricated market-data responses.
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DIVINE_TEST_URL || 'http://127.0.0.1:8000';
const qa = path.resolve('.qa');
await mkdir(qa, {recursive:true});
const profile = await mkdtemp(path.join(qa, 'chrome-'));
const chrome = spawn(process.env.CHROME_EXECUTABLE || 'C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir='+profile, 'about:blank'], {windowsHide:true, stdio:['ignore','ignore','pipe']});
const sleep = ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws;
let passed=0;
try {
  const endpoint = await new Promise((resolve,reject)=>{
    let stderr='';const timer=setTimeout(()=>reject(new Error('Chrome DevTools startup timed out')),15000);
    chrome.stderr.on('data',chunk=>{stderr+=chunk;const match=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
    chrome.on('error',reject);chrome.on('exit',code=>{clearTimeout(timer);reject(new Error('Chrome exited: '+code));});
  });
  const port=new URL(endpoint).port;
  const target=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let serial=0;const pending=new Map();const errors=[];
  ws.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id){const task=pending.get(msg.id);if(task){clearTimeout(task.timer);pending.delete(msg.id);msg.error?task.reject(new Error(JSON.stringify(msg.error))):task.resolve(msg.result);}}else if(msg.method==='Runtime.exceptionThrown'){errors.push(msg.params.exceptionDetails.text);}else if(msg.method==='Network.responseReceived'&&msg.params.response.status>=400){errors.push(msg.params.response.status+' '+msg.params.response.url);}};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const response=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(response.exceptionDetails)throw new Error(response.exceptionDetails.text);return response.result.value;};
  const wait=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await sleep(100);}throw new Error('DOM condition timed out: '+expression);};
  const check=(label,condition)=>{assert.ok(condition,label);passed++;console.log('PASS '+label);};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base+'/'});
  await wait("document.querySelectorAll('.sector-card').length===16");
  await evaluate('document.fonts.ready.then(()=>true)');
  check('16 original sector cards',await evaluate("document.querySelectorAll('.sector-card').length===16"));
  check('desktop layout fits viewport',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  check('four-column desktop sector grid',await evaluate("getComputedStyle(document.querySelector('.sector-grid')).gridTemplateColumns.split(' ').length===4"));
  check('one compact IST clock above the ticker and hero',await evaluate("document.querySelectorAll('#liveClock').length===1&&!!(document.querySelector('header').compareDocumentPosition(document.querySelector('.market-clock-strip'))&4)&&!!(document.querySelector('.market-clock-strip').compareDocumentPosition(document.querySelector('.ticker'))&4)&&!!(document.querySelector('.ticker').compareDocumentPosition(document.querySelector('.hero'))&4)"));
  check('IST date includes actual weekday and date',await evaluate("document.querySelector('#liveDate').textContent===new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',weekday:'short',day:'2-digit',month:'short',year:'numeric'}).format(new Date()).toUpperCase()"));
  await wait("[...document.querySelectorAll('.premium-hero img')].every(i=>i.complete&&i.naturalWidth>0)");
  check('two new original hero assets replace the old artwork',await evaluate("document.querySelectorAll('.premium-hero img').length===2&&document.querySelectorAll('img[src*=\"hero-art.svg\"]').length===0"));
  check('bullish and bearish headings have matching arrows',await evaluate("document.querySelector('.stat-card.green .market-heading-arrow').textContent.includes('▲')&&document.querySelector('.stat-card.red .market-heading-arrow').textContent.includes('▼')&&getComputedStyle(document.querySelector('.stat-card.green>strong')).color==='rgb(0, 230, 138)'&&getComputedStyle(document.querySelector('.stat-card.red>strong')).color==='rgb(255, 69, 101)'"));
  check('dashboard includes the opening scanner',await evaluate("!!document.querySelector('.dashboard-scanner .scanner-panel')"));
  const before=await evaluate("({clock:document.querySelector('#liveClock').textContent,origin:performance.timeOrigin,ticker:document.querySelector('#tickerTrack').textContent})");
  await sleep(4000);
  const after=await evaluate("({clock:document.querySelector('#liveClock').textContent,origin:performance.timeOrigin,ticker:document.querySelector('#tickerTrack').textContent})");
  check('clock advances without reloading',before.clock!==after.clock&&before.origin===after.origin);
  const snapshot=await evaluate("fetch('/api/quotes').then(r=>r.json()).then(q=>({count:q.rows.length,transport:q.transport,live:q.rows.filter(r=>r.quote_status==='live').length,top:q.top_performers.length,sorted:q.top_performers.every((r,i,a)=>i===0||a[i-1].change_pct>=r.change_pct)}))");
  check('verified ticker is sorted by percentage change',snapshot.sorted);
  if(snapshot.live){check('real Kite values update through SSE without reloading',before.ticker!==after.ticker&&before.origin===after.origin);}else if(snapshot.top){check('non-live quotes are explicitly labeled',await evaluate("[...document.querySelectorAll('.ticker-stock small')].every(n=>/closed|stale/.test(n.textContent))"));}else{check('disconnected quotes remain explicitly unavailable',await evaluate("document.querySelector('#tickerTrack').textContent.includes('Awaiting verified Kite quotes')"));}
  check('NSE calendar label agrees across navigation clock and ticker',await evaluate("fetch('/api/calendar').then(r=>r.json()).then(c=>['navMarketStatus','sessionStatus','tickerMarketStatus'].every(id=>document.getElementById(id).textContent.includes(c.label)))"));
  await evaluate("document.querySelector('#tickerPause').click()");
  check('ticker pause control',await evaluate("(getComputedStyle(document.querySelector('#tickerTrack')).animationPlayState==='paused'||getComputedStyle(document.querySelector('#tickerTrack')).animationName==='none')&&document.querySelector('#tickerPause').getAttribute('aria-pressed')==='true'"));
  await evaluate("document.querySelector('#tickerPause').click()");
  check('ticker resume control',await evaluate("document.querySelector('#tickerPause').getAttribute('aria-pressed')==='false'"));
  check('bullish green and bearish red',await evaluate("getComputedStyle(document.querySelector('.positive')).color==='rgb(0, 230, 138)'&&getComputedStyle(document.querySelector('.negative')).color==='rgb(255, 69, 101)'"));
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(qa,'dashboard-desktop.png'),Buffer.from(shot.data,'base64'));
  for(const [width,height,columns]of [[768,1024,3],[375,812,2]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(150);
    check(`${width}px dashboard has no horizontal overflow`,await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    check(`${width}px sector columns`,await evaluate(`getComputedStyle(document.querySelector('.sector-grid')).gridTemplateColumns.split(' ').length===${columns}`));
    check(`${width}px Connect Kite is reachable`,await evaluate("(()=>{const e=document.querySelector('.connect'),r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})()"));
  }
  const mobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(qa,'dashboard-mobile.png'),Buffer.from(mobile.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('a[href=\"/sectors/banking\"].sector-card').click()");
  await wait("location.pathname==='/sectors/banking'&&!!document.querySelector('#stockBody')");
  check('sector route has eight financial columns',await evaluate("document.querySelectorAll('thead th').length===8"));
  check('ten configured sector entries',await evaluate("document.querySelectorAll('#stockBody tr').length===10"));
  check('sticky table headings',await evaluate("getComputedStyle(document.querySelector('th')).position==='sticky'"));
  check('desktop headings are larger and high contrast',await evaluate("parseFloat(getComputedStyle(document.querySelector('th')).fontSize)>=15&&Number(getComputedStyle(document.querySelector('th')).fontWeight)>=700"));
  check('Difference column is wide with large tabular numbers',await evaluate("parseFloat(getComputedStyle(document.querySelector('th[data-column=difference]')).minWidth)>=180&&parseFloat(getComputedStyle(document.querySelector('.difference-value')).fontSize)>=16&&getComputedStyle(document.querySelector('.difference-value')).fontVariantNumeric.includes('tabular-nums')"));
  check('Difference movement badges have correct colors',await evaluate("[...document.querySelectorAll('.difference-value')].every(n=>getComputedStyle(n).color===(n.classList.contains('positive')?'rgb(0, 230, 138)':n.classList.contains('negative')?'rgb(255, 69, 101)':n.classList.contains('exact')?'rgb(0, 216, 255)':'rgb(154, 171, 196)'))"));
  const scannerDesktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(qa,'scanner-desktop.png'),Buffer.from(scannerDesktop.data,'base64'));
  await evaluate("const input=document.querySelector('#stockSearch');input.value='HDFCBANK';input.dispatchEvent(new Event('input',{bubbles:true}))");
  check('scanner search',await evaluate("document.querySelectorAll('#stockBody tr').length===1&&document.querySelector('#stockBody').textContent.includes('HDFCBANK')"));
  await evaluate("document.querySelector('[data-action=reset]').click();document.querySelector('[data-sort=change_pct]').click()");
  check('scanner sort semantics',await evaluate("document.querySelector('th[data-column=change_pct]').getAttribute('aria-sort')!=='none'"));
  await evaluate("document.querySelector('[data-filter=exact]').click()");
  check('exact-match filter',await evaluate("document.querySelector('[data-filter=exact]').getAttribute('aria-pressed')==='true'&&[...document.querySelectorAll('#stockBody .match-badge')].every(n=>n.textContent==='EXACT MATCH')"));
  for(const filter of ['near','bull','bear']){
    await evaluate(`document.querySelector('[data-filter=${filter}]').click()`);
    check(filter+' scanner filter',await evaluate(`document.querySelector('[data-filter=${filter}]').getAttribute('aria-pressed')==='true'`));
  }
  await evaluate("document.querySelector('[data-action=reset]').click()");
  await send('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:false});
  check('mobile stock table scrolls within page',await evaluate("document.documentElement.scrollWidth<=innerWidth&&document.querySelector('.table-wrap').scrollWidth>document.querySelector('.table-wrap').clientWidth"));
  check('mobile headings remain readable',await evaluate("parseFloat(getComputedStyle(document.querySelector('th')).fontSize)>=13&&parseFloat(getComputedStyle(document.querySelector('th')).fontSize)<=14"));
  await evaluate("document.querySelector('.scanner-panel').scrollIntoView();document.querySelector('.table-wrap').scrollLeft=650");
  const scannerMobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(qa,'scanner-mobile.png'),Buffer.from(scannerMobile.data,'base64'));
  const groups=await evaluate("fetch('/static/sector-universe.json').then(r=>r.json()).then(u=>u.groups.map(g=>g.id))");
  for(const id of groups){
    await evaluate(`history.pushState({},'',${JSON.stringify('/sectors/')}+${JSON.stringify(id)});dispatchEvent(new PopStateEvent('popstate'))`);
    await wait("document.querySelectorAll('#stockBody tr').length===10");
    check('sector route '+id,await evaluate(`location.pathname===${JSON.stringify('/sectors/'+id)}&&document.querySelectorAll('thead th').length===8&&document.documentElement.scrollWidth<=innerWidth`));
  }
  await evaluate("document.querySelector('nav a[href=\"/ai-predictions\"]').click()");
  await wait("!!document.querySelector('#aiContent .ai-empty')||!!document.querySelector('#aiContent table')");
  check('AI unavailable state is explicit without fake predictions',await evaluate("document.querySelector('#aiContent').textContent.includes('Prediction unavailable')||document.querySelector('#aiContent').textContent.includes('MODEL FORECASTS')"));
  check('mobile AI page fits viewport',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  await evaluate("document.querySelector('nav a[href=\"/history\"]').click()");
  await wait("!!document.querySelector('#importSummary .metric')");
  check('durable history import controls and policy',await evaluate("fetch('/api/history/imports').then(r=>r.json()).then(s=>!!document.querySelector('[data-action=incremental]')&&(!s.retention_authorized?document.querySelector('[data-action=import]').disabled:true)&&document.querySelector('#importSummary').textContent.includes('Last successful import'))"));
  check('mobile history page fits viewport',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  await evaluate("document.querySelector('nav a[href=\"/settings\"]').click()");
  await wait("!!document.querySelector('#reconciliationContent .metric')");
  check('complete reconciliation report is available',await evaluate("fetch('/api/instruments/reconciliation').then(r=>r.json()).then(r=>r.total_configured_entries===160&&r.unique_requested_instruments===148&&r.duplicate_membership_count===12&&r.instruments.length===148)"));
  check('mobile settings page fits viewport',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  check('reduced motion disables ticker animation',await evaluate("getComputedStyle(document.querySelector('#tickerTrack')).animationName==='none'"));
  check('no JavaScript or failed resource errors',errors.length===0);
  console.log(JSON.stringify({passed,provider:snapshot,errors,screenshots:['.qa/dashboard-desktop.png','.qa/dashboard-mobile.png']}));
} finally {
  if(ws)ws.close();chrome.kill();
}
