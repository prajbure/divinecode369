import {adminRequest,initializeAdminSession,mountAdminSession,refreshAdminSession} from './admin-auth.js';
const target=document.getElementById('approval'), notice=document.getElementById('deviceNotice');
const request=new URL(location.href).searchParams.get('request');
history.replaceState(null,'','/mobile/connect');
function message(value){notice.textContent=value;refresh().catch(()=>{});}
initializeAdminSession(message);
async function refresh(){
  if(!request||!/^[A-Za-z0-9_-]{43}$/.test(request)){target.textContent='Invalid device request. Start sign-in again in the app.';return;}
  const session=await refreshAdminSession();
  if(!session.authenticated){target.textContent='Sign in, then compare the code shown on your Android device.';return;}
  const device=await adminRequest('/auth/mobile/requests/'+request);
  target.replaceChildren();
  const name=document.createElement('h2');name.textContent=device.name;
  const code=document.createElement('code');code.textContent=device.code;
  const explanation=document.createElement('p');explanation.textContent='Approve only if this code matches the app you just opened.';
  const permissions=document.createElement('p');permissions.className='device-permissions';permissions.textContent='Read market, IPO and research data. Manage your watchlist, alerts and preferences.';
  const approve=document.createElement('button');approve.className='primary';approve.textContent=device.approved?'Approved — return to the app':'Approve device';approve.disabled=!!device.approved;
  approve.onclick=async()=>{approve.disabled=true;try{await adminRequest('/auth/mobile/requests/'+request+'/approve',{method:'POST'});approve.textContent='Approved — return to the app';}catch(error){notice.textContent=error.message;approve.disabled=false;}};
  target.append(name,code,explanation,permissions,approve);
}
await mountAdminSession();
refresh().catch(error=>{notice.textContent=error.message;});
