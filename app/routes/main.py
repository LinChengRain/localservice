from flask import render_template, request, redirect, url_for, send_from_directory, jsonify, flash, current_app
from flask_login import login_required, current_user
from app.routes import main_bp
from app.models import get_db
from app.utils import get_server_ip, get_lan_ip, is_lan_access, detect_platform, file_sha256
import os
import json
import plistlib


@main_bp.route('/')
def index():
    platform = detect_platform()
    filter_platform = request.args.get('platform', '')
    search_query = request.args.get('q', '').strip()

    db = get_db()
    query = 'SELECT * FROM apps'
    params = []
    conditions = []

    if platform != 'all':
        conditions.append('platform = ?')
        params.append(platform)
    elif filter_platform and filter_platform in ('ios', 'harmonyos', 'android'):
        conditions.append('platform = ?')
        params.append(filter_platform)

    if search_query:
        conditions.append('(name LIKE ? OR bundle_id LIKE ? OR description LIKE ?)')
        search_pattern = f'%{search_query}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    count_query = 'SELECT COUNT(*) as cnt FROM apps'
    if conditions:
        count_query += ' WHERE ' + ' AND '.join(conditions)
    total = db.execute(count_query, params).fetchone()['cnt']
    total_pages = (total + per_page - 1) // per_page

    query += ' ORDER BY upload_time DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    apps = db.execute(query, params).fetchall()

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

    for group in grouped.values():
        sorted_versions = {}
        for ver in sorted(group['versions'].keys(),
                         key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')],
                         reverse=True):
            sorted_versions[ver] = sorted(group['versions'][ver],
                                         key=lambda x: x['upload_time'] or '',
                                         reverse=True)
        group['versions'] = sorted_versions

    server_ip = get_server_ip()
    lan_ip = get_lan_ip()
    is_lan = is_lan_access(request.host)

    stats = None
    if is_lan:
        total_apps = db.execute('SELECT COUNT(DISTINCT bundle_id || "_" || platform) as cnt FROM apps').fetchone()['cnt']
        total_downloads = db.execute('SELECT COUNT(*) as cnt FROM download_logs').fetchone()['cnt']
        stats = {'total_apps': total_apps, 'total_downloads': total_downloads}

    return render_template('index.html', apps=apps, grouped_apps=grouped.values(),
                         server_ip=server_ip, is_lan=is_lan,
                         client_platform=platform,
                         page=page, total_pages=total_pages,
                         search_query=search_query, stats=stats)


@main_bp.route('/install/<int:app_id>')
def install(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if not app_data:
        flash('应用不存在')
        return redirect(url_for('main.index'))

    changelogs = db.execute(
        'SELECT * FROM changelogs WHERE app_id = ? ORDER BY created_at DESC',
        (app_id,)
    ).fetchall()

    download_count = db.execute(
        'SELECT COUNT(*) as cnt FROM download_logs WHERE app_id = ?',
        (app_id,)
    ).fetchone()['cnt']

    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host

    return render_template('install.html', app=app_data, server_ip=server_ip,
                         changelogs=changelogs, download_count=download_count)


@main_bp.route('/manifest/<int:app_id>')
def manifest(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if not app_data:
        return 'App not found', 404

    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host

    manifest_data = {
        'items': [{
            'assets': [
                {
                    'kind': 'software-package',
                    'url': f'https://{server_ip}/download/{app_data["filename"]}'
                },
                {
                    'kind': 'display-image',
                    'url': f'https://{server_ip}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else f'https://{server_ip}/static/icon.png'
                },
                {
                    'kind': 'full-size-image',
                    'url': f'https://{server_ip}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else f'https://{server_ip}/static/icon.png'
                }
            ],
            'metadata': {
                'bundle-identifier': app_data['bundle_id'],
                'bundle-version': app_data['version'],
                'kind': 'software',
                'title': app_data['name']
            }
        }]
    }

    plist_xml = plistlib.dumps(manifest_data, sort_keys=True)

    response = current_app.response_class(
        response=plist_xml,
        status=200,
        mimetype='application/xml'
    )
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@main_bp.route('/manifest-harmony/<int:app_id>')
def manifest_harmony(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if not app_data:
        return 'App not found', 404

    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host

    deploy_domain = f'https://{server_ip}'
    hap_path = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['filename'])

    manifest_data = {
        'app': {
            'bundleName': app_data['bundle_id'],
            'bundleType': 'app',
            'versionCode': int(app_data['build_number']) if app_data['build_number'] else 1,
            'versionName': app_data['version'],
            'label': app_data['name'],
            'deployDomain': deploy_domain,
            'icons': {
                'normal': f'{deploy_domain}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else '',
                'large': f'{deploy_domain}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else '',
            },
            'minAPIVersion': '4.1.0(11)',
            'targetAPIVersion': '4.1.0(11)',
            'modules': [{
                'name': 'entry',
                'type': 'entry',
                'deviceTypes': ['phone', 'tablet'],
                'packageUrl': f'{deploy_domain}/download/{app_data["filename"]}',
                'packageHash': file_sha256(hap_path) if os.path.exists(hap_path) else '',
            }]
        }
    }

    response = current_app.response_class(
        response=json.dumps(manifest_data, indent=2, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@main_bp.route('/manifest-harmony/<int:app_id>.json5')
def manifest_harmony_json5(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()

    if not app_data:
        return 'App not found', 404

    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host

    deploy_domain = f'https://{server_ip}'
    hap_path = os.path.join(current_app.config['UPLOAD_FOLDER'], app_data['filename'])

    manifest_data = {
        'app': {
            'bundleName': app_data['bundle_id'],
            'bundleType': 'app',
            'versionCode': int(app_data['build_number']) if app_data['build_number'] else 1,
            'versionName': app_data['version'],
            'label': app_data['name'],
            'deployDomain': server_ip,
            'icons': {
                'normal': f'{deploy_domain}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else '',
                'large': f'{deploy_domain}/download/{app_data["icon_filename"]}' if app_data['icon_filename'] else '',
            },
            'minAPIVersion': '5.0.0(12)',
            'targetAPIVersion': '5.0.0(12)',
            'modules': [{
                'name': 'entry',
                'type': 'entry',
                'deviceTypes': ['phone'],
                'packageUrl': f'{deploy_domain}/download/{app_data["filename"]}',
                'packageHash': file_sha256(hap_path) if os.path.exists(hap_path) else '',
            }]
        }
    }

    response = current_app.response_class(
        response=json.dumps(manifest_data, indent=2, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@main_bp.route('/download/<filename>')
def download(filename):
    is_icon = filename.lower().endswith(('.png', '.jpg', '.jpeg'))

    if not is_icon:
        host = request.host
        if is_lan_access(host) and current_app.config.get('LAN_REQUIRE_LOGIN', False):
            if not current_user.is_authenticated:
                flash('请先登录')
                return redirect(url_for('auth.login'))

    db = get_db()
    app_data = db.execute('SELECT id FROM apps WHERE filename = ?', (filename,)).fetchone()
    if app_data:
        db.execute('INSERT INTO download_logs (app_id, ip_address, user_agent) VALUES (?, ?, ?)',
                   (app_data['id'], request.remote_addr, request.headers.get('User-Agent', '')))
        db.commit()
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=not is_icon)


@main_bp.route('/cert')
def download_cert():
    cert_path = os.path.join(current_app.config['CERT_FOLDER'], 'local.crt')
    if os.path.exists(cert_path):
        return send_from_directory(current_app.config['CERT_FOLDER'], 'local.crt', as_attachment=True)
    return 'Certificate not found', 404


@main_bp.route('/health')
def health():
    try:
        db = get_db()
        db.execute('SELECT 1')
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'database': str(e)}), 500
