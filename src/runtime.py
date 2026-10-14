"""Environment-only deployment safeguards; no market or portfolio calculations."""
import os
from urllib.parse import urlsplit


def staging():
    return os.getenv('APP_ENV', 'development').lower() in {'staging', 'production'}


def secure_cookie():
    return os.getenv('PAPER_COOKIE_SECURE', 'true' if staging() else 'false').lower() == 'true'


def allowed_origins():
    default = '' if staging() else 'http://127.0.0.1:3000,http://localhost:3000'
    return [value.strip() for value in os.getenv('PAPER_ALLOWED_ORIGINS', default).split(',') if value.strip()]


def validate_runtime():
    if not staging():
        return
    if len(os.getenv('PAPER_SESSION_SECRET', '')) < 32:
        raise RuntimeError('Staging requires PAPER_SESSION_SECRET with at least 32 characters.')
    origins = allowed_origins()
    if not origins or any(urlsplit(value).scheme != 'https' or not urlsplit(value).netloc or
                          urlsplit(value).path or urlsplit(value).query or urlsplit(value).fragment or
                          urlsplit(value).username for value in origins):
        raise RuntimeError('Staging requires explicit HTTPS PAPER_ALLOWED_ORIGINS.')
    if not secure_cookie():
        raise RuntimeError('Staging requires secure session cookies.')
    if not os.getenv('MARKET_DATA_ROOT') or not os.getenv('MARKET_MODELS_ROOT'):
        raise RuntimeError('Staging requires explicit persistent data and model roots.')
