"""No network calls. Secret values are compared in memory and never emitted."""
import hashlib
import json
from pathlib import Path
from app import config

ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(name,result):
    checks.append({'check':name,'passed':bool(result)})
    print(('PASS ' if result else 'FAIL ')+name)

approved=json.loads((ROOT/'static/sector-universe.json').read_text(encoding='utf-8'))
check('16 sectors and 160 memberships',len(approved['groups'])==16 and sum(len(g['stocks']) for g in approved['groups'])==160)
check('Approved universe original byte hash',hashlib.sha256((ROOT/'static/sector-universe.json').read_bytes()).hexdigest()=='61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad')
check('Original scanner byte hash',hashlib.sha256((ROOT/'app/scanner.py').read_bytes()).hexdigest()=='cedf41dd728d97b9221261fc8af7772ca005d016e542f7f5c86983b76e699f6d')
files=list((ROOT/'static').glob('*.js'))+list((ROOT/'android/app/src').rglob('*.kt'))+list((ROOT/'contracts').glob('*.json'))
payloads=[p.read_text(encoding='utf-8') for p in files]
for name in ('ADMIN_TOKEN','ADMIN_PASSWORD_HASH','KITE_API_SECRET','KITE_ACCESS_TOKEN','IPOGURU_API_KEY'):
    value=getattr(config,name,'')
    check(name+' value absent from browser/native/contract sources',not value or all(value not in text for text in payloads))
private=ROOT/'.qa/private-admin/admin-login.json'
if private.exists():
    value=json.loads(private.read_text(encoding='utf-8')).get('password')
    check('Configured owner password absent from client sources',not value or all(value not in text for text in payloads))
check('No signing keystore in Android source tree',not list((ROOT/'android').rglob('*.jks')) and not list((ROOT/'android').rglob('*.keystore')))
contract=json.loads((ROOT/'contracts/mobile-v1.openapi.json').read_text(encoding='utf-8'))
check('Mobile contract declares both credential types',{'MobileBearer','AdminCookie'}<=set(contract['components']['securitySchemes']))
check('Protected mobile writes declare scoped auth',bool(contract['paths']['/api/v1/mobile/watchlist']['put'].get('security')))
check('Native network disallows cleartext', 'cleartextTrafficPermitted="false"' in (ROOT/'android/app/src/main/res/xml/network_security_config.xml').read_text())
report={'checks':checks,'passed':sum(c['passed'] for c in checks),'scope':'Source and preservation checks only. No APK exists, so packaged APK secret inspection was not performed.'}
(ROOT/'reports/PLATFORM_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
if not all(c['passed'] for c in checks):raise SystemExit(1)
