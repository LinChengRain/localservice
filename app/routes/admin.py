import os
import shutil
from datetime import datetime
from flask import redirect, url_for, flash, current_app, render_template, request, send_file, jsonify
from app.routes import admin_bp
from app.models import get_db, cleanup_old_logs
from app.utils import admin_required


def log_audit(action, target_id=None, detail=None):
    db = get_db()
    operator = 'admin'
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            operator = current_user.username
    except Exception:
        pass
    db.execute(
        'INSERT INTO audit_logs (action, target_id, detail, operator, created_at) VALUES (?, ?, ?, ?, ?)',
        (action, target_id, detail, operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    db.commit()


@admin_bp.route('/edit/<int:app_id>', methods=['GET', 'POST'])
@admin_required
def edit(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if not app_data:
        flash('应用不存在')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name = request.form.get('name', app_data['name'])
        description = request.form.get('description', '')
        build_type = request.form.get('build_type', app_data['build_type'])

        db.execute(
            'UPDATE apps SET name = ?, description = ?, build_type = ? WHERE id = ?',
            (name, description, build_type, app_id)
        )
        db.commit()
        log_audit('edit_app', app_id, f'name={name}, build_type={build_type}')
        flash('应用信息已更新')
        return redirect(url_for('main.install', app_id=app_id))

    return render_template('edit.html', app=app_data)


@admin_bp.route('/backup')
@admin_required
def backup():
    db_path = current_app.config['DATABASE']
    if not os.path.exists(db_path):
        flash('数据库文件不存在')
        return redirect(url_for('main.index'))

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f'apps_backup_{timestamp}.db'

    return send_file(db_path, as_attachment=True, download_name=backup_filename)


@admin_bp.route('/delete/<int:app_id>', methods=['POST'])
@admin_required
def delete(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if app_data:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)

        if app_data['icon_filename']:
            icon_path = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['icon_filename'])
            if os.path.exists(icon_path):
                os.remove(icon_path)

        db.execute('DELETE FROM changelogs WHERE app_id = ?', (app_id,))
        db.execute('DELETE FROM download_logs WHERE app_id = ?', (app_id,))
        db.execute('DELETE FROM apps WHERE id = ?', (app_id,))
        db.commit()
        log_audit('delete_app', app_id, f'filename={app_data["filename"]}')
        flash('应用已删除')

    return redirect(url_for('main.index'))


@admin_bp.route('/cleanup-logs', methods=['POST'])
@admin_required
def cleanup_logs():
    days = request.form.get('days', 90, type=int)
    if days < 1:
        days = 90
    cleanup_old_logs(days)
    flash(f'已清理 {days} 天前的下载日志')
    return redirect(url_for('main.index'))


@admin_bp.route('/batch-delete', methods=['POST'])
@admin_required
def batch_delete():
    app_ids = request.form.getlist('app_ids[]')
    if not app_ids:
        flash('未选择任何应用')
        return redirect(url_for('main.index'))

    db = get_db()
    deleted_count = 0
    for app_id_str in app_ids:
        try:
            app_id = int(app_id_str)
        except ValueError:
            continue
        app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
        if app_data:
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            if app_data['icon_filename']:
                icon_path = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['icon_filename'])
                if os.path.exists(icon_path):
                    os.remove(icon_path)
            db.execute('DELETE FROM changelogs WHERE app_id = ?', (app_id,))
            db.execute('DELETE FROM download_logs WHERE app_id = ?', (app_id,))
            db.execute('DELETE FROM apps WHERE id = ?', (app_id,))
            log_audit('delete_app', app_id, f'filename={app_data["filename"]}')
            deleted_count += 1

    db.commit()
    flash(f'已删除 {deleted_count} 个应用')
    return redirect(url_for('main.index'))
