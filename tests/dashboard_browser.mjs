// Real Chromium + isolated HTTPS FastAPI. Synthetic values never reach production.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import https from 'node:https';
import {readFile,writeFile} from 'node:fs/promises';
import {browser,sleep} from './browser_client.mjs';

const base=process.env.DIVINE_TEST_URL||'https://localhost:8443';
const checks=[];
let fixture,chrome,fixtureOutput='';
const check=(label,value)=>{assert.ok(value,label);checks.push(label);console.log('PASS '+label);};
const ready=()=>new Promise(resolve=>{const request=https.get(base+'/api/quotes',{rejectUnauthorized:false},response=>{response.resume();resolve(response.statusCode===200);});request.on('error',()=>resolve(false));request.setTimeout(1000,()=>request.destroy());});
try {
  if(!process.env.DIVINE_TEST_URL){
    const python=process.env.PYTHON_EXECUTABLE||(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
    fixture=spawn(python,['-m','tests.dashboard_fixture'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    fixture.on('error',error=>{fixtureOutput+=error.message;});
    for(const stream of [fixture.stdout,fixture.stderr])stream.on('data',data=>{fixtureOutput+=data;});
    for(let i=0;i<150&&!await ready();i++){if(fixture.exitCode!==null)throw Error(fixtureOutput);await sleep(200);}
    assert.ok(await ready(),'Dashboard fixture must start: '+fixtureOutput);
  }
  chrome=await browser();
  const {send,evaluate,wait,click,navigate}=chrome;
  const groups=JSON.parse(await readFile(new URL('../static/sector-universe.json',import.meta.url),'utf8')).groups;
  const total=new Set(groups.flatMap(g=>g.stocks.map(s=>s[0]))).size;
  const displayed=()=>evaluate("[...document.querySelectorAll('#stockBody [data-stock-symbol]')].map(r=>r.dataset.stockSymbol)");
  const allRows=()=>evaluate("document.querySelector('#pageSize').value='160';document.querySelector('#pageSize').dispatchEvent(new Event('change'));true");
  const back=async()=>{await click('.scanner-context a[data-route]');await wait("location.pathname==='/'&&document.querySelectorAll('[data-scanner-card]').length===7");};
  const load=async path=>{await navigate(base+path);await wait("!!document.querySelector('#stockBody')");};
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await load('/');
  const raw=await evaluate("fetch('/api/quotes').then(r=>r.json()).then(s=>s.rows)");
  const expected={all:total,exact:raw.filter(r=>r.match).length,near:raw.filter(r=>r.near_match).length,
    matched:raw.filter(r=>r.match||r.near_match).length,bull:raw.filter(r=>r.change_pct>0).length,
    bear:raw.filter(r=>r.change_pct<0).length,live:raw.filter(r=>r.quote_status==='live').length};
  const initialRequests=await evaluate("performance.getEntriesByType('resource').filter(r=>/\\/api\\/(status|quotes)$/.test(new URL(r.name).pathname)).length");
  check('seven accessible dashboard card links',await evaluate("[...document.querySelectorAll('[data-scanner-card]')].every(a=>a.tagName==='A'&&a.getAttribute('aria-label')&&a.getBoundingClientRect().height>=44)"));
  for(const [filter,count] of Object.entries(expected)){
    const shown=await evaluate(`Number(document.querySelector('[data-scanner-card="${filter}"] strong').textContent)`);
    check(`${filter} card count equals unique backend records`,shown===count);
    await click(`[data-scanner-card="${filter}"]`);
    await wait(`location.pathname==='/scanner'&&new URLSearchParams(location.search).get('filter')==='${filter}'`);
    await allRows();
    const symbols=await displayed();
    check(`${filter} card opens exactly its counted records`,symbols.length===count&&new Set(symbols).size===count);
    if(filter!=='all'){
      const expectedSymbols=raw.filter(r=>filter==='matched'?r.match||r.near_match:filter==='exact'?r.match:filter==='near'?r.near_match:filter==='bull'?r.change_pct>0:filter==='bear'?r.change_pct<0:r.quote_status==='live').map(r=>r.symbol).sort();
      check(`${filter} results contain only the intended backend classification`,JSON.stringify([...symbols].sort())===JSON.stringify(expectedSymbols));
    }
    check(`${filter} heading and selected state are clear`,await evaluate(`document.querySelector('#scannerCategory').textContent===document.querySelector('#scannerPageTitle').textContent&&document.querySelector('[data-filter="${filter}"]').getAttribute('aria-pressed')==='true'&&document.querySelector('#categoryCount').textContent.startsWith('${count} unique stocks')`));
    await send('Page.reload');await wait("!!document.querySelector('#stockBody')");
    check(`${filter} survives a page refresh`,(await displayed()).length===count&&await evaluate(`document.querySelector('[data-filter="${filter}"]').getAttribute('aria-pressed')==='true'`));
    await back();
  }
  // Card transitions themselves use the current snapshot rather than loading it again.
  await click('[data-scanner-card="exact"]');await back();
  const beforeNav=await evaluate("performance.getEntriesByType('resource').filter(r=>/\\/api\\/(status|quotes)$/.test(new URL(r.name).pathname)).length");
  await click('[data-scanner-card="near"]');await back();
  check('card navigation does not issue extra quote/status requests',beforeNav===await evaluate("performance.getEntriesByType('resource').filter(r=>/\\/api\\/(status|quotes)$/.test(new URL(r.name).pathname)).length"));
  check('existing quote/status data flow remains bounded',initialRequests<=3);
  await click('[data-scanner-card="matched"]');
  await evaluate('history.back()');await wait("location.pathname==='/'");
  check('browser Back returns to Dashboard',await evaluate("!!document.querySelector('#dashboardStats')"));
  await evaluate('history.forward()');await wait("location.pathname==='/scanner'");
  check('browser Forward restores the category',await evaluate("document.querySelector('[data-filter=matched]').getAttribute('aria-pressed')==='true'"));
  await click('[data-filter=exact]');await click('[data-filter=near]');await evaluate('history.back()');
  await wait("document.querySelector('[data-filter=exact]').getAttribute('aria-pressed')==='true'");
  check('Back restores category changes within the scanner',true);

  await load('/scanner?filter=all');
  check('professional table includes sector, opening percentage and volume',await evaluate("['Sector','Difference %','Volume'].every(label=>[...document.querySelectorAll('.scanner-panel th')].some(th=>th.textContent.includes(label)))"));
  await evaluate(`document.querySelector('#sectorFilter').value=${JSON.stringify(groups[0].id)};document.querySelector('#sectorFilter').dispatchEvent(new Event('change'))`);
  await allRows();
  const sectorSymbols=[...new Set(groups[0].stocks.map(s=>'NSE:'+s[0]))].sort();
  check('sector filter lists unique sector members only',JSON.stringify((await displayed()).sort())===JSON.stringify(sectorSymbols));
  const search=groups[0].stocks[0][0];
  await evaluate(`document.querySelector('#stockSearch').value=${JSON.stringify(search)};document.querySelector('#stockSearch').dispatchEvent(new Event('input'))`);
  check('symbol search filters the list',JSON.stringify(await displayed())===JSON.stringify(['NSE:'+search]));
  await click('[data-sort=volume]');
  const selectedUrl=await evaluate('location.search');
  await send('Page.reload');await wait("!!document.querySelector('#stockBody')");
  check('search, sector, sorting and page size survive refresh',await evaluate(`location.search===${JSON.stringify(selectedUrl)}&&document.querySelector('#stockSearch').value===${JSON.stringify(search)}&&document.querySelector('#sectorFilter').value===${JSON.stringify(groups[0].id)}&&document.querySelector('th[data-column=volume]').getAttribute('aria-sort')==='ascending'&&document.querySelector('#pageSize').value==='160'`));
  await click('#stockBody a[data-route]');await wait("location.pathname.startsWith('/stocks/')");
  check('stock opens its existing detail view',await evaluate("!!document.querySelector('#stockPrice')"));
  await evaluate('history.back()');await wait("location.pathname==='/scanner'");
  check('return from stock details restores scanner filters',await evaluate(`location.search===${JSON.stringify(selectedUrl)}`));
  await click('[data-action=reset]');
  check('clear filters resets category, search and sector in the URL',await evaluate("document.querySelector('#stockSearch').value===''&&document.querySelector('#sectorFilter').value===''&&location.search==='?filter=all&size=160'"));
  await evaluate("document.querySelector('#stockSearch').value='no-such-fixture-stock';document.querySelector('#stockSearch').dispatchEvent(new Event('input'))");
  check('empty state contains no fabricated rows',await evaluate("document.querySelector('#stockBody .empty').textContent.includes('No stocks match')&&document.querySelectorAll('[data-stock-symbol]').length===0"));

  await load('/scanner?filter=exact&size=160');
  const beforeLive=await displayed();
  await evaluate("fetch('/_test/dashboard/updated',{method:'POST'}).then(r=>r.json())");
  await wait(`document.querySelectorAll('[data-stock-symbol]').length===${beforeLive.length-1}`);
  check('real SSE update refreshes filtered rows without resetting the URL',await evaluate("new URLSearchParams(location.search).get('filter')==='exact'&&document.querySelector('[data-filter=exact]').getAttribute('aria-pressed')==='true'"));
  await back();
  check('same SSE snapshot updates dashboard count',await evaluate(`Number(document.querySelector('[data-scanner-card=exact] strong').textContent)===${beforeLive.length-1}`));
  await evaluate("document.querySelector('[data-scanner-card=exact]').focus();window.focusedCard=document.activeElement;fetch('/_test/dashboard/initial',{method:'POST'}).then(r=>r.json())");
  await wait(`Number(document.querySelector('[data-scanner-card=exact] strong').textContent)===${beforeLive.length}`);
  check('live counts preserve the focused card element',await evaluate('document.activeElement===window.focusedCard'));
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await wait("location.pathname==='/scanner'&&new URLSearchParams(location.search).get('filter')==='exact'");
  check('keyboard Enter activates the focused summary card',true);
  check('exact matches are highlighted cyan',await evaluate("getComputedStyle(document.querySelector('#stockBody .match-badge.exact')).color==='rgb(0, 216, 255)'"));
  await back();
  for(const width of [1440,768,375,320]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
    check(`${width}px dashboard cards remain within the viewport`,await evaluate("document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('[data-scanner-card]')].every(n=>n.getBoundingClientRect().width>=100)"));
    if(width===1440||width===375){await evaluate("document.querySelector('#dashboardStats').scrollIntoView({block:'start'})");await chrome.screenshot(`.qa/dashboard-cards-${width}.png`);}
    await click('[data-scanner-card=all]');
    check(`${width}px scanner is horizontally scrollable without page overflow`,await evaluate("document.documentElement.scrollWidth<=innerWidth&&document.querySelector('.scanner-panel .table-wrap').scrollWidth>document.querySelector('.scanner-panel .table-wrap').clientWidth&&document.querySelectorAll('#headerClock').length===1"));
    if(width===1440||width===375){await evaluate("document.querySelector('.scanner-panel').scrollIntoView({block:'start'})");await chrome.screenshot(`.qa/dashboard-scanner-${width}.png`);}
    await back();
  }
  await evaluate("fetch('/_test/dashboard/pagination',{method:'POST'}).then(r=>r.json())");
  await load('/scanner?filter=bull&size=10&page=2');
  check('pagination begins on the requested second page',await evaluate("document.querySelector('#pageLabel').textContent==='2 / 2'&&document.querySelectorAll('[data-stock-symbol]').length===1"));
  await evaluate("fetch('/_test/dashboard/pagination-shrink',{method:'POST'}).then(r=>r.json())");
  await wait("document.querySelector('#pageLabel').textContent==='1 / 1'");
  check('SSE shrinking results synchronizes the clamped page to the URL',await evaluate("!new URLSearchParams(location.search).has('page')&&new URLSearchParams(location.search).get('filter')==='bull'"));
  await evaluate("fetch('/_test/dashboard/pagination',{method:'POST'}).then(r=>r.json())");
  await wait("document.querySelector('#pageLabel').textContent==='1 / 2'");
  await send('Page.reload');await wait("!!document.querySelector('#stockBody')");
  check('refresh after a shrink and expansion keeps the displayed page',await evaluate("document.querySelector('#pageLabel').textContent==='1 / 2'&&document.querySelectorAll('[data-stock-symbol]').length===10"));
  await back();
  await evaluate("fetch('/_test/dashboard/empty',{method:'POST'}).then(r=>r.json())");
  await wait("document.querySelector('[data-scanner-card=exact] strong').textContent==='0'");
  check('missing provider data keeps tracked total and zero classified matches',await evaluate(`document.querySelector('[data-scanner-card=all] strong').textContent==='${total}'&&document.querySelector('[data-scanner-card=matched] strong').textContent==='0'`));
  await click('[data-scanner-card=exact]');
  check('unavailable provider data has an honest empty state',await evaluate("document.querySelector('#stockBody .empty').textContent.includes('No verified classifications')"));
  await click('[data-filter=all]');await allRows();
  check('unavailable stocks remain visible without sample prices',await evaluate(`document.querySelectorAll('[data-stock-symbol]').length===${total}&&[...document.querySelectorAll('#stockBody .quote-label')].every(n=>n.textContent.includes('unavailable'))`));
  check('no JavaScript exceptions in dashboard journeys',chrome.errors.length===0);
  await writeFile('.qa/dashboard-browser-results.json',JSON.stringify({passed:checks.length,checks},null,2));
  console.log(`${checks.length} dashboard browser checks passed.`);
} finally {chrome?.close();fixture?.kill();}
