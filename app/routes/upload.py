import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from app.routes import upload_bp
from app.models import get_db
from app.utils import (admin_required, extract_icon_from_ipa, extract_icon_from_hap,
                       extract_icon_from_apk, parse_apk_metadata, parse_hap_metadata,
                       get_server_ip, is_lan_access, file_sha256)

ALLOWED_EXTENSIONS = {'ipa', 'hap', 'apk', 'png', 'jpg', 'jpeg'}

MAGIC_BYTES = {
    'ipa': b'PK',
    'hap': b'PK',
    'apk': b'PK',
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file_magic(file_obj, ext):
    if ext not in MAGIC_BYTES:
        return True
    header = file_obj.read(2)
    file_obj.seek(0)
    return header == MAGIC_BYTES[ext]


@upload_bp.route('/upload', methods=['GET', 'POST'])
@admin_required
def upload():
    if request.method == 'POST':
        if 'ipa_file' not in request.files:
            flash('没有选择文件')
            return redirect(request.url)

        file = request.files['ipa_file']
        if file.filename == '':
            flash('没有选择文件')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

            if ext in MAGIC_BYTES and not validate_file_magic(file, ext):
                flash('文件格式无效，请上传有效的 IPA、HAP 或 APK 文件')
                return redirect(request.url)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            file_size = os.path.getsize(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))

            if filename.lower().endswith('.hap'):
                platform = 'harmonyos'
            elif filename.lower().endswith('.apk'):
                platform = 'android'
            else:
                platform = 'ios'

            name = request.form.get('name', '')
            bundle_id = request.form.get('bundle_id', '')
            version = request.form.get('version', '1.0')
            build_type = request.form.get('build_type', 'testing')
            description = request.form.get('description', '')

            db = get_db()
            build_number = ''

            if platform == 'harmonyos':
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                hap_meta = parse_hap_metadata(file_path)
                if hap_meta:
                    if not name and hap_meta.get('name'):
                        name = hap_meta['name']
                    if not bundle_id and hap_meta.get('bundle_id'):
                        bundle_id = hap_meta['bundle_id']
                    if (not version or version == '1.0') and hap_meta.get('version'):
                        version = hap_meta['version']
            elif platform == 'android':
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                apk_meta = parse_apk_metadata(file_path)
                if apk_meta:
                    if not name and apk_meta.get('name'):
                        name = apk_meta['name']
                    if not bundle_id and apk_meta.get('bundle_id'):
                        bundle_id = apk_meta['bundle_id']
                    if (not version or version == '1.0') and apk_meta.get('version'):
                        version = apk_meta['version']

            if not build_number:
                existing = db.execute(
                    'SELECT build_number FROM apps WHERE bundle_id = ? AND version = ? ORDER BY CAST(build_number AS INTEGER) DESC LIMIT 1',
                    (bundle_id, version)
                ).fetchone()
                if existing and existing['build_number']:
                    try:
                        build_number = str(int(existing['build_number']) + 1)
                    except ValueError:
                        build_number = '1'
                else:
                    build_number = '1'

            icon_filename = None
            if 'icon_file' in request.files:
                icon_file = request.files['icon_file']
                if icon_file and allowed_file(icon_file.filename):
                    icon_filename = secure_filename(icon_file.filename)
                    icon_filename = timestamp + icon_filename
                    icon_file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], icon_filename))

            extracted_icon = request.form.get('extracted_icon', '')
            if not icon_filename and extracted_icon and extracted_icon.startswith('data:image'):
                try:
                    import base64
                    icon_data = base64.b64decode(extracted_icon.split(',')[1])
                    icon_filename = f"{timestamp}icon.png"
                    icon_path = os.path.join(current_app.config['UPLOAD_FOLDER'], icon_filename)
                    with open(icon_path, 'wb') as f:
                        f.write(icon_data)
                except (ValueError, IndexError):
                    pass

            if not icon_filename:
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                if platform == 'harmonyos':
                    icon_filename = extract_icon_from_hap(file_path, current_app.config['UPLOAD_FOLDER'], timestamp)
                elif platform == 'android':
                    icon_filename = extract_icon_from_apk(file_path, current_app.config['UPLOAD_FOLDER'], timestamp)
                else:
                    icon_filename = extract_icon_from_ipa(file_path, current_app.config['UPLOAD_FOLDER'], timestamp)

            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file_hash = file_sha256(file_path)

            db.execute(
                'INSERT INTO apps (name, bundle_id, version, filename, icon_filename, description, build_number, build_type, platform, upload_time, file_size, file_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (name, bundle_id, version, filename, icon_filename, description, build_number, build_type, platform, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), file_size, file_hash)
            )
            db.commit()

            changelog = request.form.get('changelog', '').strip()
            if changelog:
                app_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
                db.execute(
                    'INSERT INTO changelogs (app_id, version, content, created_at) VALUES (?, ?, ?, ?)',
                    (app_id, version, changelog, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
                db.commit()

            from app.routes.admin import log_audit
            app_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            log_audit('upload_app', app_id, f'bundle_id={bundle_id}, version={version}')

            flash('应用上传成功')
            return redirect(url_for('main.index'))

    return render_template('upload.html')
