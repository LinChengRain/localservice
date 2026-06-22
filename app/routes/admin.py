import os
import shutil
from datetime import datetime
from flask import redirect, url_for, flash, current_app, render_template, request, send_file
from app.routes import admin_bp
from app.models import get_db
from app.utils import admin_required


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

        db.execute('DELETE FROM apps WHERE id = ?', (app_id,))
        db.commit()
        flash('应用已删除')

    return redirect(url_for('main.index'))
