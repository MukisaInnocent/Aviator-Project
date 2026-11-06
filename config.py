import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()

database_url = os.environ.get('DATABASE_URL') or 'postgresql://postgres:password@localhost/aviator_db'
if database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)


def _secret_key():
    key = os.environ.get('SECRET_KEY')
    if key and key != 'dev_secret_key_change_in_production':
        return key
    # Never fall back to a key that is published in the source code: anyone who
    # knows it could forge a session cookie. A random key keeps the app usable in
    # development, at the cost of logging everyone out on restart.
    warnings.warn(
        'SECRET_KEY is not set (or is the old default). Using a random key; '
        'sessions will not survive a restart. Set SECRET_KEY in .env.',
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_hex(32)


def _csv(name):
    return [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')

    # Cross-origin API access is off unless origins are listed explicitly,
    # e.g. CORS_ORIGINS=https://app.example.com,https://admin.example.com
    CORS_ORIGINS = _csv('CORS_ORIGINS')
