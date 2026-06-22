from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required
from app.routes import auth_bp
from app.models import User, get_db
import time


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        db = get_db()

        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        lockout_seconds = current_app.config.get('LOGIN_LOCKOUT_SECONDS', 300)

        failed_row = db.execute(
            'SELECT attempts, locked_until FROM login_attempts WHERE username = ?',
            (username,)
        ).fetchone()

        if failed_row and failed_row['locked_until']:
            if time.time() < failed_row['locked_until']:
                remaining = int(failed_row['locked_until'] - time.time())
                flash(f'账户已锁定，请 {remaining} 秒后重试')
                return render_template('login.html')
            else:
                db.execute('DELETE FROM login_attempts WHERE username = ?', (username,))
                db.commit()

        row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row:
            user = User(row['id'], row['username'], row['password_hash'],
                        row['role'], row['created_at'])
            if user.check_password(password):
                db.execute('DELETE FROM login_attempts WHERE username = ?', (username,))
                db.commit()
                login_user(user)
                flash('登录成功')
                return redirect(url_for('main.index'))

        if failed_row:
            attempts = failed_row['attempts'] + 1
        else:
            attempts = 1

        if attempts >= max_attempts:
            locked_until = time.time() + lockout_seconds
            db.execute(
                'INSERT OR REPLACE INTO login_attempts (username, attempts, locked_until) VALUES (?, ?, ?)',
                (username, attempts, locked_until)
            )
            flash(f'登录失败次数过多，账户已锁定 {lockout_seconds // 60} 分钟')
        else:
            db.execute(
                'INSERT OR REPLACE INTO login_attempts (username, attempts, locked_until) VALUES (?, ?, NULL)',
                (username, attempts)
            )
            flash('用户名或密码错误')

        db.commit()

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录')
    return redirect(url_for('main.index'))
