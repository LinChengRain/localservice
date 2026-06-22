import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    DATABASE = os.getenv('DATABASE', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'apps.db'))
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads'))
    CERT_FOLDER = os.getenv('CERT_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'certs'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 500 * 1024 * 1024))
    LAN_REQUIRE_LOGIN = os.getenv('LAN_REQUIRE_LOGIN', 'false').lower() == 'true'
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme')


class TestingConfig(Config):
    TESTING = True
    DATABASE = ':memory:'
