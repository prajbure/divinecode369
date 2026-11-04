// Read-only production verification. Does not log in, scan, or contact providers directly.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {browser,sleep} from './browser_client.mjs';
const base='https://divinecode369.in',checks=[];
const hash=data=>createHash('sha256').update(data).digest('hex');
const sourceCommit=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
// Compare deployment bytes to Git blobs, not a Windows CRLF working copy.
const source=name=>execFileSync('git',['show',sourceCommit+':'+name],{maxBuffer:4*1024*1024});
const check=(label,value)=>{assert.ok(value,label);checks.push(label);console.log('PASS '+label);};
const fetchAsset=async name=>{
  const response=await fetch(base+'/'+name+'?dashboard_verify='+Date.now(),{signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw Error(`${name}: HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
};
const desired=hash(source('static/app.js'));
const attempts=process.argv.includes('--wait')?120:1;
let deployed=false;
for(let i=0;i<attempts;i++){
  try{deployed=hash(await fetchAsset('static/app.js'))===desired;}catch(error){if(i===attempts-1)throw error;}
  if(deployed)break;
  if(i%6===0)console.log('Waiting for Render to serve the tested dashboard source…');
  if(i<attempts-1)await sleep(5000);
}
check('production serves the exact tested application JavaScript',deployed);
for(const name of ['static/scanner-view.js','static/scanner-view.css','static/sector-universe.json'])
  check(name+' matches the tested source',hash(await fetchAsset(name))===hash(source(name)));
const overview=await(await fetch(base+'/api/v1/mobile/overview')).json();
check('shared Android overview endpoint remains available',overview.meta?.api_version==='1'&&Array.isArray(overview.sectors));
const statusResponse=await fetch(base+'/auth/admin/session');
check('administrator session endpoint remains available with no-store',statusResponse.ok&&statusResponse.headers.get('cache-control')==='no-store');
const universe=JSON.parse(await readFile('static/sector-universe.json','utf8'));
const stockCount=new Set(universe.groups.flatMap(g=>g.stocks.map(s=>s[0]))).size;
let chrome;
try{
  chrome=await browser();const{send,evaluate,wait,click,navigate}=chrome;
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await navigate(base+'/');await wait("document.querySelectorAll('[data-scanner-card]').length===7");
  check('production Dashboard retains all 16 sector cards',await evaluate("document.querySelectorAll('.sector-card').length===16"));
  for(const filter of ['all','exact','near','matched','bull','bear','live']){
    const count=await evaluate(`Number(document.querySelector('[data-scanner-card=${filter}] strong').textContent)`);
    await click(`[data-scanner-card=${filter}]`);
    await wait("location.pathname==='/scanner'&&!!document.querySelector('#stockBody')");
    await evaluate("document.querySelector('#pageSize').value='160';document.querySelector('#pageSize').dispatchEvent(new Event('change'))");
    const actual=await evaluate("document.querySelectorAll('#stockBody [data-stock-symbol]').length");
    check(`${filter} production card navigates with the correct URL and record count`,count===actual&&await evaluate(`new URLSearchParams(location.search).get('filter')==='${filter}'`));
    check(`${filter} production category is selected`,await evaluate(`document.querySelector('[data-filter=${filter}]').getAttribute('aria-pressed')==='true'`));
    await send('Page.reload');await wait("!!document.querySelector('#stockBody')");
    check(`${filter} production filter survives refresh`,await evaluate(`document.querySelector('[data-filter=${filter}]').getAttribute('aria-pressed')==='true'`));
    if(filter==='all')check('production total lists unique stocks, not duplicate memberships',actual===stockCount&&await evaluate(`new Set([...document.querySelectorAll('[data-stock-symbol]')].map(n=>n.dataset.stockSymbol)).size===${stockCount}`));
    await click('.scanner-context a[data-route]');await wait("!!document.querySelector('#dashboardStats')");
  }
  await evaluate("document.querySelector('#dashboardStats').scrollIntoView({block:'start'})");
  await chrome.screenshot('.qa/dashboard-production-desktop.png');
  await send('Emulation.setDeviceMetricsOverride',{width:375,height:900,deviceScaleFactor:1,mobile:true});
  check('production mobile dashboard fits the viewport',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  await chrome.screenshot('.qa/dashboard-production-mobile.png');
  await click('[data-scanner-card=matched]');
  check('production mobile scanner retains one sticky IST clock and no page overflow',await evaluate("document.querySelectorAll('#headerClock').length===1&&document.documentElement.scrollWidth<=innerWidth"));
  await navigate(base+'/settings');await wait("!!document.querySelector('#adminLoginForm')");
  check('production Settings still presents administrator login',true);
  await navigate(base+'/ipo');await wait("!!document.querySelector('#premiumIPO')");
  check('production IPO Intelligence still loads independently',true);
  check('no production browser JavaScript exceptions',chrome.errors.length===0);
  const result={url:base,checked_at:new Date().toISOString(),source_commit:sourceCommit,passed:checks.length,checks,application_sha256:desired};
  await writeFile('.qa/dashboard-production-results.json',JSON.stringify(result,null,2));
  console.log(`${checks.length} production dashboard checks passed.`);
}finally{chrome?.close();}
