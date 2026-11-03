import {readFileSync} from 'node:fs';
import {sectorMetrics,marketRegime,openingIntelligence,opportunity,VolumeTracker} from '../static/intelligence-core.js';
const fixtures=JSON.parse(readFileSync(0,'utf8'));
const results=fixtures.map(f=>{
  const sectors=f.groups.map(g=>sectorMetrics(g,f.rows));
  const openings=f.rows.map(r=>openingIntelligence(r,f.context,f.session,Date.parse(f.now)));
  const opportunities=f.rows.map((r,i)=>opportunity(r,f.groups,sectors,openings[i],{},f.weights));
  const tracker=new VolumeTracker(),volumes=f.sequence.map(r=>tracker.observe(r));
  return {sectors,regime:marketRegime(f.groups,f.rows),openings,opportunities,volumes};
});
process.stdout.write(JSON.stringify(results));
