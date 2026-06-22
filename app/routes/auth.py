from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from app.routes import auth_bp
from app.models import User, get_db
from app.utils import is_lan_access


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    host = request.host
    if not is_lan_access(host):
        flash('登录仅限内网访问')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row:
            user = User(row['id'], row['username'], row['password_hash'],
                        row['role'], row['created_at'])
            if user.check_password(password):
                login_user(user)
                flash('登录成功')
                return redirect(url_for('main.index'))
        flash('用户名或密码错误')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录')
    return redirect(url_for('main.index'))
