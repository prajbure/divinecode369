"""Verify the IPO addition did not change protected application data or assets."""
from contextlib import closing
import hashlib
import json
import sqlite3
from app import config,main


def verify():
    root=config.ROOT
    baseline=json.loads((root/'reports/ipo-baseline.json').read_text(encoding='utf-8'))
    allowed={'app/config.py','app/main.py','static/app.js','static/index.html'}
    checked={path:hashlib.sha256((root/path).read_bytes()).hexdigest()==expected
             for path,expected in baseline['sha256'].items() if path not in allowed}
    private=json.loads((root/'.qa/ipo-private-checkpoint.json').read_text(encoding='utf-8'))
    routes={}
    for route in main.app.routes:routes.setdefault(route.path,set()).update(getattr(route,'methods',[]) or [])
    original_routes=all(set(r['methods'])<=routes.get(r['path'],set()) for r in baseline['routes'])
    tables={}
    with closing(sqlite3.connect(f'file:{(root/".qa/pre-ipo.sqlite3").as_posix()}?mode=ro',uri=True)) as before, closing(sqlite3.connect(f'file:{config.DATABASE_PATH.as_posix()}?mode=ro',uri=True)) as after:
        for name, in before.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted='"'+name.replace('"','""')+'"'
            old=before.execute('SELECT * FROM '+quoted).fetchall()
            current=after.execute('SELECT * FROM '+quoted).fetchall()
            tables[name]={'before':len(old),'after':len(current),'unchanged':set(old)==set(current)}
        integrity=after.execute('PRAGMA integrity_check').fetchone()[0]
    groups=json.loads((root/'static/sector-universe.json').read_text(encoding='utf-8'))['groups']
    report={'checkpoint':baseline['checkpoint_commit'], 'protected_files_checked':len(checked),
        'protected_files_unchanged':all(checked.values()),'original_routes_preserved':original_routes,
        'env_unchanged':hashlib.sha256((root/'.env').read_bytes()).hexdigest()==private['env_sha256'],
        'universe_sha256':hashlib.sha256((root/'static/sector-universe.json').read_bytes()).hexdigest(),
        'sector_definitions_unchanged':groups==baseline['groups'], 'sectors':len(groups),
        'memberships':sum(len(g['stocks']) for g in groups),
        'unique_symbols':len({s[0] for g in groups for s in g['stocks']}),
        'database_integrity':integrity,'tables':tables,
        'ipo_enabled':config.IPOGURU_ENABLED,'ipo_key_configured':bool(config.IPOGURU_API_KEY),
        'retention_authorized':config.DATA_RETENTION_AUTHORIZED,'auto_training':config.AUTO_RETRAIN_ENABLED}
    (root/'reports/ipo-integrity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert report['protected_files_unchanged'] and report['original_routes_preserved'] and report['env_unchanged']
    assert report['sector_definitions_unchanged'] and (report['sectors'],report['memberships'],report['unique_symbols'])==(16,160,148)
    assert integrity=='ok' and all(v['unchanged'] for v in tables.values())
    assert not report['retention_authorized'] and not report['auto_training']
    print(json.dumps({k:v for k,v in report.items() if k!='tables'}))


if __name__=='__main__':verify()
