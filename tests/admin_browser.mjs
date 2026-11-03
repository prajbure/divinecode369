// Actual Chromium form, cookie and CSRF checks against tests.admin_fixture over HTTPS.
import {spawn} from 'node:child_process';
import {mkdir,mkdtemp} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
await mkdir('.qa', {recursive:true});
const profile = await mkdtemp(path.resolve('.qa/admin-chrome-'));
const chrome = spawn(process.env.CHROME_EXECUTABLE || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  ['--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--ignore-certificate-errors','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
  {windowsHide:true, stdio:['ignore','ignore','pipe']});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws;
let passed = 0;
try {
  const endpoint = await new Promise((resolve, reject) => {
    let stderr = '';
    const timer = setTimeout(() => reject(Error('Chrome startup timeout')), 15000);
    chrome.stderr.on('data', chunk => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    chrome.on('error', reject);
  });
  const target = await (await fetch(`http://127.0.0.1:${new URL(endpoint).port}/json/new?about:blank`, {method:'PUT'})).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let serial = 0;
  const pending = new Map();
  const errors = [];
  const send = (method, params={}) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: '+method)); }, 15000);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params}));
  });
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const task = pending.get(message.id);
      clearTimeout(task.timer); pending.delete(message.id);
      message.error ? task.reject(Error(message.error.message)) : task.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  };
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
    if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
    return result.result.value;
  };
  const wait = async expression => {
    for (let attempt=0; attempt<100; attempt++) {
      if (await evaluate(expression)) return;
      await sleep(100);
    }
    throw Error('DOM wait timed out: '+expression);
  };
  const check = (label, condition) => { assert.ok(condition, label); passed++; console.log('PASS '+label); };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate', {url:'https://localhost:8443/settings'});
  await wait("!!document.querySelector('#adminLoginForm')");
  check('Settings renders the administrator login form', true);
  check('backend token field is absent', await evaluate("!document.querySelector('#adminToken')&&!document.body.textContent.includes('ADMIN_TOKEN')"));
  check('anonymous mutation is rejected by the server', await evaluate("fetch('/api/scan',{method:'POST'}).then(r=>r.status===401)"));
  await evaluate("document.querySelector('#adminLoginForm [name=username]').value='owner';document.querySelector('#adminLoginForm [name=password]').value='wrong';document.querySelector('#adminLoginForm').requestSubmit();");
  await wait("document.querySelector('#toast').textContent.includes('Invalid administrator credentials')");
  check('incorrect password displays the generic login error', true);
  check('submitted password input is cleared', await evaluate("document.querySelector('#adminLoginForm [name=password]').value===''") );
  await evaluate("document.querySelector('#adminLoginForm [name=password]').value='only-for-tests-password-369';document.querySelector('#adminLoginForm').requestSubmit();");
  await wait("!!document.querySelector('[data-admin-logout]')");
  check('valid credentials establish the browser session', true);
  const cookies = (await send('Network.getCookies')).cookies;
  const cookie = cookies.find(value => value.name === '__Host-divine_admin');
  check('browser session cookie is Secure, HttpOnly and SameSite=Lax', cookie?.secure && cookie.httpOnly && cookie.sameSite === 'Lax');
  check('JavaScript cannot read the admin session cookie', await evaluate("!document.cookie.includes('__Host-divine_admin')"));
  check('authenticated request without CSRF is rejected', await evaluate("fetch('/api/scan',{method:'POST'}).then(r=>r.status===403)"));
  check('shared frontend request sends working cookie and CSRF proof', await evaluate("import('/static/admin-auth.js').then(m=>m.adminRequest('/api/scan',{method:'POST'})).then(r=>Array.isArray(r.rows))"));
  check('provider recheck works through the same protected request flow', await evaluate("import('/static/admin-auth.js').then(m=>m.adminRequest('/api/connections/kite/recheck',{method:'POST'})).then(r=>!!r.kite)"));
  await send('Page.reload');
  await wait("!!document.querySelector('[data-admin-logout]')");
  check('reload retains the administrator session', true);
  await evaluate("document.querySelector('[data-admin-logout]').click()");
  await wait("!!document.querySelector('#adminLoginForm')");
  check('logout restores the login form', true);
  check('logout removes server access', await evaluate("fetch('/api/scan',{method:'POST'}).then(r=>r.status===401)"));
  await send('Page.navigate', {url:'https://localhost:8443/'});
  await wait("document.querySelectorAll('.sector-card').length===16");
  check('public dashboard retains all sixteen sectors', true);
  await send('Page.navigate', {url:'https://localhost:8443/ipo'});
  await wait("document.querySelector('h1')?.textContent.includes('IPO')");
  check('public IPO page opens without an admin session', true);
  check('no uncaught JavaScript exceptions', errors.length === 0);
  console.log(`${passed} HTTPS browser checks passed.`);
} finally {
  ws?.close();
  chrome.kill();
}
