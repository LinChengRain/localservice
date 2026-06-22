from flask import Blueprint

main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__)
upload_bp = Blueprint('upload', __name__)
admin_bp = Blueprint('admin', __name__)
api_bp = Blueprint('api', __name__)

from app.routes import main, auth, upload, admin, api
