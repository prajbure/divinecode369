import {spawnSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';
const python=process.env.DIVINE_PYTHON||'.venv/Scripts/python.exe';
const commands=[['regression',process.execPath,['scripts/verify_advanced.mjs','ipo-final']],
  ['ipo-frontend',process.execPath,['tests/ipo_frontend.mjs']],
  ['ipo-fixtures',python,['-m','tests.ipo_fixture']],
  ['ipo-browser',process.execPath,['tests/ipo_browser.mjs']],
  ['integrity',python,['-m','scripts.verify_ipo_integrity']],
  ['build',process.execPath,['scripts/build.mjs']],
  ['typecheck',process.execPath,['node_modules/typescript/bin/tsc','-p','tsconfig.json','--noEmit']]];
const checks=[];
for(const [name,command,args]of commands){
  const result=spawnSync(command,args,{encoding:'utf8',windowsHide:true,timeout:300000});
  const output=(result.stdout||'')+(result.stderr||'')+(result.error?.message||'');
  writeFileSync(`.qa/ipo-final-${name}.txt`,output);
  checks.push({name,passed:result.status===0,exit:result.status});
  console.log(JSON.stringify({name,passed:result.status===0,tail:output.slice(-1000)}));
  if(result.status!==0)break;
}
writeFileSync('reports/ipo-final-checks.json',JSON.stringify({checks},null,2)+'\n');
process.exitCode=checks.length===commands.length&&checks.every(v=>v.passed)?0:1;
