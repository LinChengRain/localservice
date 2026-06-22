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

ALLOWED_EXTENSIONS = {'ipa', 'hap', 'apk', 'png', 'jpg', 'jpeg'}

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
    # Add index for faster queries
    db.execute('CREATE INDEX IF NOT EXISTS idx_apps_platform ON apps(platform)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_apps_bundle_id ON apps(bundle_id)')
    db.commit()
    db.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_icon_from_ipa(ipa_path, output_dir, timestamp):
    try:
        import zipfile
        
        with zipfile.ZipFile(ipa_path, 'r') as zip_ref:
            namelist = zip_ref.namelist()
            
            icon_patterns = (
                'AppIcon60x60@2x.png',
                'AppIcon60x60@3x.png',
                'AppIcon76x76@2x~ipad.png',
                'AppIcon-60@2x.png',
                'AppIcon.png',
                'icon.png'
            )
            
            # Single pass: categorize all icon candidates
            pattern_matches = {p: [] for p in icon_patterns}
            fallback_matches = []
            
            for name in namelist:
                if name.endswith('.png'):
                    matched = False
                    for pattern in icon_patterns:
                        if name.endswith(pattern):
                            pattern_matches[pattern].append(name)
                            matched = True
                            break
                    if not matched and 'AppIcon' in name:
                        fallback_matches.append(name)
            
            # Priority: specific patterns first
            for pattern in icon_patterns:
                if pattern_matches[pattern]:
                    icon_data = zip_ref.read(pattern_matches[pattern][0])
                    icon_filename = f"{timestamp}icon.png"
                    with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                        f.write(icon_data)
                    return icon_filename
            
            # Fallback: any AppIcon file
            for name in fallback_matches:
                try:
                    icon_data = zip_ref.read(name)
                    if len(icon_data) > 1000:
                        icon_filename = f"{timestamp}icon.png"
                        with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                            f.write(icon_data)
                        return icon_filename
                except:
                    continue
        
        return None
    except Exception as e:
        print(f"Error extracting icon: {e}")
        return None

_sha256_cache = {}

def file_sha256(filepath):
    """Calculate SHA256 hash of a file with caching"""
    if filepath in _sha256_cache:
        return _sha256_cache[filepath]
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    result = sha256.hexdigest()
    _sha256_cache[filepath] = result
    return result

def extract_icon_from_hap(hap_path, output_dir, timestamp):
    """Extract app icon from HAP file"""
    try:
        import zipfile
        
        with zipfile.ZipFile(hap_path, 'r') as z:
            # First try to find icon from module.json/module.json5 reference
            for name in z.namelist():
                if name in ('module.json', 'module.json5'):
                    try:
                        content = z.read(name).decode('utf-8')
                        if name.endswith('.json5'):
                            try:
                                import json5
                                data = json5.loads(content)
                            except ImportError:
                                import re
                                content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
                                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                                content = re.sub(r',\s*([\]}])', r'\1', content)
                                data = json.loads(content)
                        else:
                            data = json.loads(content)
                    except Exception:
                        continue
                    icon_ref = data.get('app', {}).get('icon', '') or data.get('module', {}).get('icon', '')
                    
                    if icon_ref.startswith('$media:'):
                        media_name = icon_ref.replace('$media:', '')
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

def extract_icon_from_apk(apk_path, output_dir, timestamp):
    """Extract app icon from APK file"""
    try:
        import zipfile

        # First try: get icon path from AndroidManifest via androguard
        try:
            from androguard.core.apk import APK
            a = APK(apk_path)
            manifest_icon = a.get_app_icon()
            if manifest_icon:
                with zipfile.ZipFile(apk_path, 'r') as z:
                    if manifest_icon in z.namelist():
                        icon_data = z.read(manifest_icon)
                        if len(icon_data) > 500:
                            icon_filename = f"{timestamp}icon.png"
                            with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                                f.write(icon_data)
                            return icon_filename
        except Exception:
            pass

        # Fallback: search by standard paths
        with zipfile.ZipFile(apk_path, 'r') as z:
            namelist = z.namelist()

            densities = ['xxxhdpi', 'xxhdpi', 'xhdpi', 'hdpi', 'mdpi']
            icon_names = ('ic_launcher.png', 'icon.png', 'app_icon.png')

            mipmap_matches = {}
            drawable_matches = []
            fallback_matches = []

            for name in namelist:
                if name.endswith('.png') and 'icon' in name.lower():
                    for density in densities:
                        if f'mipmap-{density}' in name:
                            for icon_name in icon_names:
                                if name.endswith(icon_name):
                                    mipmap_matches.setdefault(density, []).append(name)
                            break
                        elif f'drawable-{density}' in name:
                            drawable_matches.append(name)
                            break
                    else:
                        fallback_matches.append(name)

            for density in densities:
                if density in mipmap_matches:
                    icon_data = z.read(mipmap_matches[density][0])
                    if len(icon_data) > 1000:
                        icon_filename = f"{timestamp}icon.png"
                        with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                            f.write(icon_data)
                        return icon_filename

            for name in drawable_matches:
                icon_data = z.read(name)
                if len(icon_data) > 1000:
                    icon_filename = f"{timestamp}icon.png"
                    with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                        f.write(icon_data)
                    return icon_filename

            for name in fallback_matches:
                try:
                    icon_data = z.read(name)
                    if len(icon_data) > 1000:
                        icon_filename = f"{timestamp}icon.png"
                        with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                            f.write(icon_data)
                        return icon_filename
                except Exception:
                    continue

    except Exception as e:
        print(f"Error extracting APK icon: {e}")
    return None

def parse_apk_metadata(apk_path):
    """Parse APK metadata from AndroidManifest.xml"""
    try:
        from androguard.core.apk import APK

        a = APK(apk_path)
        return {
            'name': a.get_app_name() or '',
            'bundle_id': a.get_package() or '',
            'version': a.get_androidversion_name() or '',
            'build_number': str(a.get_androidversion_code() or ''),
        }
    except Exception as e:
        print(f"Error parsing APK metadata: {e}")
    return None

def _parse_resources_index(data):
    """Parse binary resources.index file to extract string resources"""
    results = {}
    i = 0
    while i < len(data) - 10:
        if data[i] == 0x05:
            if i + 2 < len(data):
                length = data[i+1] | (data[i+2] << 8)
                if 2 < length < 200:
                    val_start = i + 3
                    val_end = val_start + length - 1
                    if val_end < len(data) and data[val_end] == 0x00:
                        val_bytes = data[val_start:val_end]
                        try:
                            val = val_bytes.decode('utf-8')
                            key_start = val_end + 1
                            if key_start < len(data) and data[key_start] == 0x09:
                                key_start += 1
                                if key_start < len(data) and data[key_start] == 0x00:
                                    key_start += 1
                                    key_end = data.find(b'\x00', key_start)
                                    if key_end > key_start and key_end - key_start < 100:
                                        key = data[key_start:key_end].decode('utf-8')
                                        results[key] = val
                                        i = key_end
                        except Exception:
                            pass
        i += 1
    return results

def _resolve_hap_string_ref(z, ref):
    """Resolve $string:xxx reference from resources/index or string.json"""
    if not ref.startswith('$string:'):
        return ref
    key = ref[len('$string:'):]
    
    # First try JSON string resources
    string_paths = [
        'resources/base/element/string.json',
        'resources/base/element/en_US/element/string.json',
        'resources/base/element/zh_CN/element/string.json',
    ]
    for sp in string_paths:
        if sp in z.namelist():
            try:
                strings = json.loads(z.read(sp))
                for item in strings.get('string', []):
                    if item.get('name') == key:
                        return item.get('value', '')
            except Exception:
                continue
    
    # Fallback: parse binary resources.index
    if 'resources.index' in z.namelist():
        try:
            data = z.read('resources.index')
            strings = _parse_resources_index(data)
            if key in strings:
                return strings[key]
        except Exception:
            pass
    
    return ''

def parse_hap_metadata(hap_path):
    """Parse module.json/module.json5 and pack.info from HAP file to get metadata"""
    try:
        import zipfile
        
        with zipfile.ZipFile(hap_path, 'r') as z:
            pack_info = None
            module_data = None
            module_key = None
            
            # Collect file list for flexible lookup
            namelist = z.namelist()
            
            # Single pass to find both files, support both .json and .json5
            for name in namelist:
                if name == 'pack.info':
                    try:
                        pack_info = json.loads(z.read(name))
                    except Exception:
                        pass
                elif name in ('module.json', 'module.json5'):
                    try:
                        content = z.read(name).decode('utf-8')
                        if name.endswith('.json5'):
                            try:
                                import json5
                                module_data = json5.loads(content)
                            except ImportError:
                                import re
                                content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
                                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                                content = re.sub(r',\s*([\]}])', r'\1', content)
                                module_data = json.loads(content)
                        else:
                            module_data = json.loads(content)
                        module_key = name
                    except Exception:
                        pass
                if pack_info and module_data:
                    break
            
            if not module_data:
                return None
            
            app_info = module_data.get('app', {})
            
            # Build a string resolver from the HAP resources
            def resolve_ref(ref):
                if not ref or not isinstance(ref, str):
                    return ''
                if ref.startswith('$string:'):
                    return _resolve_hap_string_ref(z, ref)
                return ref
            
            # Get app name from multiple sources with priority
            name = ''
            label = app_info.get('label', '')
            resolved_label = resolve_ref(label)
            if resolved_label:
                name = resolved_label
            
            # Fallback: pack.info has the resolved label directly
            if not name and pack_info:
                pack_label = pack_info.get('summary', {}).get('app', {}).get('label', '')
                if pack_label:
                    name = pack_label
            
            # Fallback: bundleName
            if not name:
                name = app_info.get('bundleName', '')
            
            # Get bundle ID
            bundle_id = app_info.get('bundleName', '')
            
            # Get version
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

_cached_lan_ip = None

def get_server_ip():
    if 'SERVER_IP' in app.config:
        return app.config['SERVER_IP']
    return get_lan_ip()

def get_lan_ip():
    global _cached_lan_ip
    if _cached_lan_ip:
        return _cached_lan_ip
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        _cached_lan_ip = s.getsockname()[0]
    except:
        _cached_lan_ip = '127.0.0.1'
    finally:
        s.close()
    return _cached_lan_ip

def detect_platform():
    """Detect device platform from User-Agent"""
    ua = request.headers.get('User-Agent', '').lower()
    if 'iphone' in ua or 'ipad' in ua:
        return 'ios'
    elif 'harmony' in ua or 'hmos' in ua:
        return 'harmonyos'
    elif 'android' in ua:
        return 'android'
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
    elif filter_platform and filter_platform in ('ios', 'harmonyos', 'android'):
        apps = db.execute('SELECT * FROM apps WHERE platform = ? ORDER BY upload_time DESC', (filter_platform,)).fetchall()
    else:
        apps = db.execute('SELECT * FROM apps ORDER BY upload_time DESC').fetchall()
    
    # Group apps by bundle_id + platform
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

            # Auto-increment build_number for same bundle_id + version
            db = get_db()
            build_number = ''
            
            # For HAP/APK files, try to get metadata from file
            if platform == 'harmonyos':
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                hap_meta = parse_hap_metadata(file_path)
                if hap_meta:
                    if not name and hap_meta.get('name'):
                        name = hap_meta['name']
                    if not bundle_id and hap_meta.get('bundle_id'):
                        bundle_id = hap_meta['bundle_id']
                    if (not version or version == '1.0') and hap_meta.get('version'):
                        version = hap_meta['version']
                    if hap_meta.get('build_number'):
                        build_number = hap_meta['build_number']
            elif platform == 'android':
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                apk_meta = parse_apk_metadata(file_path)
                if apk_meta:
                    if not name and apk_meta.get('name'):
                        name = apk_meta['name']
                    if not bundle_id and apk_meta.get('bundle_id'):
                        bundle_id = apk_meta['bundle_id']
                    if (not version or version == '1.0') and apk_meta.get('version'):
                        version = apk_meta['version']
                    if apk_meta.get('build_number'):
                        build_number = apk_meta['build_number']
            
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
                elif platform == 'android':
                    icon_filename = extract_icon_from_apk(file_path, app.config['UPLOAD_FOLDER'], timestamp)
                else:
                    icon_filename = extract_icon_from_ipa(file_path, app.config['UPLOAD_FOLDER'], timestamp)
            
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

@app.route('/api/parse-apk', methods=['POST'])
def parse_apk():
    """Parse APK file metadata"""
    if 'ipa_file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['ipa_file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    if not file.filename.lower().endswith('.apk'):
        return jsonify({'error': '不是APK文件'}), 400

    try:
        import tempfile
        import base64
        import zipfile

        with tempfile.NamedTemporaryFile(suffix='.apk', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        result = None
        icon_data = None

        # Parse metadata and icon in one pass using single APK instance
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

        # Fallback: metadata from zip
        if not result:
            result = parse_apk_metadata(tmp_path)

        # Fallback: icon by standard paths
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
