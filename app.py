import os
import sqlite3
import subprocess
import json
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, flash
from werkzeug.utils import secure_filename
import plistlib

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['CERT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs')
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

ALLOWED_EXTENSIONS = {'ipa', 'hap', 'png', 'jpg', 'jpeg'}

def get_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            bundle_id TEXT NOT NULL,
            version TEXT NOT NULL,
            filename TEXT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            icon_filename TEXT,
            description TEXT,
            build_number TEXT DEFAULT '',
            build_type TEXT DEFAULT 'release',
            platform TEXT DEFAULT 'ios'
        )
    ''')
    # Add columns if missing (migration for existing DB)
    for col, default in [("build_number", "''"), ("build_type", "'release'"), ("platform", "'ios'")]:
        try:
            db.execute(f"ALTER TABLE apps ADD COLUMN {col} TEXT DEFAULT {default}")
        except:
            pass
    db.commit()
    db.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_icon_from_ipa(ipa_path, output_dir, timestamp):
    try:
        import zipfile
        
        with zipfile.ZipFile(ipa_path, 'r') as zip_ref:
            # Look for common app icon patterns
            icon_patterns = [
                'AppIcon60x60@2x.png',
                'AppIcon60x60@3x.png',
                'AppIcon76x76@2x~ipad.png',
                'AppIcon-60@2x.png',
                'AppIcon.png',
                'icon.png'
            ]
            
            # First try specific patterns
            for pattern in icon_patterns:
                for name in zip_ref.namelist():
                    if name.endswith(pattern):
                        icon_data = zip_ref.read(name)
                        icon_filename = f"{timestamp}icon.png"
                        icon_path = os.path.join(output_dir, icon_filename)
                        with open(icon_path, 'wb') as f:
                            f.write(icon_data)
                        return icon_filename
            
            # Fallback: search for any AppIcon file
            for name in zip_ref.namelist():
                if 'AppIcon' in name and name.endswith('.png'):
                    try:
                        icon_data = zip_ref.read(name)
                        if len(icon_data) > 1000:  # Skip tiny files
                            icon_filename = f"{timestamp}icon.png"
                            icon_path = os.path.join(output_dir, icon_filename)
                            with open(icon_path, 'wb') as f:
                                f.write(icon_data)
                            return icon_filename
                    except:
                        continue
        
        return None
    except Exception as e:
        print(f"Error extracting icon: {e}")
        return None

def file_sha256(filepath):
    """Calculate SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def extract_icon_from_hap(hap_path, output_dir, timestamp):
    """Extract app icon from HAP file"""
    try:
        import zipfile
        
        with zipfile.ZipFile(hap_path, 'r') as z:
            # First try to find icon from module.json reference
            for name in z.namelist():
                if name == 'module.json':
                    data = json.loads(z.read(name))
                    icon_ref = data.get('app', {}).get('icon', '') or data.get('module', {}).get('icon', '')
                    
                    if icon_ref.startswith('$media:'):
                        # Resolve media reference - look for the file directly
                        media_name = icon_ref.replace('$media:', '')
                        # Try common locations
                        for path in [
                            f'resources/base/media/{media_name}.png',
                            f'resources/base/media/{media_name}.jpg',
                            f'resources/base/media/{media_name}.webp',
                        ]:
                            if path in z.namelist():
                                icon_data = z.read(path)
                                if len(icon_data) > 1000:
                                    icon_filename = f"{timestamp}icon.png"
                                    icon_path = os.path.join(output_dir, icon_filename)
                                    with open(icon_path, 'wb') as f:
                                        f.write(icon_data)
                                    return icon_filename
                    break
            
            # Fallback: look for app_icon.png or icon.png in common locations
            fallback_paths = [
                'resources/base/media/app_icon.png',
                'resources/base/media/icon.png',
            ]
            for path in fallback_paths:
                if path in z.namelist():
                    icon_data = z.read(path)
                    if len(icon_data) > 1000:
                        icon_filename = f"{timestamp}icon.png"
                        icon_path = os.path.join(output_dir, icon_filename)
                        with open(icon_path, 'wb') as f:
                            f.write(icon_data)
                        return icon_filename
            
            # Last fallback: search for any icon file in media directory
            for name in z.namelist():
                if 'media' in name and name.endswith(('.png', '.jpg', '.webp')):
                    if 'icon' in name.lower() or 'app' in name.lower():
                        icon_data = z.read(name)
                        if len(icon_data) > 1000:
                            icon_filename = f"{timestamp}icon.png"
                            icon_path = os.path.join(output_dir, icon_filename)
                            with open(icon_path, 'wb') as f:
                                f.write(icon_data)
                            return icon_filename
    except Exception as e:
        print(f"Error extracting HAP icon: {e}")
    return None

def parse_hap_metadata(hap_path):
    """Parse module.json and pack.info from HAP file to get metadata"""
    try:
        import zipfile
        
        with zipfile.ZipFile(hap_path, 'r') as z:
            # Read pack.info for versionCode (more reliable source)
            pack_info = None
            for name in z.namelist():
                if name == 'pack.info':
                    pack_info = json.loads(z.read(name))
                    break
            
            # Read module.json for other metadata
            module_data = None
            for name in z.namelist():
                if name == 'module.json':
                    module_data = json.loads(z.read(name))
                    break
            
            if not module_data:
                return None
            
            app_info = module_data.get('app', {})
            
            # Get app name - prefer non-localization reference
            name = ''
            label = app_info.get('label', '')
            if label and not label.startswith('$string:'):
                name = label
            if not name:
                name = app_info.get('bundleName', '')
            
            # Get bundle ID
            bundle_id = app_info.get('bundleName', '')
            
            # Get version - prefer pack.info for versionCode
            version = app_info.get('versionName', '')
            build_number = ''
            
            if pack_info:
                summary_app = pack_info.get('summary', {}).get('app', {})
                version_info = summary_app.get('version', {})
                build_number = str(version_info.get('code', ''))
            
            if not build_number:
                build_number = str(app_info.get('versionCode', ''))
            
            # Get icon reference
            icon_ref = app_info.get('icon', '')
            
            return {
                'name': name,
                'bundle_id': bundle_id,
                'version': version,
                'build_number': build_number,
                'icon_ref': icon_ref,
            }
    except Exception as e:
        print(f"Error parsing HAP metadata: {e}")
    return None

def generate_certificates(cn):
    cert_path = os.path.join(app.config['CERT_FOLDER'], 'local.crt')
    key_path = os.path.join(app.config['CERT_FOLDER'], 'local.key')
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path
    
    os.makedirs(app.config['CERT_FOLDER'], exist_ok=True)
    
    cmd = [
        'openssl', 'req', '-x509', '-nodes', '-days', '3650',
        '-newkey', 'rsa:2048',
        '-keyout', key_path,
        '-out', cert_path,
        '-subj', f'/CN={cn}'
    ]
    
    subprocess.run(cmd, check=True)
    return cert_path, key_path

def get_server_ip():
    # 优先使用配置中的服务器地址
    if 'SERVER_IP' in app.config:
        return app.config['SERVER_IP']
    
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def detect_platform():
    """Detect device platform from User-Agent"""
    ua = request.headers.get('User-Agent', '').lower()
    if 'iphone' in ua or 'ipad' in ua:
        return 'ios'
    elif 'harmony' in ua or 'hmos' in ua:
        return 'harmonyos'
    return 'all'

@app.context_processor
def inject_globals():
    server_ip = get_server_ip()
    lan_ip = get_lan_ip()
    is_lan = request.host and (request.host.startswith('127.') or request.host.startswith(lan_ip) or request.host == 'localhost')
    client_platform = detect_platform()
    
    # Use request host for URL generation to support cloudflared/ngrok
    host = request.host
    if host and not host.startswith('127.') and not host.startswith('localhost'):
        server_ip = host
    
    return {
        'server_ip': server_ip,
        'lan_ip': lan_ip,
        'is_lan': is_lan,
        'lan_url': f'http://{lan_ip}:8080',
        'client_platform': client_platform,
    }

@app.route('/')
def index():
    platform = detect_platform()
    filter_platform = request.args.get('platform', '')
    
    db = get_db()
    # Filter by platform if on mobile, or if filter is specified
    if platform != 'all':
        apps = db.execute('SELECT * FROM apps WHERE platform = ? ORDER BY upload_time DESC', (platform,)).fetchall()
    elif filter_platform and filter_platform in ('ios', 'harmonyos'):
        apps = db.execute('SELECT * FROM apps WHERE platform = ? ORDER BY upload_time DESC', (filter_platform,)).fetchall()
    else:
        apps = db.execute('SELECT * FROM apps ORDER BY upload_time DESC').fetchall()
    
    # Group apps by bundle_id
    grouped = {}
    for app in apps:
        bid = app['bundle_id']
        if bid not in grouped:
            grouped[bid] = {
                'bundle_id': bid,
                'name': app['name'],
                'icon_filename': app['icon_filename'],
                'platform': app['platform'],
                'versions': {}
            }
        
        ver = app['version']
        if ver not in grouped[bid]['versions']:
            grouped[bid]['versions'][ver] = []
        
        grouped[bid]['versions'][ver].append(dict(app))
    
    db.close()
    server_ip = get_server_ip()
    return render_template('index.html', apps=apps, grouped_apps=grouped.values(), server_ip=server_ip)

@app.route('/upload', methods=['GET', 'POST'])
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
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Detect platform from file extension
            platform = 'harmonyos' if filename.lower().endswith('.hap') else 'ios'
            
            name = request.form.get('name', '')
            bundle_id = request.form.get('bundle_id', '')
            version = request.form.get('version', '1.0')
            build_type = request.form.get('build_type', 'testing')
            description = request.form.get('description', '')

            # Auto-increment build_number for same bundle_id + version
            db = get_db()
            
            # For HAP files, try to get versionCode from pack.info
            if platform == 'harmonyos':
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                hap_meta = parse_hap_metadata(file_path)
                if hap_meta and hap_meta.get('build_number'):
                    build_number = hap_meta['build_number']
                else:
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
            else:
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
            db.close()
            
            icon_filename = None
            if 'icon_file' in request.files:
                icon_file = request.files['icon_file']
                if icon_file and allowed_file(icon_file.filename):
                    icon_filename = secure_filename(icon_file.filename)
                    icon_filename = timestamp + icon_filename
                    icon_file.save(os.path.join(app.config['UPLOAD_FOLDER'], icon_filename))
            
            # Handle base64 icon from frontend
            extracted_icon = request.form.get('extracted_icon', '')
            if not icon_filename and extracted_icon and extracted_icon.startswith('data:image'):
                try:
                    import base64
                    icon_data = base64.b64decode(extracted_icon.split(',')[1])
                    icon_filename = f"{timestamp}icon.png"
                    icon_path = os.path.join(app.config['UPLOAD_FOLDER'], icon_filename)
                    with open(icon_path, 'wb') as f:
                        f.write(icon_data)
                except:
                    pass
            
            # If no icon, try to extract from file
            if not icon_filename:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if platform == 'harmonyos':
                    icon_filename = extract_icon_from_hap(file_path, app.config['UPLOAD_FOLDER'], timestamp)
                else:
                    icon_filename = extract_icon_from_ipa(file_path, app.config['UPLOAD_FOLDER'], timestamp)
            
            db = get_db()
            db.execute(
                'INSERT INTO apps (name, bundle_id, version, filename, icon_filename, description, build_number, build_type, platform) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (name, bundle_id, version, filename, icon_filename, description, build_number, build_type, platform)
            )
            db.commit()
            db.close()
            
            flash('应用上传成功')
            return redirect(url_for('index'))
    
    return render_template('upload.html')

@app.route('/delete/<int:app_id>', methods=['POST'])
def delete(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
    
    if app_data:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], app_data['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        
        if app_data['icon_filename']:
            icon_path = os.path.join(app.config['UPLOAD_FOLDER'], app_data['icon_filename'])
            if os.path.exists(icon_path):
                os.remove(icon_path)
        
        db.execute('DELETE FROM apps WHERE id = ?', (app_id,))
        db.commit()
        flash('应用已删除')
    
    db.close()
    return redirect(url_for('index'))

@app.route('/install/<int:app_id>')
def install(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
    db.close()
    
    if not app_data:
        flash('应用不存在')
        return redirect(url_for('index'))
    
    # Use request host for URL generation to support cloudflared/ngrok
    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host
    
    return render_template('install.html', app=app_data, server_ip=server_ip)

@app.route('/manifest/<int:app_id>')
def manifest(app_id):
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
    db.close()
    
    if not app_data:
        return 'App not found', 404
    
    # Use request host for URL generation to support cloudflared/ngrok
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
    
    import io
    plist_xml = plistlib.dumps(manifest_data, sort_keys=True)
    
    response = app.response_class(
        response=plist_xml,
        status=200,
        mimetype='application/xml'
    )
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/manifest-harmony/<int:app_id>')
def manifest_harmony(app_id):
    """Generate HarmonyOS enterprise distribution manifest JSON5"""
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
    db.close()
    
    if not app_data:
        return 'App not found', 404
    
    # Use request host for URL generation to support cloudflared/ngrok
    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host
    
    deploy_domain = f'https://{server_ip}'
    hap_path = os.path.join(app.config['UPLOAD_FOLDER'], app_data['filename'])
    
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
    
    response = app.response_class(
        response=json.dumps(manifest_data, indent=2, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@app.route('/manifest-harmony/<int:app_id>.json5')
def manifest_harmony_json5(app_id):
    """Serve HarmonyOS manifest as .json5 file"""
    db = get_db()
    app_data = db.execute('SELECT * FROM apps WHERE id = ?', (app_id,)).fetchone()
    db.close()
    
    if not app_data:
        return 'App not found', 404
    
    # Use request host for URL generation to support cloudflared/ngrok
    host = request.host
    if host.startswith('127.') or host.startswith('localhost'):
        server_ip = get_server_ip()
    else:
        server_ip = host
    
    deploy_domain = f'https://{server_ip}'
    hap_path = os.path.join(app.config['UPLOAD_FOLDER'], app_data['filename'])
    
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
    
    response = app.response_class(
        response=json.dumps(manifest_data, indent=2, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/cert')
def download_cert():
    cert_path = os.path.join(app.config['CERT_FOLDER'], 'local.crt')
    if os.path.exists(cert_path):
        return send_from_directory(app.config['CERT_FOLDER'], 'local.crt', as_attachment=True)
    return 'Certificate not found', 404

@app.route('/api/apps')
def api_apps():
    db = get_db()
    apps = db.execute('SELECT * FROM apps ORDER BY upload_time DESC').fetchall()
    db.close()
    return jsonify([dict(app) for app in apps])

@app.route('/api/apps/grouped')
def api_apps_grouped():
    db = get_db()
    apps = db.execute('''
        SELECT * FROM apps 
        ORDER BY bundle_id, version DESC, upload_time DESC
    ''').fetchall()
    db.close()
    
    grouped = {}
    for app in apps:
        bid = app['bundle_id']
        if bid not in grouped:
            grouped[bid] = {
                'bundle_id': bid,
                'name': app['name'],
                'icon_filename': app['icon_filename'],
                'platform': app['platform'],
                'versions': {}
            }
        
        ver = app['version']
        if ver not in grouped[bid]['versions']:
            grouped[bid]['versions'][ver] = []
        
        grouped[bid]['versions'][ver].append(dict(app))
    
    return jsonify(list(grouped.values()))

@app.route('/api/parse-ipa', methods=['POST'])
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
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.ipa', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        result = {'name': '', 'bundle_id': '', 'version': ''}
        
        with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
            # Find all Info.plist files
            plist_files = [f for f in zip_ref.namelist() if f.endswith('Info.plist')]
            
            # Priority: main app plist first, then others
            main_plist = None
            for pf in plist_files:
                # Main app plist is usually at Payload/XXX.app/Info.plist
                if pf.count('/') == 2 and pf.endswith('.app/Info.plist'):
                    main_plist = pf
                    break
            
            # Fallback: try the first plist that has CFBundleIdentifier
            if not main_plist:
                for pf in plist_files:
                    try:
                        plist_data = zip_ref.read(pf)
                        plist = plistlib.loads(plist_data)
                        if plist.get('CFBundleIdentifier'):
                            main_plist = pf
                            break
                    except:
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

@app.route('/api/parse-hap', methods=['POST'])
def parse_hap():
    """Parse HAP file metadata"""
    if 'ipa_file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    
    file = request.files['ipa_file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    
    if not file.filename.lower().endswith('.hap'):
        return jsonify({'error': '不是HAP文件'}), 400
    
    try:
        import tempfile
        
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

if __name__ == '__main__':
    import argparse
    import threading

    parser = argparse.ArgumentParser(description='应用分发服务')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8443, help='HTTPS端口')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP端口（用于ngrok）')
    parser.add_argument('--server', default=None, help='公网服务器地址（用于ngrok等场景）')
    parser.add_argument('--ngrok', action='store_true', help='ngrok模式：只启动HTTP，不启动HTTPS')
    args = parser.parse_args()

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CERT_FOLDER'], exist_ok=True)
    init_db()

    server_ip = args.server if args.server else get_server_ip()
    app.config['SERVER_IP'] = server_ip

    if args.ngrok:
        print(f"应用分发服务启动中（ngrok模式）...")
        print(f"HTTP地址: http://{args.host}:{args.http_port}")
        print(f"公网地址: https://{server_ip}")
        print(f"管理界面: https://{server_ip}/")
        print(f"证书下载: https://{server_ip}/cert")
        print("")
        print("启动方式：")
        print(f"  1. 先启动本服务: python3 app.py --ngrok --server <ngrok地址>")
        print(f"  2. 再启动cloudflared: cloudflared tunnel --url http://localhost:{args.http_port}")
        app.run(host=args.host, port=args.http_port)
    else:
        cert_cn = server_ip.split(':')[0] if ':' in server_ip else server_ip
        cert_path, key_path = generate_certificates(cert_cn)

        print(f"应用分发服务启动中...")
        print(f"服务器地址: https://{server_ip}:{args.port}")
        print(f"管理界面: https://{server_ip}:{args.port}/")
        print(f"证书下载: https://{server_ip}:{args.port}/cert")
        print(f"证书文件: {cert_path}")
        print("")
        print("提示: 使用 --ngrok --server 启动ngrok模式")
        app.run(host=args.host, port=args.port, ssl_context=(cert_path, key_path))
