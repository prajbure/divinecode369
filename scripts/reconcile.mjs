// Export the server's actual verified metadata, without quotes or credentials.
import {mkdir, readFile, writeFile} from 'node:fs/promises';
const base = process.env.DIVINE_TEST_URL || 'http://127.0.0.1:8000';
const refresh = process.argv.includes('--refresh');
const response = await fetch(base + (refresh ? '/api/instruments/reconcile' : '/api/instruments/reconciliation'), {
  method: refresh ? 'POST' : 'GET',
  headers: refresh ? {'X-Divine-Request': '1'} : {},
});
if (!response.ok) throw new Error('Instrument audit failed (HTTP ' + response.status + '). Renew Kite and retry; no unverified report is presented as current.');
const report = await response.json();
const registry = JSON.parse(await readFile('data/instrument-aliases.json', 'utf8'));
for (const item of report.instruments) {
  if (registry.unavailable[item.requested_symbol]) item.notice_source = registry.unavailable[item.requested_symbol].source;
}
await mkdir('reports', {recursive:true});
await writeFile('reports/instrument-reconciliation.json', JSON.stringify(report, null, 2) + '\n');
const table = (head, rows) => [head, head.map(()=>'---'), ...rows].map(r=>'| '+r.map(v=>String(v??'--').replaceAll('|','/')).join(' | ')+' |').join('\n');
const text = `# Approved instrument reconciliation\n\nGenerated ${report.generated_at}. ${report.source}.\n\n` +
table(['Measure','Count'],[
  ['Configured sector entries',report.total_configured_entries],['Unique requested instruments',report.unique_requested_instruments],
  ['Scan candidates (known suspension excluded)',report.scan_candidates],['Verified Kite instruments',report.verified_kite_instruments],
  ['Exact symbols',report.verified_exact],['Explicit same-company aliases',report.verified_aliases],
  ['Additional duplicate memberships',report.duplicate_membership_count],['Unavailable or suspended',report.unavailable_instruments.length],
  ['Unresolved aliases',report.unresolved_aliases.length],
]) + '\n\n' + report.note + '\n\n## Resolutions and unavailable members\n\n' +
table(['Configured symbol','Verified provider symbol','State','Resolution','Explanation','Source'],report.instruments.filter(i=>i.resolution_kind!=='exact').map(i=>[i.requested_symbol,i.provider_symbol,i.state,i.resolution_kind,i.explanation,`[evidence](${i.notice_source||i.source})`])) +
'\n\n## Duplicate memberships\n\n'+table(['Instrument','Memberships','Extra entries'],report.duplicate_memberships.map(d=>[d.symbol,d.memberships.map(m=>m.sector+' #'+m.entry).join('; '),d.extra_entries]))+
'\n\n## Complete audit\n\n[Machine-readable report](./instrument-reconciliation.json) includes all instruments, memberships, evidence and verification timestamps. Unverified metadata is labeled unverified; no missing company is substituted.\n';
await writeFile('reports/instrument-reconciliation.md', text);
console.log(JSON.stringify({configured:report.total_configured_entries,unique:report.unique_requested_instruments,verified:report.verified_kite_instruments,aliases:report.verified_aliases,unavailable:report.unavailable_instruments.map(i=>i.requested_symbol),unresolvedAliases:report.unresolved_aliases.length}));
