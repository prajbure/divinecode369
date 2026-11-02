// Isolated real-Chrome tests; IPO responses intercepted with labelled fixtures.
import {spawn} from 'node:child_process';
import {mkdir,mkdtemp,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const base=process.env.DIVINE_TEST_URL||'http://127.0.0.1:8000';
const fixtures=JSON.parse(await readFile('.qa/ipo-fixtures.json','utf8'));
const qa=path.resolve('.qa');await mkdir(qa,{recursive:true});
const profile=await mkdtemp(path.join(qa,'ipo-chrome-'));
const chrome=spawn(process.env.CHROME_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,passed=0;const checks=[],screenshots=[];
try{
  const endpoint=await new Promise((resolve,reject)=>{let stderr='';const timer=setTimeout(()=>reject(Error('Chrome startup timeout')),15000);chrome.stderr.on('data',chunk=>{stderr+=chunk;const match=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});chrome.on('error',reject);});
  const target=await(await fetch(`http://127.0.0.1:${new URL(endpoint).port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let serial=0;const pending=new Map(),errors=[],calls=[];
  let intercept=false,stockOutage=false;
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.id){const task=pending.get(msg.id);if(task){clearTimeout(task.timer);pending.delete(msg.id);msg.error?task.reject(Error(JSON.stringify(msg.error))):task.resolve(msg.result);}}
    else if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);
    else if(msg.method==='Fetch.requestPaused'){
      const request=msg.params,url=new URL(request.request.url);
      if(url.pathname.startsWith('/api/ipo/')&&intercept){calls.push(url.pathname);send('Fetch.fulfillRequest',{requestId:request.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(fixtures[url.pathname]||{provider:fixtures['/api/ipo/overview'].provider,meta:{available:true}})).toString('base64')}).catch(error=>errors.push(error.message));}
      else if(stockOutage&&url.pathname==='/api/status')send('Fetch.fulfillRequest',{requestId:request.requestId,responseCode:503,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from('{"detail":"TEST FIXTURE stock outage"}').toString('base64')}).catch(error=>errors.push(error.message));
      else send('Fetch.continueRequest',{requestId:request.requestId}).catch(error=>errors.push(error.message));
    }
  };
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const wait=async expression=>{for(let i=0;i<120;i++){if(await evaluate(expression))return;await sleep(100);}throw Error('DOM wait failed: '+expression);};
  const check=(label,condition)=>{assert.ok(condition,label);passed++;checks.push(label);console.log('PASS '+label);};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const route=async screen=>{await evaluate(`document.querySelector('.ipo-nav a[href="/ipo${screen?'/'+screen:''}"]').click()`);await wait("!document.querySelector('#ipoContent').textContent.includes('Loading the IPO workspace')");};
  async function shot(name,scrollSelector){await evaluate("document.getElementById('toast').hidden=true");if(scrollSelector)await evaluate(`document.querySelector(${JSON.stringify(scrollSelector)}).scrollIntoView({block:'start'})`);await sleep(150);const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('reports/'+name,Buffer.from(image.data,'base64'));screenshots.push('reports/'+name);}
  const sticky="(()=>{const r=document.querySelector('#headerClock').getBoundingClientRect();return r.top>=0&&r.bottom<innerHeight&&getComputedStyle(document.querySelector('.topbar')).position==='sticky';})()";
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"window.clockIntervals=0;const originalInterval=window.setInterval;window.setInterval=function(fn,delay,...args){if(delay===1000)window.clockIntervals++;return originalInterval(fn,delay,...args);};"});
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  const status=await(await fetch(base+'/api/ipo/status')).json();
  if(!status.configured){
    await send('Page.navigate',{url:base+'/ipo'});await wait("!!document.querySelector('.ipo-summary')");
    check('unconfigured integration opens independently and reports unavailable counts',await evaluate("document.querySelector('#ipoHealth').textContent.includes('not configured')&&[...document.querySelectorAll('.ipo-summary strong')].every(v=>!/^[0-9]+$/.test(v.textContent))"));
    await shot('ipo-dashboard-unconfigured.png','#ipoTerminal');
    for(const width of [375,320]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});check(`${width}px unconfigured cards do not clip`,await evaluate('document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll(".ipo-summary button")].every(v=>v.scrollWidth<=v.clientWidth)'));}
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  }
  intercept=true;
  await send('Fetch.enable',{patterns:[{urlPattern:'*/api/ipo/*'},{urlPattern:'*/api/status'}]});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"new MutationObserver(()=>{const root=document.querySelector('#ipoTerminal');if(root&&!root.querySelector('.ipo-test-banner'))root.insertAdjacentHTML('afterbegin','<div class=\"ipo-test-banner\" style=\"position:sticky;top:var(--header-height);z-index:5\">TEST FIXTURE DATA — NOT LIVE MARKET DATA</div>');}).observe(document,{subtree:true,childList:true});"});
  await send('Emulation.setTimezoneOverride',{timezoneId:'America/Los_Angeles'});
  await send('Page.navigate',{url:base+'/ipo'});await wait("document.querySelectorAll('#ipoResults tbody tr').length===7");
  await evaluate('document.fonts.ready.then(()=>true)');
  check('IPO tab is immediately after existing AI Predictions',await evaluate("(()=>{const links=[...document.querySelectorAll('#navigation>a')],ai=links.findIndex(a=>a.pathname==='/ai-predictions');return links[ai+1].pathname==='/ipo'&&links[ai+1].textContent==='IPO Intelligence';})()"));
  check('dedicated IPO dashboard has eight overview cards and no scanner',await evaluate("document.querySelectorAll('.ipo-summary button').length===8&&!document.querySelector('#stockBody')"));
  check('attribution is readable, clickable and has no nofollow',await evaluate("(()=>{const a=document.querySelector('.ipo-credit a');return a.href==='https://www.ipoguru.in/'&&getComputedStyle(a).fontSize==='16px'&&!a.rel.includes('nofollow')})()"));
  check('IPO title and company typography are large',await evaluate("parseFloat(getComputedStyle(document.querySelector('.ipo-terminal h1')).fontSize)>=30&&parseFloat(getComputedStyle(document.querySelector('.ipo-table td a')).fontSize)>=19"));
  check('source and successful fetch timestamps are separate',await evaluate("document.querySelector('#ipoHealth').textContent.includes('Last successful fetch')&&document.querySelector('#ipoResults').textContent.includes('source freshness')"));
  await shot('ipo-dashboard-desktop-fixture.png','#ipoTerminal');
  await evaluate("const search=document.querySelector('#ipoSearch');search.value='Bluefield';search.dispatchEvent(new Event('input',{bubbles:true}));");
  check('IPO search filters independently',await evaluate("document.querySelectorAll('#ipoResults tbody tr').length===1&&document.querySelector('#ipoResults').textContent.includes('Bluefield')"));
  await click('#ipoClear');await click('[data-ipo-bucket=mainboard]');
  check('board overview cards preserve original stock universe',await evaluate("document.querySelectorAll('#ipoResults tbody tr').length===4"));
  await click('#ipoClear');
  await evaluate("const select=document.querySelector('#ipoSort');select.value='gmp';select.dispatchEvent(new Event('change',{bubbles:true}));");
  check('GMP sorting keeps the strongest arithmetic sentiment first',await evaluate("document.querySelector('#ipoResults tbody tr').textContent.includes('Aster')"));
  for(const checkbox of [0,1,2,3,4,5])await evaluate(`document.querySelectorAll('[data-ipo-compare]')[${checkbox}].click()`);
  check('comparison limits selection to five',await evaluate("document.querySelectorAll('[data-ipo-compare]:checked').length===5"));
  await route('compare');await wait("!!document.querySelector('#ipoComparison table')");
  check('comparison shows five IPO columns and reported financials',await evaluate("document.querySelectorAll('#ipoComparison th').length===6&&document.querySelector('#ipoComparison').textContent.includes('Reported financials')"));
  await route('gmp');await wait("!!document.querySelector('.ipo-gmp-chart')");
  check('GMP history uses a real SVG chart with seven day-wise fixture points',await evaluate("document.querySelectorAll('#ipoSelectedContent tbody tr').length===7&&document.querySelector('#ipoSelectedContent').textContent.includes('Day-wise closing')"));
  check('unofficial GMP warning is prominent',await evaluate("document.querySelector('.ipo-warning').textContent.includes('unofficial and speculative')"));
  await shot('ipo-gmp-chart-fixture.png','.ipo-chart-panel');
  const callCount=calls.length;await sleep(2200);
  check('IPO pages do not create per-tab polling',calls.length===callCount);
  await route('subscription');await wait("document.querySelectorAll('.ipo-subscription-row').length===6");
  check('subscription categories include QIB, NII, Retail and reserved categories',await evaluate("['Qualified Institutional','Non-Institutional','Retail','Employee','Shareholder','Total'].every(v=>document.querySelector('#ipoSelectedContent').textContent.includes(v))"));
  check('real zero employee subscription remains visible',await evaluate("[...document.querySelectorAll('.ipo-subscription-row')].some(v=>v.textContent.includes('Employee')&&v.textContent.includes('0×'))"));
  await shot('ipo-subscription-fixture.png','#ipoSelect');
  await route('allotment');await wait("!!document.querySelector('#ipoSelectedContent a[target=_blank]')");
  check('allotment opens the verified official registrar site',await evaluate("document.querySelector('#ipoSelectedContent a[target=_blank]').href==='https://ipo.bigshareonline.com/ipo_status.html'&&!document.querySelector('input[name=pan]')"));
  await route('listings');await wait("!!document.querySelector('#ipoResults table')");
  check('listing page separates actual listing from GMP estimates',await evaluate("document.querySelector('#ipoResults').textContent.includes('Actual reported exchange')&&document.querySelector('#ipoResults').textContent.includes('22%')&&document.querySelectorAll('#ipoResults tbody tr').length===1"));
  await click('[data-ipo-listing]');await wait("document.querySelector('#ipoResults').textContent.includes('Archived daily reading')");
  check('listing comparison uses a verified pre-listing archived daily GMP',await evaluate("document.querySelector('#ipoResults').textContent.includes('Actual exchange listing')&&document.querySelector('#ipoResults').textContent.includes('₹238')"));
  await route('calendar');await wait("!!document.querySelector('.ipo-calendar article')");
  check('calendar uses available published dates',await evaluate("document.querySelector('.ipo-calendar').textContent.includes('Expected allotment')"));
  await route('research');await wait("!!document.querySelector('.ipo-score')");
  check('research explains support, contradiction and missing information',await evaluate("['Supporting factors','Contradictory factors','Missing information','not a probability'].every(v=>document.querySelector('#ipoContent').textContent.includes(v))"));
  await route('');await wait("!!document.querySelector('#ipoResults table')");
  await click('#ipoResults td:first-child a');await wait("!!document.querySelector('#ipoDetailResource')");
  check('complete IPO details render reported financials and schedule',await evaluate("['Company fundamentals','Revenue','Borrowings','IPO schedule','Objects of the issue','Promoters'].every(v=>document.querySelector('#ipoContent').textContent.includes(v))"));
  await click('[data-ipo-resource=anchors]');await wait("document.querySelector('#ipoDetailResource').textContent.includes('Anchor Fund')");
  check('authorized anchor allocations render on demand',await evaluate("document.querySelector('#ipoDetailResource').textContent.includes('TEST FIXTURE Anchor Fund')"));
  for(const screen of ['', 'gmp','subscription','allotment','listings','compare','calendar','research','alerts']){
    await route(screen);await evaluate('scrollTo(0,document.documentElement.scrollHeight)');await sleep(80);
    check(`sticky clock visible at bottom of IPO ${screen||'overview'}`,await evaluate(sticky));
  }
  check('one clock timer after all IPO navigation',await evaluate('window.clockIntervals===1'));
  check('clock is IST despite Los Angeles browser timezone',await evaluate("(()=>{const time=document.querySelector('#headerClock');return time.textContent===new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(time.dateTime));})()"));
  await shot('ipo-sticky-clock-fixture.png');
  await route('');await wait("!!document.querySelector('#ipoResults table')");
  for(const [width,height]of [[1440,1000],[768,1024],[375,900],[320,900]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(100);
    check(`${width}px IPO overview has no page overflow`,await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    check(`${width}px IPO primary controls remain comfortable`,await evaluate("[...document.querySelectorAll('.ipo-actions button')].every(v=>v.getBoundingClientRect().height>=44)"));
    await evaluate('scrollTo(0,document.documentElement.scrollHeight)');check(`${width}px IPO clock remains visible after scrolling`,await evaluate(sticky));
    if(width===375)await shot('ipo-dashboard-mobile-fixture.png','#ipoTerminal');
    await route('gmp');await wait("!!document.querySelector('.ipo-gmp-chart')");
    check(`${width}px GMP chart scrolls without page overflow`,await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    await route('subscription');await wait("document.querySelectorAll('.ipo-subscription-row').length===6");
    check(`${width}px subscription labels fit and remain readable`,await evaluate('document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll(".ipo-subscription-row")].every(v=>v.scrollWidth<=v.clientWidth)'));
    await route('alerts');await wait("!!document.querySelector('#ipoAlertForm')");
    check(`${width}px alert preferences fit viewport`,await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    await route('');await wait("!!document.querySelector('#ipoResults table')");
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await route('alerts');await wait("!!document.querySelector('#ipoAlertForm')");
  check('IPO alerts are disabled by default',await evaluate("!document.querySelector('#ipoAlertForm input[name=enabled]').checked"));
  await evaluate("document.querySelector('#ipoAlertForm input[name=enabled]').checked=true;document.querySelector('#ipoAlertForm').requestSubmit()");
  check('alert preferences persist without storing provider payloads',await evaluate("JSON.parse(localStorage.getItem('divine-ipo-alerts')).enabled===true&&!Object.keys(localStorage).some(v=>/key|token|pan/.test(v))"));
  stockOutage=true;await send('Page.navigate',{url:base+'/ipo'});await wait("!!document.querySelector('#ipoResults table')");await sleep(300);
  check('IPO works even when stock status endpoint fails',await evaluate("!!document.querySelector('#ipoResults table')&&!document.querySelector('#ipoContent').textContent.includes('Workspace unavailable')"));
  const before=await evaluate("document.querySelector('#headerClock').textContent");await sleep(1200);
  check('clock keeps updating during stock-feed outage',before!==await evaluate("document.querySelector('#headerClock').textContent"));
  check('fixtures are visibly labelled and no JavaScript exceptions occurred',errors.length===0&&await evaluate("document.querySelector('.ipo-test-banner').textContent.includes('NOT LIVE')"));
  check('only Standard IPO API resources were requested',calls.every(v=>!v.includes('intraday')&&!v.includes('subscription/history')&&!v.includes('unlisted')&&!v.includes('/ofs')));
  console.log(JSON.stringify({passed,errors,screenshots}));
  await writeFile('reports/ipo-browser-checks.json',JSON.stringify({passed,checks,errors,screenshots,mode:'Labelled browser fixtures; not live IPO data'},null,2)+'\n');
}finally{ws?.close();chrome.kill();}
