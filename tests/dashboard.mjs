import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {SCANNER_FILTERS,matchesScannerFilter,uniqueScannerRows,scannerCounts,scannerLocation,scannerSearch} from '../static/scanner-view.js';
let passed=0;
const check=(name,fn)=>{fn();passed++;console.log('PASS '+name);};
const groups=[{id:'one',name:'One',stocks:[['A','Alpha'],['B','Beta'],['B','Beta']]},{id:'two',name:'Two',stocks:[['A','Alpha'],['C','Gamma'],['D','Delta',null,'suspended']]}];
const snapshot={rows:[{symbol:'NSE:A',match:true,near_match:false,change_pct:2,quote_status:'live',difference:0},
  {symbol:'NSE:B',match:false,near_match:true,change_pct:-1,quote_status:'stale',difference:2},
  {symbol:'NSE:C',match:false,near_match:false,change_pct:0,quote_status:'closed',difference:20}],
  intelligence:{opening:{'NSE:B':{gap_pct:1.25}}}};
const universeSource=await readFile(new URL('../static/sector-universe.json',import.meta.url),'utf8');
check('unique symbols retain every sector membership without duplicate list rows',()=>{
  const rows=uniqueScannerRows(groups,snapshot);assert.equal(rows.length,4);assert.equal(rows.reduce((n,r)=>n+r.membership_count,0),6);
  assert.deepEqual(rows[0].sector_ids,['one','two']);assert.equal(rows[1].membership_count,2);
});
check('all seven card counts use the exact same predicates as their destination',()=>{
  const rows=uniqueScannerRows(groups,snapshot),counts=scannerCounts(rows);
  assert.deepEqual(counts,{all:4,exact:1,near:1,matched:2,bull:1,bear:1,live:1});
  for(const filter of Object.keys(SCANNER_FILTERS))assert.equal(counts[filter],rows.filter(r=>matchesScannerFilter(r,filter)).length);
});
check('matches are backend flags, not rounded differences or a new tolerance',()=>{
  assert.equal(matchesScannerFilter({difference:0},'exact'),false);
  assert.equal(matchesScannerFilter({difference:0.001,near_match:false},'near'),false);
  assert.equal(matchesScannerFilter({difference:100,near_match:true},'near'),true);
});
check('matched includes exact and near only, counted once',()=>{
  assert.equal(scannerCounts([{symbol:'A',match:true,near_match:true},{symbol:'A',match:true,near_match:true},{symbol:'B',status:'MATCH'}]).matched,1);
});
check('missing quotes stay tracked without gaining financial classifications',()=>{
  const rows=uniqueScannerRows(groups,{rows:[]});assert.deepEqual(scannerCounts(rows),{all:4,exact:0,near:0,matched:0,bull:0,bear:0,live:0});
  assert.equal(rows[3].knownStatus,'suspended');assert.equal(rows[0].ltp,undefined);
});
check('percentage comes from the backend opening analysis, not daily change',()=>{
  const rows=uniqueScannerRows(groups,snapshot);assert.equal(rows[1].gap_pct,1.25);assert.equal(rows[0].gap_pct,null);
});
check('unverified movement values do not become bullish or bearish',()=>{
  for(const change_pct of [null,undefined,NaN,Infinity,'1',true])for(const filter of ['bull','bear'])assert.equal(matchesScannerFilter({change_pct},filter),false);
});
check('category, search, sector, sorting and pagination survive a URL round trip',()=>{
  const state={filter:'near',query:'B & C',sector:'one',sort:'gap_pct',direction:1,size:50,page:2,min:0,max:3.5};
  assert.deepEqual(scannerLocation(scannerSearch(state)),state);
});
check('unknown and malformed URL controls use safe defaults',()=>{
  const state=scannerLocation('?filter=__proto__&size=Infinity&page=-10&sort=constructor&min=NaN&max=-2');
  assert.equal(state.filter,'all');assert.equal(state.sort,'match_priority');assert.equal(state.size,25);assert.equal(state.page,1);assert.equal(state.min,null);assert.equal(state.max,null);
});
check('approved real universe remains 16 sectors and 160 memberships, with unique totals',()=>{
  const universe=JSON.parse(universeSource);assert.equal(universe.groups.length,16);
  assert.equal(universe.groups.reduce((n,g)=>n+g.stocks.length,0),160);
  const rows=uniqueScannerRows(universe.groups,{rows:[]});assert.equal(rows.length,148);assert.equal(scannerCounts(rows).all,148);
});
console.log(`${passed} dashboard consistency checks passed.`);
