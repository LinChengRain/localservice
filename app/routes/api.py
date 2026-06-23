import os
import json
import tempfile
from functools import wraps
from flask import request, jsonify, current_app
from app.routes import api_bp
from app.models import get_db
from app.utils import parse_apk_metadata, parse_hap_metadata, extract_icon_from_apk


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = current_app.config.get('API_KEY', '')
        if api_key:
            provided_key = request.headers.get('X-API-Key', '')
            if provided_key != api_key:
                return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated


@api_bp.route('/apps')
@require_api_key
def api_apps():
    db = get_db()
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', 20, type=int)

    if page is not None:
        offset = (page - 1) * per_page
        total = db.execute('SELECT COUNT(*) as cnt FROM apps').fetchone()['cnt']
        apps = db.execute('SELECT * FROM apps ORDER BY upload_time DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
        return jsonify({
            'items': [dict(app) for app in apps],
            'total': total,
            'page': page,
            'per_page': per_page
        })
    else:
        apps = db.execute('SELECT * FROM apps ORDER BY upload_time DESC').fetchall()
        return jsonify([dict(app) for app in apps])


@api_bp.route('/apps/grouped')
@require_api_key
def api_apps_grouped():
    db = get_db()
    apps = db.execute('''
        SELECT * FROM apps
        ORDER BY bundle_id, version DESC, upload_time DESC
    ''').fetchall()

    grouped = {}
    for app in apps:
        bid = app['bundle_id']
        group_key = f"{bid}_{app['platform']}"
        if group_key not in grouped:
            grouped[group_key] = {
                'bundle_id': bid,
                'name': app['name'],
                'icon_filename': app['icon_filename'],
                'platform': app['platform'],
                'versions': {}
            }

        ver = app['version']
        if ver not in grouped[group_key]['versions']:
            grouped[group_key]['versions'][ver] = []

        grouped[group_key]['versions'][ver].append(dict(app))

    return jsonify(list(grouped.values()))


@api_bp.route('/parse-ipa', methods=['POST'])
@require_api_key
def parse_ipa():
    if 'ipa_file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['ipa_file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    if not file.filename.lower().endswith('.ipa'):
        return jsonify({'error': '不是IPA文件'}), 400

    try:
        import zipfile
        import plistlib

        with tempfile.NamedTemporaryFile(suffix='.ipa', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        result = {'name': '', 'bundle_id': '', 'version': ''}

        with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
            plist_files = [f for f in zip_ref.namelist() if f.endswith('Info.plist')]

            main_plist = None
            for pf in plist_files:
                if pf.count('/') == 2 and pf.endswith('.app/Info.plist'):
                    main_plist = pf
                    break

            if not main_plist:
                for pf in plist_files:
                    try:
                        plist_data = zip_ref.read(pf)
                        plist = plistlib.loads(plist_data)
                        if plist.get('CFBundleIdentifier'):
                            main_plist = pf
                            break
                    except (ValueError, KeyError):
                        continue

            if main_plist:
                plist_data = zip_ref.read(main_plist)
                plist = plistlib.loads(plist_data)

                result['name'] = plist.get('CFBundleDisplayName', '') or plist.get('CFBundleName', '')
                result['bundle_id'] = plist.get('CFBundleIdentifier', '')
                result['version'] = plist.get('CFBundleShortVersionString', '') or plist.get('CFBundleVersion', '')
                result['build_number'] = plist.get('CFBundleVersion', '')

        os.unlink(tmp_path)
        return jsonify(result)

    except Exception as e:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/parse-hap', methods=['POST'])
@require_api_key
def parse_hap():
    if 'ipa_file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['ipa_file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    if not file.filename.lower().endswith('.hap'):
        return jsonify({'error': '不是HAP文件'}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix='.hap', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        result = parse_hap_metadata(tmp_path)
        os.unlink(tmp_path)

        if result:
            return jsonify(result)
        else:
            return jsonify({'error': '无法解析HAP文件'}), 400

    except Exception as e:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/parse-apk', methods=['POST'])
@require_api_key
def parse_apk():
    if 'ipa_file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['ipa_file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    if not file.filename.lower().endswith('.apk'):
        return jsonify({'error': '不是APK文件'}), 400

    try:
        import base64
        import zipfile

        with tempfile.NamedTemporaryFile(suffix='.apk', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        result = None
        icon_data = None

        try:
            from androguard.core.apk import APK
            a = APK(tmp_path)
            result = {
                'name': a.get_app_name() or '',
                'bundle_id': a.get_package() or '',
                'version': a.get_androidversion_name() or '',
                'build_number': str(a.get_androidversion_code() or ''),
            }
            manifest_icon = a.get_app_icon()
            if manifest_icon:
                with zipfile.ZipFile(tmp_path, 'r') as z:
                    if manifest_icon in z.namelist():
                        icon_data = z.read(manifest_icon)
        except Exception:
            pass

        if not result:
            result = parse_apk_metadata(tmp_path)

        if not icon_data or len(icon_data) <= 500:
            icon_data = None
            with zipfile.ZipFile(tmp_path, 'r') as z:
                namelist = z.namelist()
                densities = ['xxxhdpi', 'xxhdpi', 'xhdpi', 'hdpi', 'mdpi']
                icon_names = ('ic_launcher.png', 'icon.png', 'app_icon.png')

                for name in namelist:
                    if name.endswith('.png') and 'icon' in name.lower():
                        for density in densities:
                            if f'mipmap-{density}' in name:
                                for icon_name in icon_names:
                                    if name.endswith(icon_name):
                                        icon_data = z.read(name)
                                        break
                                if icon_data:
                                    break
                        if icon_data:
                            break

                if not icon_data:
                    for name in namelist:
                        if name.endswith('.png') and 'icon' in name.lower():
                            try:
                                data = z.read(name)
                                if len(data) > 1000:
                                    icon_data = data
                                    break
                            except Exception:
                                continue

        if icon_data and len(icon_data) > 500:
            result['icon'] = 'data:image/png;base64,' + base64.b64encode(icon_data).decode('utf-8')

        os.unlink(tmp_path)

        if result:
            return jsonify(result)
        else:
            return jsonify({'error': '无法解析APK文件'}), 400

    except Exception as e:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({'error': str(e)}), 500
