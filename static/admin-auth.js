// Only a CSRF proof is available to JavaScript. The session is an HttpOnly cookie.
let session = null;
let pendingSession = null;
let notify = () => {};

async function decode(response) {
  let body;
  try { body = await response.json(); } catch { throw new Error('The server returned an invalid response.'); }
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : 'The request failed.');
    if (response.status === 401) {
      session = null;
      error.action = {href:'/settings', label:'Administrator sign in'};
    }
    throw error;
  }
  return body;
}

export async function refreshAdminSession() {
  if (!pendingSession) {
    pendingSession = fetch('/auth/admin/session', {credentials:'same-origin', cache:'no-store', redirect:'error'})
      .then(decode).then(value => (session = value)).finally(() => { pendingSession = null; });
  }
  return pendingSession;
}

export async function adminRequest(path, options = {}) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('A same-origin API path is required.');
  const headers = new Headers(options.headers);
  const method = (options.method || 'GET').toUpperCase();
  if (!['GET','HEAD','OPTIONS'].includes(method)) {
    const current = await refreshAdminSession();
    if (!current.authenticated && path !== '/auth/admin/login') {
      const error = new Error('Sign in as an administrator in Settings to continue.');
      error.action = {href:'/settings', label:'Administrator sign in'};
      throw error;
    }
    headers.set('X-CSRF-Token', current.csrf_token);
  }
  if (options.body) headers.set('Content-Type', 'application/json');
  return decode(await fetch(path, {...options, method, headers, credentials:'same-origin', cache:'no-store', redirect:'error'}));
}

function paintSession() {
  const node = document.getElementById('adminSession');
  if (!node) return;
  if (session?.authenticated) {
    node.innerHTML = '<p>You are signed in as an administrator. This session expires automatically.</p><button type="button" class="secondary" data-admin-logout>Sign out</button>';
  } else {
    node.innerHTML = '<p>Sign in to manage provider connections and administrative actions.</p><form id="adminLoginForm"><label>Username<input name="username" autocomplete="username" required maxlength="256"></label><label>Password<input name="password" type="password" autocomplete="current-password" required maxlength="1024"></label><button type="submit" class="secondary">Sign in</button></form>';
  }
}

export async function mountAdminSession() {
  try { await refreshAdminSession(); paintSession(); }
  catch (error) {
    const node = document.getElementById('adminSession');
    if (node) node.textContent = error.message;
  }
}

export function initializeAdminSession(notice) {
  notify = notice;
  document.addEventListener('submit', async event => {
    if (event.target.id !== 'adminLoginForm') return;
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const body = JSON.stringify({username:form.elements.username.value, password:form.elements.password.value});
      form.elements.password.value = '';
      session = await adminRequest('/auth/admin/login', {method:'POST', body});
      paintSession();
      notify('Administrator signed in.');
    } catch (error) { notify(error.message, true, error.action); }
    finally { button.disabled = false; }
  });
  document.addEventListener('click', async event => {
    const logout = event.target.closest('[data-admin-logout]');
    const kite = event.target.closest('a[href="/auth/kite/login"]');
    if (!logout && !kite) return;
    event.preventDefault();
    const control = logout || kite;
    if (control.dataset.busy) return;
    control.dataset.busy = 'true';
    try {
      if (logout) {
        await adminRequest('/auth/admin/logout', {method:'POST'});
        session = null;
        await mountAdminSession();
        notify('Administrator signed out.');
      } else {
        const result = await adminRequest('/auth/kite/login', {method:'POST'});
        const target = new URL(result.redirect_url);
        if (target.origin !== 'https://kite.zerodha.com') throw new Error('Invalid provider login destination.');
        location.assign(target.href);
      }
    } catch (error) { notify(error.message, true, error.action); }
    finally { delete control.dataset.busy; }
  });
}
