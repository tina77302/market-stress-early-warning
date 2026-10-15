import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response

from .store import database
from src.runtime import allowed_origins, secure_cookie

COOKIE = 'mri_paper_session'
SESSION_SECONDS = 7 * 24 * 60 * 60


def secret():
    value = os.getenv('PAPER_SESSION_SECRET', '')
    if len(value) < 32:
        raise HTTPException(503, 'Account service requires a configured PAPER_SESSION_SECRET (at least 32 characters).')
    return value.encode()


def digest(token):
    return hmac.new(secret(), token.encode(), hashlib.sha256).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return 'scrypt$32768$8$3$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(value).decode()


def password_matches(password, encoded):
    try:
        parts = encoded.split('$')
        if len(parts) == 3:  # Previous local-development hash format.
            algorithm, salt, expected = parts
            n, r, p = 16384, 8, 1
        else:
            algorithm, n, r, p, salt, expected = parts
            n, r, p = int(n), int(r), int(p)
        if algorithm != 'scrypt' or n not in [16384, 32768] or r != 8 or p not in [1, 3]:
            return False
        value = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=n, r=r, p=p, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(value, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def check_origin(request: Request):
    origin = request.headers.get('origin')
    allowed = allowed_origins()
    if origin and origin not in [value.strip() for value in allowed]:
        raise HTTPException(403, 'Untrusted request origin.')


def current_user(request: Request, response: Response):
    check_origin(request)
    response.headers['Cache-Control'] = 'no-store'
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 256:
        raise HTTPException(401, 'Please log in to your paper portfolio.')
    with database() as db:
        row = db.execute('SELECT u.id,u.email,u.username,u.created_at,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?', (digest(token), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(401, 'Session expired. Please log in again.')
    return dict(row)


def csrf_token(request: Request):
    return hmac.new(secret(), ('csrf:' + request.cookies.get(COOKIE, '')).encode(), hashlib.sha256).hexdigest()


def protected_write(request: Request, user=Depends(current_user)):
    check_origin(request)
    submitted = request.headers.get('x-csrf-token', '')
    if not submitted or not hmac.compare_digest(submitted, csrf_token(request)):
        raise HTTPException(403, 'Session verification failed. Refresh the workspace.')
    return user


def set_session(db, user_id, request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    old = request.cookies.get(COOKIE)
    if old:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(old),))
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
    db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token), user_id, int(time.time()) + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, httponly=True, secure=secure_cookie(), samesite='lax', max_age=SESSION_SECONDS, path='/')


def throttle(request, email):
    now = int(time.time())
    keys = ['email:' + hashlib.sha256(email.encode()).hexdigest(), 'ip:' + (request.client.host if request.client else 'unknown')]
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE window_start<?', (now - 300,))
        for key, limit in zip(keys, [15, 100]):
            row = db.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
            if row and row['attempts'] >= limit:
                raise HTTPException(429, 'Too many authentication attempts. Try again in five minutes.')
            db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1', (key, now))
        db.commit()


def require_admin(user=Depends(current_user)):
    # Role is read from the database for every request, never trusted from the browser.
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required.')
    return user
