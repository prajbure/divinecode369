// One document-scoped IST clock, independent of both providers.
const formatter=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
let timer=null,onTick=()=>{},registered=false;
export const formatIST=instant=>formatter.format(instant);
function tick(){const now=new Date(),clock=document.getElementById('headerClock');if(clock){clock.textContent=formatIST(now);clock.dateTime=now.toISOString();}onTick(now);}
function stop(){if(timer!==null){clearInterval(timer);timer=null;}}
export function startISTClock(callback=()=>{}){
  onTick=callback;tick();if(timer===null)timer=setInterval(tick,1000);
  if(!registered){registered=true;addEventListener('pagehide',stop);addEventListener('pageshow',()=>{tick();if(timer===null)timer=setInterval(tick,1000);});}
}
