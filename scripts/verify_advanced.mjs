import {spawnSync} from 'node:child_process';
import {mkdirSync,writeFileSync,existsSync} from 'node:fs';
const stage=process.argv[2]||'final';
mkdirSync('.qa',{recursive:true});
const commands=[['python',['-m','unittest','discover','-s','tests','-v']],['node',['tests/frontend.mjs']]];
if(existsSync('tests/intelligence.mjs'))commands.push(['node',['tests/intelligence.mjs']]);
commands.push(['node',['tests/browser.mjs']]);
let failure=false;const checks=[];
for(const [label,args] of commands){
  const executable=label==='python'?process.env.DIVINE_PYTHON||'.venv/Scripts/python.exe':process.execPath;
  const result=spawnSync(executable,args,{encoding:'utf8',windowsHide:true,timeout:180000});
  const log=(result.stdout||'')+(result.stderr||'')+(result.error?.message||'');
  const name=label==='python'?'python':args[0].split('/').pop().replace('.mjs','');
  writeFileSync(`.qa/advanced-${stage}-${name}.txt`,log);
  const passed=result.status===0;failure ||= !passed;checks.push({name,passed,exit:result.status});
  console.log(JSON.stringify({stage,name,passed,tail:log.slice(-1000)}));
  if(!passed)break;
}
writeFileSync(`reports/advanced-${stage}-checks.json`,JSON.stringify({stage,checks},null,2)+'\n');
process.exitCode=failure?1:0;
