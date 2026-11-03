import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {browser,sleep} from './browser_client.mjs';
const chrome=await browser(),base='https://localhost:8443',checks=[];
const {send,evaluate,wait,click,navigate}=chrome;
function check(label,value){assert.ok(value,label);checks.push(label);console.log('PASS '+label);}
try{
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await navigate(base+'/ipo');await wait("document.querySelectorAll('[data-ipo-card]').length===2");
  check('four IPO phases and three board filters',await evaluate("document.querySelectorAll('#premiumIPO [data-phase]').length===4&&document.querySelectorAll('[data-board]').length===3"));
  check('compact provider cards expose price, GMP and subscription',await evaluate("[...document.querySelectorAll('[data-ipo-card]')].every(v=>['Issue price','GMP','Subscription'].every(label=>v.textContent.includes(label)))"));
  check('unavailable fields stay unavailable',await evaluate("document.querySelector('[data-ipo-card=fixture-ipo-0] .ipo-card-values').textContent.includes('Unavailable')||document.querySelector('[data-ipo-card=fixture-ipo-0] .ipo-card-values').textContent.includes('—')"));
  check('public IPO page has no scanner or admin token',await evaluate("!document.querySelector('#stockBody')&&!document.body.textContent.includes('ADMIN_TOKEN')"));
  check('anonymous personal mutation denied',await evaluate("fetch('/api/v1/mobile/watchlist',{method:'PUT',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status===401)"));
  await click('[data-phase=upcoming]');await wait("document.querySelectorAll('[data-ipo-card]').length===2&&document.querySelector('[data-phase=upcoming]').getAttribute('aria-selected')==='true'");
  await click('[data-board=SME]');await wait("document.querySelectorAll('[data-ipo-card]').length===1");
  check('upcoming SME filter uses backend classification',await evaluate("document.querySelector('[data-ipo-card]').dataset.ipoCard==='fixture-ipo-3'"));
  await evaluate("{const input=document.querySelector('#premiumSearch');input.value='no such fixture';input.dispatchEvent(new Event('input',{bubbles:true}));}");await wait("document.querySelectorAll('[data-ipo-card]').length===0");
  check('search empty state is explicit',await evaluate("document.querySelector('#premiumCards').textContent.includes('No IPOs')"));
  await evaluate("{const input=document.querySelector('#premiumSearch');input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));}");await wait("document.querySelectorAll('[data-ipo-card]').length===1");
  await click('[data-board=all]');await click('[data-phase=allotted]');await wait("document.querySelectorAll('[data-ipo-card]').length===1&&document.querySelector('[data-ipo-card]').dataset.ipoCard==='fixture-ipo-4'");
  check('allotted phase requires verified stage',true);
  await click('[data-phase=ongoing]');await wait("document.querySelectorAll('[data-ipo-card]').length===2");
  await click('[data-watch=fixture-ipo-1]');await wait("document.querySelector('[data-watch=fixture-ipo-1]').getAttribute('aria-pressed')==='true'");
  check('guest watchlist stores identifiers only',await evaluate("JSON.parse(localStorage.getItem('divine-personal-watchlist-v1')).some(v=>v.key==='fixture-ipo-1'&&v.saved)&&!localStorage.getItem('divine-personal-watchlist-v1').includes('gmp')"));
  await navigate(base+'/settings');await wait("!!document.querySelector('#adminLoginForm')");
  await evaluate("document.querySelector('#adminLoginForm [name=username]').value='owner';document.querySelector('#adminLoginForm [name=password]').value='only-for-tests-password-369';document.querySelector('#adminLoginForm').requestSubmit()");await wait("!!document.querySelector('[data-admin-logout]')");
  await navigate(base+'/watchlists');await wait("document.querySelector('#personalContent').textContent.includes('Aurora')");
  check('website watchlist synchronizes with protected backend',await evaluate("fetch('/api/v1/mobile/watchlist').then(r=>r.json()).then(v=>v.items.some(x=>x.key==='fixture-ipo-1'&&x.saved))"));
  check('cookie mutations still require CSRF',await evaluate("fetch('/api/v1/mobile/watchlist',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'ipo',key:'fixture-ipo-0',label:'Fixture'})}).then(r=>r.status===403)"));
  const device=await evaluate("(async()=>{const verifier='A'.repeat(64),bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))),challenge=btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');const response=await fetch('/auth/mobile/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device_name:'TEST FIXTURE Android',code_challenge:challenge})});return {...await response.json(),verifier};})()");
  await navigate(device.verification_uri);await wait("!!document.querySelector('#approval code')");
  check('browser approval displays the matching native device code',await evaluate("document.querySelector('#approval code').textContent")==device.user_code);
  check('approval clears request parameters from browser history',await evaluate("location.search===''") );
  await click('#approval button');await wait("document.querySelector('#approval button').textContent.includes('Approved')");
  const mobile=await evaluate(`(async()=>{const response=await fetch('/auth/mobile/token',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:${JSON.stringify(device.request_id)},code_verifier:${JSON.stringify(device.verifier)}})});const tokens=await response.json(),headers={Authorization:'Bearer '+tokens.access_token};const personal=await fetch('/api/v1/mobile/watchlist',{credentials:'omit',headers});const provider=await fetch('/api/connections/kite/disconnect',{method:'POST',credentials:'omit',headers});const logout=await fetch('/auth/mobile/logout',{method:'POST',credentials:'omit',headers});const revoked=await fetch('/auth/mobile/session',{credentials:'omit',headers});return {grant:response.status,personal:personal.status,provider:provider.status,logout:logout.status,revoked:revoked.status};})()`);
  check('approved PKCE grant reaches only scoped personal data',mobile.grant===200&&mobile.personal===200&&mobile.provider===401);
  check('mobile logout revokes the browser-tested device session',mobile.logout===200&&mobile.revoked===401);
  await navigate(base+'/ipo/details/fixture-ipo-1');await wait("document.querySelectorAll('[data-view]').length===7");
  check('IPO detail has seven sections',true);
  await click('[data-view=financials]');await wait("[...document.querySelectorAll('#ipoContent>section:not([hidden])')].some(v=>v.textContent.includes('Revenue'))");
  check('verified financial figures are retained',await evaluate("document.querySelector('#ipoContent').textContent.includes('Revenue')&&document.querySelector('#ipoContent').textContent.includes('120')"));
  await click('[data-view=subscription]');await wait("document.querySelectorAll('.ipo-subscription-row').length>=4");
  check('subscription categories and source timestamp render',await evaluate("document.querySelector('#ipoDetailResource').textContent.includes('TOTAL')&&document.querySelector('#ipoDetailResource').textContent.includes('IST')"));
  await click('[data-view=gmp]');await wait("!!document.querySelector('#ipoDetailResource svg')");check('day-wise GMP chart renders provider history',true);
  await click('[data-view=timeline]');check('timeline retains refund and demat dates',await evaluate("[...document.querySelectorAll('#ipoContent>section:not([hidden])')].some(v=>v.textContent.includes('refund')&&v.textContent.includes('demat'))"));
  await evaluate("document.querySelector('#detailAlertForm').closest('details').open=true;document.querySelector('#detailAlertForm [name=event]').value='closes_tomorrow';document.querySelector('#detailAlertForm').requestSubmit()");await wait("document.querySelector('#toast').textContent.includes('Alert saved')");
  check('owner alert rule saved with CSRF',await evaluate("fetch('/api/v1/mobile/alerts').then(r=>r.json()).then(v=>v.items.some(x=>x.event==='closes_tomorrow'))"));
  for(const width of [320,375,768,1440]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});await navigate(base+'/ipo');await wait("document.querySelectorAll('[data-ipo-card]').length===2");await sleep(150);
    check(`${width}px page and cards fit viewport`,await evaluate("document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('[data-ipo-card]')].every(v=>v.scrollWidth<=v.clientWidth)"));
    if(width<=375){check(`${width}px five-item bottom navigation visible`,await evaluate("getComputedStyle(document.querySelector('.mobile-bottom-nav')).display==='flex'&&document.querySelectorAll('.mobile-bottom-nav>a,.mobile-bottom-nav>button').length===5"));await click('#mobileMore');check(`${width}px More retains navigation links`,await evaluate("document.querySelector('#navigation').classList.contains('open')&&!!document.querySelector('#navigation a[href=\"/history\"]')"));await click('#mobileMore');}
    if(width===375)await chrome.screenshot('reports/platform-ipo-phone-fixture.png');if(width===1440)await chrome.screenshot('reports/platform-ipo-desktop-fixture.png');
  }
  await navigate(base+'/');await wait("document.querySelectorAll('.sector-card').length===16");
  check('website retains all 16 sector cards',true);
  check('concise hero replaces promotional panels',await evaluate("document.querySelector('.compact-market-hero').getBoundingClientRect().height<170&&!document.querySelector('.hero-visual')"));
  const before=await evaluate("document.querySelector('#headerClock').textContent");await sleep(1200);check('IST clock still updates',before!==await evaluate("document.querySelector('#headerClock').textContent"));
  check('no browser exceptions',chrome.errors.length===0);
  await writeFile('reports/PLATFORM_BROWSER.json',JSON.stringify({passed:checks.length,checks,errors:chrome.errors,mode:'Real Chrome over local HTTPS; synthetic provider fixtures; no live provider validation'},null,2)+'\n');
  console.log(`${checks.length} platform browser checks passed.`);
}catch(error){console.error('Browser diagnostics',JSON.stringify(chrome.errors));throw error;}finally{chrome.close();}
