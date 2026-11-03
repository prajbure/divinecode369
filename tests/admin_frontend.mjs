import assert from 'node:assert/strict';
import {adminRequest} from '../static/admin-auth.js';

let calls = [];
let authenticated = true;
let failure = false;
globalThis.fetch = async (path, options) => {
  calls.push({path, options});
  if (path === '/auth/admin/session') return Response.json({authenticated, csrf_token:'session-csrf-proof'});
  if (failure) return Response.json({detail:'Session expired.'}, {status:401});
  return Response.json({ok:true});
};
let passed = 0;
const check = (message, fn) => { fn(); passed++; console.log('PASS ' + message); };

await adminRequest('/api/quotes');
check('public read does not require an admin session', () => assert.equal(calls.length, 1));
check('requests use same-origin cookies', () => assert.equal(calls[0].options.credentials, 'same-origin'));
await adminRequest('/api/connections/kite/recheck', {method:'POST'});
check('mutation refreshes server session before submission', () => assert.equal(calls.at(-2).path, '/auth/admin/session'));
check('mutation carries the current CSRF proof', () => assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), 'session-csrf-proof'));
check('browser never sends a backend bearer token', () => assert.equal(calls.at(-1).options.headers.has('Authorization'), false));
check('mutation prevents unexpected redirects', () => assert.equal(calls.at(-1).options.redirect, 'error'));

authenticated = false;
calls = [];
await assert.rejects(adminRequest('/api/connections/kite/disconnect', {method:'POST'}), /Sign in/);
check('expired or logged-out session prevents action submission', () => assert.equal(calls.length, 1));
check('logged-out browser only checks the session', () => assert.equal(calls[0].path, '/auth/admin/session'));
await adminRequest('/auth/admin/login', {method:'POST', body:JSON.stringify({username:'test', password:'synthetic'})});
check('login is permitted with an anonymous CSRF session', () => assert.equal(calls.at(-1).path, '/auth/admin/login'));
check('login uses JSON rather than URL credentials', () => assert.equal(calls.at(-1).options.headers.get('Content-Type'), 'application/json'));

await assert.rejects(adminRequest('https://evil.example/api', {method:'POST'}), /same-origin/);
await assert.rejects(adminRequest('//evil.example/api', {method:'POST'}), /same-origin/);
check('absolute and protocol-relative destinations are rejected', () => assert.ok(true));
authenticated = true;
failure = true;
try { await adminRequest('/api/scan', {method:'POST'}); assert.fail('Expected unauthorized error'); }
catch (error) {
  check('unauthorized response offers the Settings login', () => assert.equal(error.action.href, '/settings'));
}
console.log(`${passed} admin frontend checks passed.`);
