import sqlite3
from flask import g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                version TEXT NOT NULL,
                filename TEXT NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                icon_filename TEXT,
                description TEXT,
                build_number TEXT DEFAULT '',
                build_type TEXT DEFAULT 'release',
                platform TEXT DEFAULT 'ios',
                file_size INTEGER DEFAULT 0
            )
        ''')
        for col, default in [("build_number", "''"), ("build_type", "'release'"), ("platform", "'ios'"), ("file_size", "0")]:
            try:
                db.execute(f"ALTER TABLE apps ADD COLUMN {col} TEXT DEFAULT {default}")
            except sqlite3.OperationalError:
                pass
        db.execute('CREATE INDEX IF NOT EXISTS idx_apps_platform ON apps(platform)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_apps_bundle_id ON apps(bundle_id)')

        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS download_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES apps(id)
            )
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS changelogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES apps(id)
            )
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                locked_until REAL
            )
        ''')

        db.commit()

        _ensure_admin_user(db, app.config.get('ADMIN_USERNAME', 'admin'),
                           app.config.get('ADMIN_PASSWORD', 'changeme'))
        db.close()


def _ensure_admin_user(db, username, password):
    from werkzeug.security import check_password_hash
    existing = db.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        if not check_password_hash(existing['password_hash'], password):
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, existing['id']))
            db.commit()
    else:
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                   (username, password_hash, 'admin'))
        db.commit()


class User(UserMixin):
    def __init__(self, id, username, password_hash, role, created_at):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.created_at = created_at

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def get_by_id(user_id):
        from app.models import get_db
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['password_hash'],
                        row['role'], row['created_at'])
        return None
