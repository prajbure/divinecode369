"""Read-only comparison against the pre-upgrade SQLite and file checkpoint."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import config


def verify():
    baseline=json.loads((ROOT/'reports/advanced-upgrade-baseline.json').read_text(encoding='utf-8'))
    protected={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected for name,expected in baseline['protected_sha256'].items()}
    private=json.loads((ROOT/'.qa/advanced-private-baseline.json').read_text(encoding='utf-8'))
    tables=['candles','quote_snapshots','scan_results','history_imports','model_versions','model_metrics','predictions','training_evaluations']
    results={}
    with sqlite3.connect(f'file:{(ROOT/".qa/advanced-checkpoint.sqlite3").as_posix()}?mode=ro',uri=True) as before,sqlite3.connect(f'file:{config.DATABASE_PATH.as_posix()}?mode=ro',uri=True) as after:
        for table in tables:
            original=before.execute(f'SELECT * FROM {table}').fetchall()
            current=after.execute(f'SELECT * FROM {table}').fetchall()
            # Comparing complete rows catches a removed or altered record, even when counts agree.
            results[table]={'before':len(original),'after':len(current),'unchanged':set(original)==set(current)}
        results['instruments']={'after':after.execute('SELECT COUNT(*) FROM instruments').fetchone()[0]}
        results['sector_memberships']={'after':after.execute('SELECT COUNT(*) FROM sector_memberships').fetchone()[0]}
        results['database_integrity']=after.execute('PRAGMA integrity_check').fetchone()[0]
        journal=after.execute("SELECT name FROM sqlite_master WHERE name='personal_journal_v1'").fetchone()
        results['manual_journal_records']=after.execute('SELECT COUNT(*) FROM personal_journal_v1').fetchone()[0] if journal else 0
    report={'universe_sha256':hashlib.sha256((ROOT/'static/sector-universe.json').read_bytes()).hexdigest(),
            'protected_files':len(protected),'all_protected_files_unchanged':all(protected.values()),
            'env_unchanged':hashlib.sha256((ROOT/'.env').read_bytes()).hexdigest()==private['env_sha256'],
            'retention_authorized':config.DATA_RETENTION_AUTHORIZED,'auto_retrain_enabled':config.AUTO_RETRAIN_ENABLED,
            'database':results}
    (ROOT/'reports/advanced-runtime-integrity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert report['all_protected_files_unchanged'] and report['env_unchanged']
    assert not report['retention_authorized'] and not report['auto_retrain_enabled']
    assert all(results[t]['unchanged'] for t in tables)
    assert results['instruments']['after']==148 and results['sector_memberships']['after']==160
    assert results['database_integrity']=='ok'
    print(json.dumps(report))


if __name__=='__main__':verify()
