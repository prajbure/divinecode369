"""Server-side administrator sessions. No backend credentials are sent to clients."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config

COOKIE = "__Host-divine_admin"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PREAUTH_SECONDS = 600
LOGIN_WINDOW = 900


def hash_password(password: str) -> str:
    if not 14 <= len(password) <= 1024:
        raise ValueError("Use an administrator password of 14 to 1024 characters.")
    salt = secrets.token_hex(16)
    # OWASP's 16 MiB / p=5 scrypt profile also fits smaller hosting instances.
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5).hex()
    return f"scrypt$16384$8$5${salt}${digest}"


def valid_password_hash(encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = encoded.split("$")
        return (algorithm, n, r, p) == ("scrypt", "16384", "8", "5") and len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 64
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    if not valid_password_hash(encoded) or not isinstance(password, str) or len(password) > 1024:
        return False
    *_, salt, expected = encoded.split("$")
    try:
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5)
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(actual, bytes.fromhex(expected))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AdminAuth:
    @property
    def configured(self):
        try:
            origin = urlsplit(config.ADMIN_ORIGIN)
            origin.port  # Validate malformed ports without accepting them as configuration.
        except ValueError:
            return False
        return bool(len(config.ADMIN_TOKEN) >= 32 and 0 < len(config.ADMIN_USERNAME) <= 256 and valid_password_hash(config.ADMIN_PASSWORD_HASH)
                    and origin.scheme == "https" and origin.netloc and not origin.username
                    and not origin.path and not origin.query and not origin.fragment)

    def version(self):
        return hmac.new(config.ADMIN_TOKEN.encode(), (config.ADMIN_USERNAME + "\n" + config.ADMIN_PASSWORD_HASH).encode(), "sha256").hexdigest()

    @contextmanager
    def database(self):
        path = config.ADMIN_SESSION_DATABASE_PATH
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE IF NOT EXISTS admin_sessions (id TEXT PRIMARY KEY, authenticated INTEGER NOT NULL, expires REAL NOT NULL, version TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS admin_attempts (peer TEXT NOT NULL, created REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS admin_oauth (state TEXT PRIMARY KEY, session TEXT NOT NULL, expires REAL NOT NULL)")
            db.execute("DELETE FROM admin_sessions WHERE expires <= ?", (time.time(),))
            db.execute("DELETE FROM admin_attempts WHERE created <= ?", (time.time() - LOGIN_WINDOW,))
            db.execute("DELETE FROM admin_oauth WHERE expires <= ?", (time.time(),))
            yield db
            db.commit()
        finally:
            db.close()

    def transport(self, request, *, oauth_callback=False):
        if request.url.scheme != "https":
            raise HTTPException(403, "Administrator authentication requires HTTPS.")
        # An OAuth provider must navigate back from its own site. Only the exact
        # callback's top-level GET may use that path; session + single-use state
        # are still mandatory before any provider credential exchange.
        oauth_navigation = (
            oauth_callback and request.method == "GET"
            and request.url.path == "/auth/kite/callback"
            and request.headers.get("sec-fetch-mode") == "navigate"
            and request.headers.get("sec-fetch-dest") == "document"
        )
        if request.headers.get("sec-fetch-site") == "cross-site" and not oauth_navigation:
            raise HTTPException(403, "Cross-site administrator requests are not allowed.")
        origin = request.headers.get("origin")
        if origin and origin != config.ADMIN_ORIGIN:
            raise HTTPException(403, "Cross-origin administrator requests are not allowed.")

    def session(self, request):
        if not self.configured:
            return None
        raw = request.cookies.get(COOKIE, "")
        if len(raw) != 43:
            return None
        with self.database() as db:
            row = db.execute("SELECT * FROM admin_sessions WHERE id = ?", (digest(raw),)).fetchone()
        if row and hmac.compare_digest(row["version"], self.version()):
            return dict(row)
        return None

    def csrf(self, raw):
        return hmac.new(config.ADMIN_TOKEN.encode(), ("csrf\n" + raw).encode(), "sha256").hexdigest()

    def require_csrf(self, request):
        self.transport(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not request.headers.get("origin") or not hmac.compare_digest(supplied.encode(), self.csrf(request.cookies.get(COOKIE, "")).encode()):
            raise HTTPException(403, "CSRF verification failed. Reload the page and try again.")

    def require_admin(self, request: Request, *, oauth_callback=False):
        self.transport(request, oauth_callback=oauth_callback)
        session = self.session(request)
        if not session or not session["authenticated"]:
            raise HTTPException(401, "Sign in as an administrator in Settings to continue.", headers={"X-Divine-Auth": "admin-login-required"})
        if request.method not in SAFE_METHODS:
            self.require_csrf(request)
        return session

    def create(self, request, authenticated=False):
        raw = secrets.token_urlsafe(32)
        seconds = config.ADMIN_SESSION_SECONDS if authenticated else PREAUTH_SECONDS
        expires = time.time() + seconds
        with self.database() as db:
            db.execute("DELETE FROM admin_sessions WHERE id = ?", (digest(request.cookies.get(COOKIE, "")),))
            db.execute("INSERT INTO admin_sessions VALUES (?, ?, ?, ?)", (digest(raw), int(authenticated), expires, self.version()))
        response = JSONResponse({"authenticated": authenticated, "csrf_token": self.csrf(raw), "expires_at": expires})
        response.set_cookie(COOKIE, raw, max_age=seconds, secure=True, httponly=True, samesite="lax", path="/")
        return response

    def reserve_attempt(self, request):
        # Only the ASGI connection peer is used; arbitrary forwarding headers are ignored.
        peer = digest(request.client.host if request.client else "unknown")
        blocked = False
        with self.database() as db:
            count = db.execute("SELECT COUNT(*) FROM admin_attempts WHERE peer = ?", (peer,)).fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM admin_attempts").fetchone()[0]
            blocked = count >= 5 or total >= 100
            if not blocked:
                db.execute("INSERT INTO admin_attempts VALUES (?, ?)", (peer, time.time()))
        if blocked:
            raise HTTPException(429, "Too many login attempts. Try again in 15 minutes.", headers={"Retry-After": str(LOGIN_WINDOW)})

    def start_oauth(self, request, state):
        session = self.require_admin(request)
        with self.database() as db:
            db.execute("DELETE FROM admin_oauth WHERE session = ?", (session["id"],))
            db.execute("INSERT INTO admin_oauth VALUES (?, ?, ?)", (digest(state), session["id"], time.time() + 600))

    def consume_oauth(self, request, state):
        session = self.require_admin(request, oauth_callback=True)
        with self.database() as db:
            deleted = db.execute("DELETE FROM admin_oauth WHERE state = ? AND session = ?", (digest(state), session["id"])).rowcount
        if deleted != 1:
            raise HTTPException(400, "Kite login state expired or was already used. Start login again.")


auth = AdminAuth()
router = APIRouter(prefix="/auth/admin")


@router.get("/session")
def session_status(request: Request):
    auth.transport(request)
    if not auth.configured:
        raise HTTPException(503, "Administrator login is not configured. The server owner must configure the admin credentials.")
    session = auth.session(request)
    if not session:
        return auth.create(request)
    return {"authenticated": bool(session["authenticated"]), "csrf_token": auth.csrf(request.cookies[COOKIE]), "expires_at": session["expires"]}


@router.post("/login")
def login(request: Request, body: dict):
    auth.transport(request)
    if not auth.configured:
        raise HTTPException(503, "Administrator login is not configured.")
    auth.require_csrf(request)
    if not auth.session(request):
        raise HTTPException(403, "Login session expired. Reload the page and try again.")
    auth.reserve_attempt(request)
    username, password = body.get("username"), body.get("password")
    password_ok = verify_password(password, config.ADMIN_PASSWORD_HASH)
    try:
        username_ok = isinstance(username, str) and len(username) <= 256 and hmac.compare_digest(username.encode(), config.ADMIN_USERNAME.encode())
    except UnicodeEncodeError:
        username_ok = False
    if not password_ok or not username_ok:
        raise HTTPException(401, "Invalid administrator credentials.")
    return auth.create(request, authenticated=True)


@router.post("/logout")
def logout(request: Request):
    session = auth.require_admin(request)
    with auth.database() as db:
        db.execute("DELETE FROM admin_sessions WHERE id = ?", (session["id"],))
        db.execute("DELETE FROM admin_oauth WHERE session = ?", (session["id"],))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    response.delete_cookie("kite_oauth_state", secure=True, httponly=True, samesite="lax", path="/")
    response.delete_cookie("divine_scan_session")
    return response
