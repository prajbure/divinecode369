import assert from 'node:assert/strict';
import {formatIST,startISTClock} from '../static/clock.js';
let passed=0;const check=(name,fn)=>{fn();passed++;console.log('PASS '+name);};
check('IST uses HH:MM:SS independently of operating-system timezone',()=>{for(const tz of ['UTC','America/Los_Angeles','Asia/Tokyo']){process.env.TZ=tz;assert.equal(formatIST(new Date('2026-11-02T23:00:01Z')),'04:30:01');}});
const original={document:globalThis.document,setInterval:globalThis.setInterval,clearInterval:globalThis.clearInterval,addEventListener:globalThis.addEventListener};
const intervals=new Map(),listeners=new Map(),clock={};let serial=0;
globalThis.document={getElementById:id=>id==='headerClock'?clock:null};
globalThis.setInterval=(fn,delay)=>{intervals.set(++serial,{fn,delay});return serial;};
globalThis.clearInterval=id=>intervals.delete(id);
globalThis.addEventListener=(name,fn)=>listeners.set(name,fn);
try{
  startISTClock();startISTClock();
  check('repeated initialization retains exactly one second timer',()=>{assert.equal(intervals.size,1);assert.equal([...intervals.values()][0].delay,1000);});
  check('clock exposes a machine-readable instant without another date element',()=>{assert.match(clock.textContent,/^\d\d:\d\d:\d\d$/);assert.ok(Number.isFinite(Date.parse(clock.dateTime)));});
  listeners.get('pagehide')();check('page exit clears timer',()=>assert.equal(intervals.size,0));
  listeners.get('pageshow')();listeners.get('pageshow')();check('page restoration starts only one timer',()=>assert.equal(intervals.size,1));
  listeners.get('pagehide')();
}finally{Object.assign(globalThis,original);}
console.log(JSON.stringify({passed}));
