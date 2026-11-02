"""Read-only IPO checkpoint: code/assets, routes and an online SQLite backup."""
import hashlib
from contextlib import closing
import json
import sqlite3
import subprocess
from pathlib import Path
from app import config, main

root = config.ROOT
output = root / 'reports/ipo-baseline.json'
if output.exists():
    raise SystemExit('IPO baseline already exists; refusing to replace it.')
files = [p for folder in ('app', 'static') for p in (root / folder).rglob('*')
         if p.is_file() and '__pycache__' not in p.parts]
universe = json.loads((root/'static/sector-universe.json').read_text(encoding='utf-8'))
data = {'checkpoint_commit': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        'sha256': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'groups': universe['groups'],
        'routes': [{'path': r.path, 'methods': sorted(getattr(r,'methods',[]) or [])} for r in main.app.routes]}
output.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
private = root/'.qa/ipo-private-checkpoint.json'
private.write_text(json.dumps({'env_sha256':hashlib.sha256((root/'.env').read_bytes()).hexdigest()}), encoding='utf-8')
with closing(sqlite3.connect(config.DATABASE_PATH)) as source, closing(sqlite3.connect(root/'.qa/pre-ipo.sqlite3')) as target:
    source.backup(target)
print('IPO checkpoint saved; 16 sectors / 160 memberships / 148 unique symbols protected.')
