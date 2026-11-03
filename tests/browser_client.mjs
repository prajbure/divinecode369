import {spawn} from 'node:child_process';
import {mkdir,mkdtemp,writeFile} from 'node:fs/promises';
import path from 'node:path';
export const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function browser(){
  await mkdir('.qa',{recursive:true});const profile=await mkdtemp(path.resolve('.qa/platform-chrome-'));
  const process=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--ignore-certificate-errors','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
  const endpoint=await new Promise((resolve,reject)=>{let data='';const timer=setTimeout(()=>reject(Error('Chrome startup timeout')),15000);process.stderr.on('data',chunk=>{data+=chunk;const match=data.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});process.on('error',reject);});
  const target=await(await fetch(`http://127.0.0.1:${new URL(endpoint).port}/json/new?about:blank`,{method:'PUT'})).json();
  const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let serial=0;const pending=new Map(),errors=[];
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id&&pending.has(msg.id)){const task=pending.get(msg.id);clearTimeout(task.timer);pending.delete(msg.id);msg.error?task.reject(Error(msg.error.message)):task.resolve(msg.result);}else if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.exception?.description||msg.params.exceptionDetails.text);};
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;};
  const wait=async expression=>{for(let i=0;i<120;i++){try{if(await evaluate(expression))return;}catch{}await sleep(100);}throw Error('DOM wait: '+expression);};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const navigate=async url=>{await send('Page.navigate',{url});};
  const screenshot=async name=>{const result=await send('Page.captureScreenshot',{format:'png'});await writeFile(name,Buffer.from(result.data,'base64'));};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  return {send,evaluate,wait,click,navigate,errors,screenshot,close(){ws.close();process.kill();}};
}
