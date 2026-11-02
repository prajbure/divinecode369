import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
const python=process.env.DIVINE_PYTHON||'.venv/Scripts/python.exe';
const commands=[['regression',process.execPath,['scripts/verify_advanced.mjs','v21-final']],
  ['clock',process.execPath,['tests/clock.mjs']],['ipo-frontend',process.execPath,['tests/ipo_frontend.mjs']],
  ['ipo-fixtures',python,['-m','tests.ipo_fixture']],['ipo-browser',process.execPath,['tests/ipo_browser.mjs']],
  ['v21-browser',process.execPath,['tests/v21_browser.mjs']],['integrity',python,['-m','scripts.verify_v21_integrity']],
  ['build',process.execPath,['scripts/build.mjs']],['typecheck',process.execPath,['node_modules/typescript/bin/tsc','-p','tsconfig.json','--noEmit']]];
const checks=[];
for(const [name,command,args]of commands){
  const result=spawnSync(command,args,{encoding:'utf8',windowsHide:true,timeout:300000});
  const output=(result.stdout||'')+(result.stderr||'')+(result.error?.message||'');
  writeFileSync(`.qa/v21-final-${name}.txt`,output);
  checks.push({name,passed:result.status===0,exit:result.status});
  console.log(JSON.stringify({name,passed:result.status===0,tail:output.slice(-1200)}));
  if(result.status!==0)break;
}
let counts=null;
if(checks.length===commands.length&&checks.every(v=>v.passed)){
  const read=p=>readFileSync(p,'utf8');
  counts={python:Number(read('.qa/advanced-v21-final-python.txt').match(/Ran (\d+) tests/)[1]),
    financial_formatting:Number(read('.qa/advanced-v21-final-frontend.txt').match(/(\d+) financial/)[1]),
    intelligence:Number(read('.qa/advanced-v21-final-intelligence.txt').match(/(\d+) intelligence checks/)[1]),
    original_browser:100,clock:JSON.parse(read('.qa/v21-final-clock.txt').trim().split('\n').at(-1)).passed,
    ipo_frontend:JSON.parse(read('.qa/v21-final-ipo-frontend.txt').trim().split('\n').at(-1)).passed,
    ipo_browser:JSON.parse(read('reports/ipo-browser-checks.json')).passed,
    v21_browser:JSON.parse(read('reports/v21-browser-checks.json')).passed};
  counts.total=Object.values(counts).reduce((sum,v)=>sum+v,0);
}
writeFileSync('reports/v21-final-checks.json',JSON.stringify({checks,counts},null,2)+'\n');
process.exitCode=counts?0:1;
