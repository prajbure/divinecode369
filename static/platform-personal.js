import {adminRequest,refreshAdminSession} from './admin-auth.js';
import {escapeHTML as esc,fmt,istStamp} from './ipo-core.js';
const key='divine-personal-watchlist-v1';
let themeListening=false;
export function initializePlatformPreferences(){
  const update=()=>{let choice='dark';try{choice=localStorage.getItem('divine-theme')||'dark';}catch{}document.documentElement.dataset.theme=choice==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):choice==='light'?'light':'dark';};
  update();if(!themeListening){matchMedia('(prefers-color-scheme: dark)').addEventListener('change',update);themeListening=true;}
}
const targetPath=v=>v.kind==='stock'?'/stocks/'+encodeURIComponent((v.symbol||'').replace(/^NSE:/,'')):'/ipo/details/'+encodeURIComponent(v.ipo_slug);
const targetLabel=v=>v.kind==='stock'?v.symbol:v.ipo_slug;
let saved=[];try{const value=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(value))saved=value.filter(v=>['ipo','stock'].includes(v.kind)&&typeof v.key==='string'&&typeof v.label==='string'&&v.key.length<=150&&v.label.length<=150).slice(0,1000);}catch{}
let authenticated=false,pending=null;
function persist(){try{localStorage.setItem(key,JSON.stringify(saved));}catch{}window.dispatchEvent(new Event('divine-personal-change'));}
export function watched(kind,id){return saved.some(v=>v.kind===kind&&v.key===id&&v.saved);}
export async function syncPersonal(){
  if(pending)return pending;
  pending=(async()=>{
    const session=await refreshAdminSession();authenticated=session.authenticated;
    if(!authenticated)return saved;
    for(const item of saved.filter(v=>v.dirty)){const revision=item.saved;await adminRequest('/api/v1/mobile/watchlist',{method:'PUT',body:JSON.stringify({kind:item.kind,key:item.key,label:item.label,saved:revision})});if(item.saved===revision)item.dirty=false;}
    const result=await adminRequest('/api/v1/mobile/watchlist');
    for(const item of result.items){const local=saved.find(v=>v.kind===item.kind&&v.key===item.key);if(!local?.dirty){if(local)Object.assign(local,item);else saved.push({...item,dirty:false});}}
    persist();return saved;
  })().finally(()=>{pending=null;});return pending;
}
export async function toggleWatch(kind,id,label){
  let item=saved.find(v=>v.kind===kind&&v.key===id);
  if(!item){item={kind,key:id,label,saved:false};saved.push(item);}
  item.saved=!item.saved;item.dirty=true;persist();
  if(authenticated)await syncPersonal();return item.saved;
}
export function personalShell(){return '<section id="personalWorkspace"><h1>'+ (location.pathname==='/alerts'?'Alerts':'Watchlists')+'</h1><div id="personalContent" aria-live="polite">Loading account…</div></section>';}
export async function mountPersonalPage({notice}){
  const root=document.getElementById('personalWorkspace');if(!root)return;
  const content=root.querySelector('#personalContent');
  try{
    await syncPersonal();if(!root.isConnected)return;
    if(location.pathname==='/watchlists'){
      const items=saved.filter(v=>v.saved);
      content.innerHTML=`<p class="subtle-note">${authenticated?'Synced with Android':'Saved on this browser · sign in to sync'}</p><div class="personal-records">${items.map(v=>`<article class="ipo-panel"><a data-route href="${v.kind==='ipo'?'/ipo/details/':'/stocks/'}${encodeURIComponent(v.key.replace(/^NSE:/,''))}">${esc(v.label)}</a><small>${esc(v.kind.toUpperCase())}${v.dirty?' · pending sync':''}</small><button class="ghost" data-unsave="${esc(v.key)}" data-kind="${v.kind}">Remove</button></article>`).join('')||'<p>No saved instruments.</p>'}</div>`;
      root.onclick=async event=>{const button=event.target.closest('[data-unsave]');if(!button)return;try{await toggleWatch(button.dataset.kind,button.dataset.unsave,'Saved instrument');mountPersonalPage({notice});}catch(error){notice(error.message,true);}};
      return;
    }
    if(!authenticated){content.innerHTML='<p>Sign in as owner to synchronize alert rules and your backend inbox.</p><a class="secondary" data-route href="/settings">Sign in</a>';return;}
    const [rules,inbox,sectors]=await Promise.all([adminRequest('/api/v1/mobile/alerts'),adminRequest('/api/v1/mobile/alerts/inbox'),adminRequest('/api/v1/mobile/sectors')]);if(!root.isConnected)return;
    content.innerHTML=`<p class="subtle-note">Backend events · opt-in Android delivery · no Firebase configured</p><details class="ipo-panel"><summary>Add market alert</summary><form id="marketAlertForm"><label>Stock<select name="symbol">${[...new Map(sectors.items.flatMap(s=>s.stocks).map(s=>[s.symbol,s])).values()].map(s=>`<option value="${esc(s.symbol)}">${esc(s.symbol)} · ${esc(s.name)}</option>`).join('')}</select></label><label>Event<select name="event"><option value="exact">Exact opening match</option><option value="near">Near opening match</option><option value="price_above">Price reaches above ₹</option><option value="price_below">Price reaches below ₹</option></select></label><label>Price threshold<input name="threshold" type="number" min="0" max="1000000" step="0.01"></label><button class="secondary" type="submit">Save market alert</button></form><small>Fresh quotes during an open session only. Android inbox delivery may be delayed.</small></details><h2>Your rules</h2><div class="personal-records">${rules.items.filter(v=>!v.deleted).map(v=>`<article class="ipo-panel"><a data-route href="${targetPath(v)}">${esc(targetLabel(v))}</a><span>${esc(v.event.replaceAll('_',' '))}${v.threshold!=null?' ≥ '+esc(fmt(v.threshold)):''}</span><button class="ghost" data-delete-rule="${esc(v.id)}">Delete</button></article>`).join('')||'<p>Add a rule from an IPO detail screen.</p>'}</div><h2>Inbox</h2>${inbox.items.map(v=>`<article class="ipo-panel"><a href="${targetPath(v)}" data-route>${esc(v.title)}</a><small>${esc(istStamp(v.created_at))}</small></article>`).join('')||'<p>No events yet.</p>'}`;
    root.onsubmit=async event=>{if(event.target.id!=='marketAlertForm')return;event.preventDefault();const values=new FormData(event.target),type=values.get('event'),value=values.get('threshold');if(type.startsWith('price_')&&(value===''||!Number.isFinite(Number(value)))){notice('Enter a price threshold.',true);return;}try{await adminRequest('/api/v1/mobile/alerts',{method:'PUT',body:JSON.stringify({kind:'stock',symbol:values.get('symbol'),event:type,threshold:type.startsWith('price_')?Number(value):null})});notice('Market alert saved.');mountPersonalPage({notice});}catch(error){notice(error.message,true);}};
    root.onclick=async event=>{const button=event.target.closest('[data-delete-rule]');if(!button)return;button.disabled=true;try{await adminRequest('/api/v1/mobile/alerts/'+encodeURIComponent(button.dataset.deleteRule),{method:'DELETE'});mountPersonalPage({notice});}catch(error){notice(error.message,true);button.disabled=false;}};
  }catch(error){if(root.isConnected)content.textContent=error.message;}
}
export async function addIpoAlert(slug,event,threshold){return adminRequest('/api/v1/mobile/alerts',{method:'PUT',body:JSON.stringify({ipo_slug:slug,event,threshold,enabled:true})});}

export async function mountPlatformSettings(notice){
  if(location.pathname!=='/settings')return;
  document.getElementById('platformAccount')?.remove();
  const panel=document.createElement('section');panel.id='platformAccount';panel.className='panel';
  panel.innerHTML='<h2>Display &amp; account</h2><form id="platformPreferences" class="platform-preferences"><label>Theme<select name="theme"><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label><label>Density<select name="density"><option value="compact">Compact</option><option value="comfortable">Comfortable</option><option value="large">Large</option></select></label><label><input type="checkbox" name="notifications"> Android inbox notifications</label><button class="secondary">Save preferences</button></form><p id="platformPreferenceState" class="subtle-note"></p><details><summary>Approved Android devices</summary><button class="secondary" type="button" id="refreshApprovedDevices">Refresh devices</button><div id="approvedDevices"></div></details><p><a href="/watchlists" data-route>Watchlists</a> · <a href="/alerts" data-route>Market &amp; IPO alerts</a> · <a href="/privacy" target="_blank" rel="noopener">Privacy</a></p>';
  document.getElementById('main').append(panel);
  const form=panel.querySelector('form'),state=panel.querySelector('#platformPreferenceState');
  let signedIn=false;
  function apply(value){form.elements.theme.value=value.theme;form.elements.density.value=value.density;form.elements.notifications.checked=value.notifications;document.documentElement.dataset.density=value.density;document.documentElement.dataset.theme=value.theme;try{localStorage.setItem('divine-density',value.density);localStorage.setItem('divine-theme',value.theme);}catch{}initializePlatformPreferences();}
  async function devices(){
    const target=panel.querySelector('#approvedDevices');
    try{const result=await adminRequest('/auth/mobile/sessions');if(!panel.isConnected)return;target.innerHTML=result.items.map(device=>`<div class="setting-row"><span>${esc(device.device)}<small>Expires ${esc(new Date(device.expires*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}))} IST</small></span><button class="ghost" data-revoke-device="${esc(device.id)}">Revoke</button></div>`).join('')||'<p>No approved devices.</p>';}catch(error){target.textContent=error.message;}
  }
  try{const session=await refreshAdminSession();signedIn=session.authenticated;if(!panel.isConnected)return;if(signedIn)apply(await adminRequest('/api/v1/mobile/preferences'));state.textContent=signedIn?'Preferences sync with Android. Notification permission is controlled on each device.':'Sign in to synchronize preferences and manage devices.';}catch(error){state.textContent=error.message;}
  form.onsubmit=async event=>{event.preventDefault();const value={theme:form.elements.theme.value,density:form.elements.density.value,notifications:form.elements.notifications.checked};apply(value);try{if(signedIn)await adminRequest('/api/v1/mobile/preferences',{method:'PUT',body:JSON.stringify(value)});notice(signedIn?'Preferences synced.':'Display saved on this browser.');}catch(error){notice(error.message,true);}};
  panel.querySelector('#refreshApprovedDevices').onclick=devices;
  panel.onclick=async event=>{const button=event.target.closest('[data-revoke-device]');if(!button)return;button.disabled=true;try{await adminRequest('/auth/mobile/sessions/'+encodeURIComponent(button.dataset.revokeDevice),{method:'DELETE'});await devices();notice('Device access revoked.');}catch(error){notice(error.message,true);button.disabled=false;}};
}
