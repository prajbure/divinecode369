// V2.1 navigation/health checks against the real local app. No live credentials.
import {spawn} from 'node:child_process';
import {mkdir,mkdtemp,writeFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const base=process.env.DIVINE_TEST_URL||'http://127.0.0.1:8000',qa=path.resolve('.qa');await mkdir(qa,{recursive:true});
const profile=await mkdtemp(path.join(qa,'v21-chrome-'));
const chrome=spawn(process.env.CHROME_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,passed=0;const checks=[],screenshots=[];
try{
  const endpoint=await new Promise((resolve,reject)=>{let stderr='';const timer=setTimeout(()=>reject(Error('Chrome startup timeout')),15000);chrome.stderr.on('data',chunk=>{stderr+=chunk;const match=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});chrome.on('error',reject);});
  const target=await(await fetch(`http://127.0.0.1:${new URL(endpoint).port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let serial=0;const pending=new Map(),errors=[];
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id){const task=pending.get(msg.id);if(task){clearTimeout(task.timer);pending.delete(msg.id);msg.error?task.reject(Error(JSON.stringify(msg.error))):task.resolve(msg.result);}}else if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);};
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const wait=async expression=>{for(let i=0;i<120;i++){if(await evaluate(expression))return;await sleep(100);}throw Error('DOM wait: '+expression);};
  const check=(label,condition)=>{assert.ok(condition,label);passed++;checks.push(label);console.log('PASS '+label);};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const navigate=async route=>{await evaluate(`document.querySelector('a[data-route][href="${route}"]').click()`);await wait(`location.pathname===${JSON.stringify(route)}`);await sleep(100);};
  const clockVisible="(()=>{const r=document.querySelector('#headerClock').getBoundingClientRect();return r.top>=0&&r.bottom<innerHeight&&document.querySelectorAll('#headerClock').length===1;})()";
  async function shot(name){await evaluate("document.getElementById('toast').hidden=true");const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('reports/'+name,Buffer.from(image.data,'base64'));screenshots.push('reports/'+name);}
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"window.clockIntervals=0;const originalInterval=window.setInterval;window.setInterval=function(fn,delay,...args){if(delay===1000)window.clockIntervals++;return originalInterval(fn,delay,...args);};"});
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base+'/'});await wait("document.querySelectorAll('.sector-card').length===16");await evaluate('document.fonts.ready.then(()=>true)');
  check('single global header with two organized levels',await evaluate("document.querySelectorAll('header.topbar').length===1&&document.querySelector('.header-primary').getBoundingClientRect().bottom<=document.querySelector('#navigation').getBoundingClientRect().top+1"));
  check('original six primary destinations in exact order',await evaluate("JSON.stringify([...document.querySelectorAll('#navigation>a')].map(a=>a.pathname))===JSON.stringify(['/','/sectors','/scanner','/live-market','/ai-predictions','/ipo'])"));
  check('secondary destinations remain accessible in More',await evaluate("['/history','/settings','/connections','/health'].every(path=>!!document.querySelector('#navMore a[href=\"'+path+'\"]'))"));
  check('duplicate clock and INDIA MARKET TIME strip removed',await evaluate("!document.querySelector('.market-clock-strip')&&!document.querySelector('#liveClock')&&!document.querySelector('#liveDate')&&!document.body.textContent.includes('INDIA MARKET TIME')"));
  check('clock is adjacent to original logo and quiet for screen readers',await evaluate("!!document.querySelector('.header-primary .brand + .header-clock')&&document.querySelector('.header-clock').getAttribute('aria-live')==='off'"));
  await shot('v21-dashboard-desktop.png');
  await click('#navMore>summary');
  check('More opens readable secondary links',await evaluate("document.querySelector('#navMore').open&&document.querySelector('#navMore a').getBoundingClientRect().height>=44"));
  await evaluate("document.querySelector('#navMore a').focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");
  check('Escape closes More and restores keyboard focus',await evaluate("!document.querySelector('#navMore').open&&document.activeElement===document.querySelector('#navMore>summary')"));
  await click('#providerMenu>summary');await wait("document.querySelector('#connectionDropdown').textContent.includes('IPO Guru')");
  check('compact connection dropdown shows both backend providers',await evaluate("document.querySelector('#providerMenu').open&&document.querySelectorAll('#connectionDropdown .provider-card').length===2"));
  check('closed NSE session is distinct from connection status',await evaluate("document.querySelector('#navMarketStatus').textContent.includes('NSE')&&document.querySelector('#connectionDropdown').textContent.includes('Authentication')"));
  await shot('v21-connection-dropdown.png');await click('#providerMenu>summary');
  await navigate('/connections');await wait("document.querySelectorAll('#connectionDetailsPage>.panel').length===2");
  check('Connection Manager includes auth, network, freshness and safe actions',await evaluate("(()=>{const text=document.querySelector('#connectionDetailsPage').textContent;return ['Authentication','Network','Last local data update','Data freshness','Recheck configured provider'].every(v=>text.includes(v))&&(text.includes('Official Kite login')||text.includes('Recheck session'));})()"));
  const publicHealth=await evaluate("fetch('/api/connections/status').then(r=>r.json())");
  check('health response exposes no credential fields',!/(?:access_token|api_secret|request_token|IPOGURU_API_KEY)/i.test(JSON.stringify(publicHealth)));
  await shot('v21-connection-manager.png');
  const states=await evaluate("(async()=>{const m=await import('/static/connections.js'),actual=await fetch('/api/connections/status').then(r=>r.json()),results=[];for(const state of ['connected','login_required','api_key_missing','expired','rate_limited','disconnected','degraded','error']){const sample=structuredClone(actual);sample.kite.state=state;m.receiveConnections(sample);results.push(document.querySelector('#connectionDetailsPage .provider-state').dataset.state===state);}m.receiveConnections(actual);return results;})()");
  check('all eight connection states render honestly from backend input',states.every(Boolean));
  check('provider generation updates reload IPO once per change',await evaluate("(async()=>{const m=await import('/static/connections.js'),actual=await fetch('/api/connections/status').then(r=>r.json());m.receiveConnections(actual);let calls=0;const value={...actual,ipo_generation:999};m.receiveConnections(value,()=>calls++);m.receiveConnections(value,()=>calls++);m.receiveConnections(actual);return calls===1;})()"));
  await navigate('/health');await wait("!!document.querySelector('#connectionDetailsPage dl')");
  check('detailed data health includes tick subscriptions cache and source timestamps',await evaluate("['Last received tick','Active subscriptions','GMP source timestamp','Subscription source timestamp','Cache'].every(v=>document.querySelector('#connectionDetailsPage').textContent.includes(v))"));
  await shot('v21-data-health.png');
  for(const route of ['/sectors','/scanner','/live-market','/ai-predictions','/ipo','/history','/settings','/connections','/health']){
    await navigate(route);await evaluate('scrollTo(0,document.documentElement.scrollHeight)');
    check(`one visible sticky clock on ${route}`,await evaluate(clockVisible));
  }
  await navigate('/ipo');await wait("!!document.querySelector('.ipo-terminal')");
  check('IPO workspace hides the stock marquee and has no provider Connect button',await evaluate("getComputedStyle(document.querySelector('.ticker')).display==='none'&&!document.querySelector('#ipoVerify')"));
  await shot('v21-ipo-unconfigured.png');
  await navigate('/');await wait("document.querySelectorAll('.sector-card').length===16");
  const sectors=await evaluate("[...document.querySelectorAll('.sector-card')].map(a=>a.pathname)");
  for(const route of sectors){await evaluate(`document.querySelector('a[href="${route}"]').click()`);await wait("!!document.querySelector('#stockBody')");await evaluate('scrollTo(0,document.documentElement.scrollHeight)');check(`persistent single clock on ${route}`,await evaluate(clockVisible));await navigate('/');}
  await navigate('/sectors/banking');
  await evaluate("document.querySelector('#sectorIntelligence').closest('details').open=true;document.querySelector('#sectorIntelligence').scrollIntoView({block:'start'})");
  check('sector panel includes dispersion and volume participation',await evaluate("document.querySelector('#sectorIntelligence').textContent.includes('Dispersion')&&document.querySelector('#sectorIntelligence').textContent.includes('Constituents with traded volume')"));
  await shot('v21-sector-intelligence.png');
  await evaluate('scrollTo(0,document.documentElement.scrollHeight)');await shot('v21-sticky-clock.png');
  await send('Emulation.setTimezoneOverride',{timezoneId:'America/Los_Angeles'});await sleep(1100);
  check('IST clock stays correct in Los Angeles browser timezone',await evaluate("(()=>{const e=document.querySelector('#headerClock');return e.textContent===new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(e.dateTime));})()"));
  for(const width of [1920,1440,1100,980,900,768,700,650,375,320]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});await navigate('/');await evaluate('scrollTo(0,0)');await sleep(100);
    check(`${width}px header fits without overlapping clock or logo`,await evaluate("(()=>{const brand=document.querySelector('.brand'),clock=document.querySelector('.header-clock'),strong=brand.querySelector('strong').getBoundingClientRect(),time=clock.getBoundingClientRect(),status=document.querySelector('.header-status').getBoundingClientRect();return document.documentElement.scrollWidth<=innerWidth&&strong.right<=time.left+1&&time.right<=status.left+1;})()"));
    if(width<=900){await click('#menuToggle');check(`${width}px compact menu is keyboard-accessible and expanded`,await evaluate("document.querySelector('#navigation').classList.contains('open')&&document.querySelector('#menuToggle').getAttribute('aria-expanded')==='true'&&[...document.querySelectorAll('#navigation>a')].every(a=>a.getBoundingClientRect().height>=44)"));if(width===375){await click('#navMore>summary');await shot('v21-navigation-mobile.png');}await evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");}
    await click('#providerMenu>summary');await sleep(100);
    check(`${width}px provider dropdown fits viewport`,await evaluate("(()=>{const r=document.querySelector('.provider-popover').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=document.querySelector('.topbar').getBoundingClientRect().bottom-1&&r.bottom<=innerHeight+1;})()"));
    await click('#providerMenu>summary');
    if(width===375)await shot('v21-dashboard-mobile.png');
  }
  check('route navigation creates no duplicate clock intervals',await evaluate('window.clockIntervals===1'));
  check('all navigation and health checks produced no JavaScript exceptions',errors.length===0);
  await writeFile('reports/v21-browser-checks.json',JSON.stringify({passed,checks,errors,screenshots,mode:'Local app with no live provider credentials; simulated states are isolated and not used in screenshots'},null,2)+'\n');
  console.log(JSON.stringify({passed,errors,screenshots}));
}finally{ws?.close();chrome.kill();}
