"""Verify protected sources, universe, routes and pre-existing research/journal data."""
from contextlib import closing
import hashlib
import json
import sqlite3
from app import config,main

APPROVED_CHANGES={'app/config.py','app/main.py','app/provider.py','app/market.py','app/ipo_routes.py','app/ipoguru.py',
                  'static/index.html','static/app.js','static/ipo.js','static/intelligence-core.js','static/command-center.js'}


def verify():
    root=config.ROOT
    baseline=json.loads((root/'reports/v21-baseline.json').read_text(encoding='utf-8'))
    checked={p:hashlib.sha256((root/p).read_bytes()).hexdigest()==expected for p,expected in baseline['sha256'].items() if p not in APPROVED_CHANGES}
    routes={}
    for route in main.app.routes:routes.setdefault(route.path,set()).update(getattr(route,'methods',[]) or [])
    original_routes=all(set(r['methods'])<=routes.get(r['path'],set()) for r in baseline['routes'])
    private=json.loads((root/'.qa/v21-private-baseline.json').read_text(encoding='utf-8'))
    current_env=hashlib.sha256((root/'.env').read_bytes()).hexdigest()
    observation=root/'.qa/v21-external-env.json'
    external=json.loads(observation.read_text(encoding='utf-8')) if observation.exists() else None
    expected_env=external['observed_env_sha256'] if external else private['env_sha256']
    tables={}
    with closing(sqlite3.connect(f'file:{(root/".qa/pre-v21.sqlite3").as_posix()}?mode=ro',uri=True)) as before,closing(sqlite3.connect(f'file:{config.DATABASE_PATH.as_posix()}?mode=ro',uri=True)) as after:
        for name, in before.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted='"'+name.replace('"','""')+'"'
            old=before.execute('SELECT * FROM '+quoted).fetchall();current=after.execute('SELECT * FROM '+quoted).fetchall()
            mutable_metadata=name in ('capabilities','instrument_resolutions','instruments')
            if mutable_metadata:
                old_keys={r[0] for r in old};new_keys={r[0] for r in current}
                preserved=old_keys<=new_keys
            else:preserved=set(old)<=set(current)
            tables[name]={'before':len(old),'after':len(current),'all_original_records_preserved':preserved,
                          'unchanged':set(old)==set(current),'normal_provider_metadata':mutable_metadata}
        integrity=after.execute('PRAGMA integrity_check').fetchone()[0]
        instrument_count=after.execute('SELECT COUNT(*) FROM instruments').fetchone()[0]
        membership_count=after.execute('SELECT COUNT(*) FROM sector_memberships').fetchone()[0]
    groups=json.loads((root/'static/sector-universe.json').read_text(encoding='utf-8'))['groups']
    report={'checkpoint':baseline['checkpoint'],'protected_files_checked':len(checked),'protected_files_unchanged':all(checked.values()),
            'all_original_routes_preserved':original_routes,'sector_definitions_unchanged':groups==baseline['groups'],
            'sectors':len(groups),'memberships':sum(len(g['stocks']) for g in groups),
            'unique_symbols':len({s[0] for g in groups for s in g['stocks']}),
            'universe_sha256':hashlib.sha256((root/'static/sector-universe.json').read_bytes()).hexdigest(),
            'database_integrity':integrity,'database_instruments':instrument_count,'database_memberships':membership_count,'tables':tables,
            'env_matches_original_checkpoint':current_env==private['env_sha256'],
            'external_configuration_update_recorded':bool(external),'env_matches_latest_recorded_observation':current_env==expected_env,
            'ipo_key_present':bool(config.IPOGURU_API_KEY),'ipo_enabled':config.IPOGURU_ENABLED,
            'retention_authorized':config.DATA_RETENTION_AUTHORIZED,'auto_training':config.AUTO_RETRAIN_ENABLED}
    (root/'reports/v21-integrity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert all(checked.values()) and original_routes and groups==baseline['groups']
    assert (len(groups),report['memberships'],report['unique_symbols'])==(16,160,148)
    assert current_env==expected_env and integrity=='ok' and instrument_count==148 and membership_count==160
    assert all(t['all_original_records_preserved'] for t in tables.values())
    assert not config.DATA_RETENTION_AUTHORIZED and not config.AUTO_RETRAIN_ENABLED
    print(json.dumps({k:v for k,v in report.items() if k!='tables'}))


if __name__=='__main__':verify()
