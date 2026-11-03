import {escapeHTML as esc,istStamp,fmt} from './ipo-core.js';
let latest,apiCall,notice,previousGeneration;
const labels={connected:'Connected',login_required:'Kite Login Required',api_key_missing:'API key missing',expired:'Expired · Kite Login Required',rate_limited:'Rate limited',disconnected:'Disconnected',degraded:'Degraded',error:'Error'};
const stateLabel=value=>labels[value]||'Checking';
const badge=provider=>`<span class="provider-state" data-state="${esc(provider.state)}">${esc(stateLabel(provider.state))}</span>`;
const fact=(label,value)=>`<dt>${esc(label)}</dt><dd>${esc(value??'Unavailable')}</dd>`;
function actions(provider){
  if(provider.name==='Zerodha Kite')return `<div class="control-row">${['login_required','expired','disconnected','api_key_missing','error'].includes(provider.state)?'<a href="/auth/kite/login" class="secondary connect">Official Kite login ↗</a>':'<button class="secondary" data-connection-action="kite/recheck">Recheck session</button>'}${!['disconnected','api_key_missing'].includes(provider.state)?'<button class="ghost" data-connection-action="kite/disconnect">Disconnect Kite</button>':''}</div>`;
  return `<p>IPO Guru initializes automatically when enabled with a valid backend key. Account access and limits are verified on the server.</p><button class="secondary" data-connection-action="ipo/recheck">Recheck configured provider</button>`;
}
function detail(provider){
  return `<article class="panel"><div class="panel-head"><h2>${esc(provider.name)}</h2>${badge(provider)}</div><dl>${fact('Authentication',provider.authentication)}${fact('Network',provider.network)}${fact('Last authentication',provider.last_authenticated?istStamp(provider.last_authenticated):'Not recorded')}${fact('Last validation',provider.last_validated?istStamp(provider.last_validated):'Unavailable')}${fact('Last local data update',provider.last_data_update?istStamp(provider.last_data_update):'Unavailable')}${fact('Data freshness',provider.freshness)}${provider.name==='Zerodha Kite'?fact('WebSocket',provider.websocket_connected?'Connected':'Disconnected')+fact('Active subscriptions',fmt(provider.active_subscriptions,'',0))+fact('Last received tick',provider.last_tick?istStamp(provider.last_tick):'Unavailable')+fact('Stale / unavailable',`${provider.stale_instruments} / ${provider.unavailable_instruments}`)+fact('Session storage',provider.persistence)+fact('Session expiry',provider.expires_at?istStamp(provider.expires_at):'Provider validation required'):fact('Verified plan',provider.plan||'Unavailable')+fact('Quota remaining',provider.quota?fmt(provider.quota.remaining,'',0):'Unavailable')+fact('GMP source timestamp',provider.gmp_source_timestamp?istStamp(provider.gmp_source_timestamp):'Unavailable')+fact('Subscription source timestamp',provider.subscription_source_timestamp?istStamp(provider.subscription_source_timestamp):'Unavailable')+fact('Cache',provider.cache_stale?'Stale cached response':'Shared backend cache')+fact('Next scheduled refresh',provider.configured?fmt(provider.next_refresh_seconds,' seconds',0):'Disabled')}${fact('Last error',provider.last_error||'None reported')}</dl>${actions(provider)}</article>`;
}
export function connectionPage(){return `<div class="page-header"><div><p class="kicker">PRIVATE PROVIDER CONTROL</p><h1>${location.pathname==='/health'?'Data Health Center':'Connection Manager'}</h1><p>Authentication, network connectivity and source freshness are separate. Market closure does not disconnect a valid session.</p></div></div><div id="connectionDetailsPage" class="health-provider-grid"><div class="panel">Loading backend provider health…</div></div><section class="panel"><h2>Session and data policy</h2><p>Kite uses the official daily login. Valid saved sessions are verified and restored automatically; expired sessions require official login. No password, TOTP or CAPTCHA is automated.</p><p>IPO Guru refreshes through one backend scheduler and shared cache. Source timestamps remain separate from successful local fetch time. Unknown or stale data stays labelled.</p><p>Historical retention and automatic AI training remain disabled unless separately authorized. This terminal places no orders or IPO applications.</p></section>`;}
export function receiveConnections(data,onIPOUpdate=()=>{}){
  if(!data?.kite||!data?.ipoguru)return;
  latest=data;
  const summary=document.getElementById('connectionSummary');
  if(summary)summary.textContent=`Connections · ${[data.kite,data.ipoguru].filter(p=>p.state==='connected').length}/2`;
  const dot=document.getElementById('connectionDot');if(dot)dot.dataset.state=data.summary==='connected'?'connected':[data.kite,data.ipoguru].some(p=>p.state==='error')?'error':'attention';
  const control=document.querySelector('#providerMenu>summary');if(control)control.setAttribute('aria-label',`Connections. Kite: ${stateLabel(data.kite.state)}. IPO Guru: ${stateLabel(data.ipoguru.state)}.`);
  const dropdown=document.getElementById('connectionDropdown');
  if(dropdown){const markup=[data.kite,data.ipoguru].map(p=>`<article class="provider-card"><h3>${esc(p.name)}</h3>${badge(p)}<p>Authentication: ${esc(p.authentication)} · Network: ${esc(p.network)}<br>Freshness: ${esc(p.freshness)}</p>${p.last_error?`<p>${esc(p.last_error)}</p>`:''}${p.name==='Zerodha Kite'?actions(p):'<a class="secondary" data-route href="/ipo">Open IPO Intelligence</a>'}</article>`).join('');if(dropdown.innerHTML!==markup)dropdown.innerHTML=markup;}
  const page=document.getElementById('connectionDetailsPage');if(page){const markup=detail(data.kite)+detail(data.ipoguru);if(page.innerHTML!==markup)page.innerHTML=markup;}
  const health=document.getElementById('unifiedHealthSummary');if(health)health.innerHTML=`<p>Kite: ${esc(stateLabel(data.kite.state))} · IPO Guru: ${esc(stateLabel(data.ipoguru.state))}</p><a data-route class="secondary" href="/health">Open unified Data Health Center</a>`;
  if(previousGeneration!==undefined&&previousGeneration!==data.ipo_generation&&!document.hidden)onIPOUpdate();previousGeneration=data.ipo_generation;
}
export async function refreshConnections(){try{receiveConnections(await apiCall('/api/connections/status'));}catch{/* Existing clock and page remain available during backend outages. */}}
export function mountConnections(){if(latest)receiveConnections(latest);else if(apiCall)refreshConnections();}
export function initializeConnections(api,notify){
  if(apiCall)return;apiCall=api;notice=notify;refreshConnections();
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-connection-action]');if(!button)return;
    button.disabled=true;
    try{const action=button.dataset.connectionAction;if(action==='ipo/recheck'){const value=await api('/api/ipo/verify',{method:'POST'});notice(value.meta?.error?.message||'Configured IPO Guru account checked.',!!value.meta?.error);await refreshConnections();}else{receiveConnections(await api('/api/connections/'+action,{method:'POST'}));notice(action.endsWith('disconnect')?'Kite disconnected and the saved session cleared.':'Kite recheck queued.');}}
    catch(error){notice(error.message,true,error.action);}finally{if(button.isConnected)button.disabled=false;}
  });
}
