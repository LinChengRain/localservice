import os
from dotenv import load_dotenv

load_dotenv()

_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')

_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    _secret_key = os.urandom(24).hex()
    with open(_env_file, 'a') as f:
        f.write(f'\nSECRET_KEY={_secret_key}\n')


class Config:
    SECRET_KEY = _secret_key
    DATABASE = os.getenv('DATABASE', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'apps.db'))
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads'))
    CERT_FOLDER = os.getenv('CERT_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'certs'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 500 * 1024 * 1024))
    LAN_REQUIRE_LOGIN = os.getenv('LAN_REQUIRE_LOGIN', 'false').lower() == 'true'
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme')
    API_KEY = os.getenv('API_KEY', '')
    PERMANENT_SESSION_LIFETIME = int(os.getenv('PERMANENT_SESSION_LIFETIME', 7 * 24 * 3600))
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', 5))
    LOGIN_LOCKOUT_SECONDS = int(os.getenv('LOGIN_LOCKOUT_SECONDS', 300))
    PER_PAGE = int(os.getenv('PER_PAGE', 20))


class TestingConfig(Config):
    TESTING = True
    DATABASE = ':memory:'
