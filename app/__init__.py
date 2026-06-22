from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler
import os


def create_app(config_name=None):
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    from app.config import Config
    app.config.from_object(Config)

    if config_name == 'testing':
        app.config['TESTING'] = True

    if not app.config.get('TESTING'):
        log_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(os.path.dirname(log_dir), 'server.log')
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('应用分发平台启动')

    csrf = CSRFProtect(app)

    app.permanent_session_lifetime = timedelta(seconds=app.config.get('PERMANENT_SESSION_LIFETIME', 7 * 24 * 3600))

    from app.models import init_db
    init_db(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(int(user_id))

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.upload import upload_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(upload_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    csrf.exempt(api_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template('413.html'), 413

    @app.errorhandler(500)
    def server_error(e):
        return render_template('500.html'), 500

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    @app.template_filter('highlight')
    def highlight_filter(text, query):
        if not query or not text:
            return text
        import re
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return pattern.sub(lambda m: f'<mark>{m.group()}</mark>', text)

    @app.context_processor
    def inject_globals():
        from app.utils import get_server_ip, get_lan_ip, is_lan_access, detect_platform
        from flask import request as req

        server_ip = get_server_ip()
        lan_ip = get_lan_ip()
        host = req.host
        is_lan = is_lan_access(host)
        client_platform = detect_platform()

        if host and not host.startswith('127.') and not host.startswith('localhost'):
            server_ip = host

        return {
            'server_ip': server_ip,
            'lan_ip': lan_ip,
            'is_lan': is_lan,
            'client_platform': client_platform,
        }

    return app
