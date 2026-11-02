"""Pre-V2.1 manifest and online database backup. Never copies credentials into reports."""
from contextlib import closing
import hashlib
import json
import sqlite3
import subprocess
from app import config,main

root=config.ROOT
destination=root/'reports/v21-baseline.json'
if destination.exists():raise SystemExit('Baseline exists; refusing to overwrite.')
files=[p for folder in ('app','static') for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
manifest={'checkpoint':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          'sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
          'groups':json.loads((root/'static/sector-universe.json').read_text(encoding='utf-8'))['groups'],
          'routes':[{'path':r.path,'methods':sorted(getattr(r,'methods',[]) or [])} for r in main.app.routes]}
destination.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'.qa/v21-private-baseline.json').write_text(json.dumps({'env_sha256':hashlib.sha256((root/'.env').read_bytes()).hexdigest()}),encoding='utf-8')
with closing(sqlite3.connect(config.DATABASE_PATH)) as source,closing(sqlite3.connect(root/'.qa/pre-v21.sqlite3')) as target:source.backup(target)
print('V2.1 baseline and database backup saved.')
