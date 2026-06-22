import os
from flask import redirect, url_for, flash, current_app
from app.routes import admin_bp
from app.models import get_db
from app.utils import admin_required


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
