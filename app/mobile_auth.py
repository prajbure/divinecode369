"""Owner-approved public-client device flow. Mobile credentials never grant admin rights."""
import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import config
from .admin_auth import auth, digest
from .mobile_models import APIError

SCOPES = ['market:read', 'ipo:read', 'research:read', 'personal:write']
ACCESS_SECONDS = 900
REFRESH_SECONDS = 7 * 86400
FAMILY_SECONDS = 30 * 86400


class RequestLimits:
    """Bounded per-process protection keyed by the actual ASGI peer, never forwarded claims."""
    def __init__(self): self.lock=threading.Lock();self.buckets={}
    def allow(self,peer,mutation=False,now=None):
        window=int((time.time() if now is None else now)//60)
        with self.lock:
            self.buckets={k:v for k,v in self.buckets.items() if v[0]==window}
            key=digest(peer)+(':write' if mutation else ':read')
            if len(self.buckets)>=4096 and key not in self.buckets:return False
            count=self.buckets.get(key,(window,0))[1]+1
            self.buckets[key]=(window,count)
            return count<=(60 if mutation else 300)


request_limits=RequestLimits()


@contextmanager
def database():
    path = config.PLATFORM_DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS device_requests(id TEXT PRIMARY KEY, code TEXT NOT NULL, name TEXT NOT NULL, challenge TEXT NOT NULL, expires REAL NOT NULL, approved INTEGER NOT NULL DEFAULT 0, last_poll REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mobile_families(id TEXT PRIMARY KEY, owner TEXT NOT NULL, device TEXT NOT NULL, expires REAL NOT NULL, version TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mobile_access(hash TEXT PRIMARY KEY, family TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS mobile_refresh(hash TEXT PRIMARY KEY, family TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS device_attempts(peer TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS access_family ON mobile_access(family);
        CREATE INDEX IF NOT EXISTS refresh_family ON mobile_refresh(family);
        ''')
        db.execute('BEGIN IMMEDIATE')
        if 'approved_version' not in {r[1] for r in db.execute('PRAGMA table_info(device_requests)')}:
            db.execute("ALTER TABLE device_requests ADD COLUMN approved_version TEXT NOT NULL DEFAULT ''")
        db.execute('DELETE FROM device_requests WHERE expires <= ?', (time.time(),))
        db.execute('DELETE FROM mobile_access WHERE expires <= ?', (time.time(),))
        db.execute('DELETE FROM mobile_refresh WHERE expires <= ?', (time.time(),))
        db.execute('DELETE FROM mobile_families WHERE expires <= ?', (time.time(),))
        db.execute('DELETE FROM device_attempts WHERE created < ?', (time.time()-60,))
        yield db
        db.commit()
    finally:
        db.close()


def transport(request):
    if request.url.scheme != 'https':
        raise HTTPException(403, 'HTTPS is required.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site authentication requests are not allowed.')
    if request.headers.get('origin') and request.headers['origin'] != config.ADMIN_ORIGIN:
        raise HTTPException(403, 'Cross-origin authentication requests are not allowed.')


def mobile_identity(request, scope=None):
    transport(request)
    supplied = request.headers.get('authorization', '')
    if not supplied.startswith('Bearer dc_access_') or len(supplied) > 200 or not auth.configured:
        raise HTTPException(401, 'Mobile sign-in required.')
    with database() as db:
        row = db.execute('SELECT f.*, a.expires AS access_expires FROM mobile_access a JOIN mobile_families f ON f.id=a.family WHERE a.hash=?', (digest(supplied[7:]),)).fetchone()
    if not row or row['revoked'] or row['expires'] <= time.time() or row['access_expires'] <= time.time() or not hmac.compare_digest(row['version'], auth.version()):
        raise HTTPException(401, 'Mobile session expired or revoked.')
    if scope and scope not in SCOPES:
        raise HTTPException(403, 'The device does not have this permission.')
    return {'owner': row['owner'], 'family': row['id'], 'device': row['device'], 'scopes': SCOPES}


def personal_identity(request, scope='personal:write'):
    if request.headers.get('authorization'):
        return mobile_identity(request, scope)
    auth.require_admin(request)
    return {'owner': 'owner', 'family': None, 'device': 'Website', 'scopes': ['admin']}


def issue(db, family, deadline):
    access, refresh = 'dc_access_' + secrets.token_urlsafe(32), 'dc_refresh_' + secrets.token_urlsafe(48)
    now = time.time()
    db.execute('INSERT INTO mobile_access VALUES(?,?,?)', (digest(access), family, min(deadline, now+ACCESS_SECONDS)))
    db.execute('INSERT INTO mobile_refresh VALUES(?,?,?,0)', (digest(refresh), family, min(deadline, now+REFRESH_SECONDS)))
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer', 'expires_in': max(1,int(min(ACCESS_SECONDS,deadline-now))), 'scope': ' '.join(SCOPES)}


class DeviceStart(BaseModel):
    device_name: str = Field(min_length=1, max_length=80)
    code_challenge: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


class DeviceGrant(BaseModel):
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code_verifier: str = Field(pattern=r'^[A-Za-z0-9._~-]{43,128}$')


class RefreshGrant(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=200)


class DeviceStarted(BaseModel):
    request_id: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class MobileTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: str


router = APIRouter(prefix='/auth/mobile', tags=['Mobile authentication'],responses={status:{'model':APIError} for status in (400,401,403,404,422,429,503)})


@router.post('/start', response_model=DeviceStarted)
def start(request: Request, body: DeviceStart):
    transport(request)
    if not auth.configured:
        raise HTTPException(503, 'Owner sign-in is not configured.')
    peer = digest(request.client.host if request.client else 'unknown')
    blocked = False
    request_id = secrets.token_urlsafe(32)
    code = secrets.token_hex(4).upper()
    code = code[:4] + '-' + code[4:]
    with database() as db:
        blocked = db.execute('SELECT COUNT(*) FROM device_attempts WHERE peer=?', (peer,)).fetchone()[0] >= 5 or db.execute('SELECT COUNT(*) FROM device_requests').fetchone()[0] >= 1000
        if not blocked:
            db.execute('INSERT INTO device_attempts VALUES(?,?)', (peer, time.time()))
            db.execute('INSERT INTO device_requests(id,code,name,challenge,expires) VALUES(?,?,?,?,?)', (request_id, code, body.device_name, body.code_challenge, time.time()+600))
    if blocked:
        raise HTTPException(429, 'Too many device requests.', headers={'Retry-After': '60'})
    return {'request_id': request_id, 'user_code': code, 'verification_uri': config.ADMIN_ORIGIN + '/mobile/connect?request=' + request_id, 'expires_in': 600, 'interval': 5}


@router.get('/requests/{request_id}')
def inspect_request(request: Request, request_id: str):
    auth.require_admin(request)
    with database() as db:
        row = db.execute('SELECT code,name,expires,approved FROM device_requests WHERE id=?', (request_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Device request expired.')
    return {**dict(row), 'scopes': SCOPES}


@router.post('/requests/{request_id}/approve')
def approve(request: Request, request_id: str):
    auth.require_admin(request)
    with database() as db:
        changed = db.execute('UPDATE device_requests SET approved=1,approved_version=? WHERE id=?', (auth.version(),request_id)).rowcount
    if not changed:
        raise HTTPException(404, 'Device request expired.')
    return {'approved': True}


@router.post('/token', response_model=MobileTokens)
def redeem(request: Request, body: DeviceGrant):
    transport(request)
    error = None
    result = None
    challenge = base64.urlsafe_b64encode(hashlib.sha256(body.code_verifier.encode()).digest()).rstrip(b'=').decode()
    with database() as db:
        row = db.execute('SELECT * FROM device_requests WHERE id=?', (body.request_id,)).fetchone()
        if not row or not hmac.compare_digest(row['challenge'], challenge):
            error = HTTPException(401, 'Invalid or expired device request.')
        elif time.time() - row['last_poll'] < 5:
            error = HTTPException(429, 'Poll no more than once every five seconds.', headers={'Retry-After': '5'})
        elif not row['approved']:
            db.execute('UPDATE device_requests SET last_poll=? WHERE id=?', (time.time(), body.request_id))
            error = HTTPException(428, 'Owner approval pending.', headers={'Retry-After': '5'})
        elif not auth.configured:
            error = HTTPException(503, 'Owner sign-in is not configured.')
        elif not hmac.compare_digest(row['approved_version'],auth.version()):
            error = HTTPException(401,'Device approval expired. Start sign-in again.')
        else:
            family = secrets.token_hex(16)
            deadline = time.time()+FAMILY_SECONDS
            db.execute('INSERT INTO mobile_families VALUES(?,?,?,?,?,0)', (family, 'owner', row['name'], deadline, auth.version()))
            db.execute('DELETE FROM device_requests WHERE id=?', (body.request_id,))
            result = issue(db, family, deadline)
    if error:
        raise error
    return result


@router.post('/refresh', response_model=MobileTokens)
def refresh(request: Request, body: RefreshGrant):
    transport(request)
    error = None
    result = None
    with database() as db:
        row = db.execute('SELECT r.*, f.expires AS deadline, f.version, f.revoked FROM mobile_refresh r JOIN mobile_families f ON f.id=r.family WHERE r.hash=?', (digest(body.refresh_token),)).fetchone()
        if not row or row['revoked'] or row['expires'] <= time.time() or row['deadline'] <= time.time() or not auth.configured or not hmac.compare_digest(row['version'], auth.version()):
            error = HTTPException(401, 'Refresh session expired or revoked.')
        elif row['used']:
            db.execute('UPDATE mobile_families SET revoked=1 WHERE id=?', (row['family'],))
            db.execute('DELETE FROM mobile_access WHERE family=?', (row['family'],))
            error = HTTPException(401, 'Refresh credential reuse detected. Sign in again.')
        else:
            db.execute('UPDATE mobile_refresh SET used=1 WHERE hash=?', (digest(body.refresh_token),))
            db.execute('DELETE FROM mobile_access WHERE family=?', (row['family'],))
            result = issue(db, row['family'], row['deadline'])
    if error:
        raise error
    return result


@router.post('/logout')
def logout(request: Request):
    identity = mobile_identity(request)
    with database() as db:
        db.execute('UPDATE mobile_families SET revoked=1 WHERE id=?', (identity['family'],))
        db.execute('DELETE FROM mobile_access WHERE family=?', (identity['family'],))
    return {'revoked': True}


@router.get('/session')
def session(request: Request):
    return mobile_identity(request)


@router.get('/sessions')
def devices(request:Request):
    auth.require_admin(request)
    with database() as db:
        rows=db.execute('SELECT id,device,expires FROM mobile_families WHERE revoked=0 AND version=?',(auth.version(),)).fetchall()
    return {'items':[dict(row) for row in rows]}


@router.delete('/sessions/{family}')
def revoke_device(request:Request,family:str):
    auth.require_admin(request)
    with database() as db:
        db.execute('UPDATE mobile_families SET revoked=1 WHERE id=?',(family,))
        db.execute('DELETE FROM mobile_access WHERE family=?',(family,))
    return {'revoked':True}
