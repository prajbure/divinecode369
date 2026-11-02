"""Record immutable upgrade inputs; never copy credentials into a report."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import config, main


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    report_path = ROOT / 'reports' / 'advanced-upgrade-baseline.json'
    if report_path.exists():
        raise SystemExit('Baseline already exists; refusing to overwrite it.')
    universe = json.loads((ROOT / 'static/sector-universe.json').read_text(encoding='utf-8'))
    protected = ['static/sector-universe.json', 'app/scanner.py', 'data/watchlist.txt',
                 'data/instrument-aliases.json', 'data/nse-calendar-2026.json']
    protected += [str(p.relative_to(ROOT)).replace('\\', '/') for p in (ROOT / 'static').rglob('*')
                  if p.suffix.lower() in {'.svg', '.webp', '.png', '.jpg'}]
    manifest = {path: digest(ROOT / path) for path in sorted(protected)}
    memberships = sum(len(g['stocks']) for g in universe['groups'])
    unique = {s[0] for g in universe['groups'] for s in g['stocks']}
    assert (len(universe['groups']), memberships, len(unique)) == (16, 160, 148)
    report = {'checkpoint_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'active_application': 'FastAPI app.main:app; static/index.html and static/app.js',
              'groups': universe['groups'], 'memberships': memberships, 'unique_symbols': sorted(unique),
              'protected_sha256': manifest,
              'routes': [{'path': r.path, 'methods': sorted(getattr(r, 'methods', []) or [])} for r in main.app.routes],
              'formulas': {'difference': 'Decimal(str(open)) - Decimal(str(previous_close))',
                           'exact': 'valid positive finite opening/reference prices AND difference.is_zero()',
                           'near': 'not exact AND abs(difference) <= Decimal(str(MAX_DIFFERENCE))'},
              'runtime_dependencies': (ROOT / 'requirements.txt').read_text(),
              'retention_authorized': config.DATA_RETENTION_AUTHORIZED,
              'auto_retrain_enabled': config.AUTO_RETRAIN_ENABLED}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    private = ROOT / '.qa/advanced-private-baseline.json'
    private.write_text(json.dumps({'env_sha256': digest(ROOT / '.env')}, indent=2), encoding='utf-8')
    if config.DATABASE_PATH.exists():
        with sqlite3.connect(f'file:{config.DATABASE_PATH.as_posix()}?mode=ro', uri=True) as source:
            with sqlite3.connect(ROOT / '.qa/advanced-checkpoint.sqlite3') as backup:
                source.backup(backup)
    print(json.dumps({'groups': 16, 'memberships': memberships, 'unique': len(unique),
                      'universe_sha256': manifest['static/sector-universe.json'],
                      'protected_files': len(manifest), 'routes': len(report['routes'])}))


if __name__ == '__main__':
    audit()
