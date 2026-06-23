import os
import socket
import hashlib
import plistlib
import zipfile
import json
import re
from functools import wraps
from flask import request, redirect, url_for, flash, current_app
from flask_login import current_user


_cached_lan_ip = None


def get_lan_ip():
    global _cached_lan_ip
    if _cached_lan_ip:
        return _cached_lan_ip
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        _cached_lan_ip = s.getsockname()[0]
    except (IOError, OSError):
        _cached_lan_ip = '127.0.0.1'
    finally:
        s.close()
    return _cached_lan_ip


def get_server_ip():
    try:
        from flask import current_app
        if 'SERVER_IP' in current_app.config:
            return current_app.config['SERVER_IP']
    except RuntimeError:
        pass
    return get_lan_ip()


def is_lan_access(host):
    if not host:
        return False
    lan_ip = get_lan_ip()
    return (host.startswith('127.') or
            host.startswith('localhost') or
            host.startswith(lan_ip) or
            host == 'localhost')


def detect_platform(ua=None):
    if ua is None:
        from flask import request as req
        ua = req.headers.get('User-Agent', '').lower()
    else:
        ua = ua.lower()
    if 'iphone' in ua or 'ipad' in ua:
        return 'ios'
    elif 'harmony' in ua or 'hmos' in ua:
        return 'harmonyos'
    elif 'android' in ua:
        return 'android'
    return 'all'


def lan_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        host = request.host
        if not is_lan_access(host):
            flash('该功能仅限内网访问')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        host = request.host
        if not is_lan_access(host):
            flash('该功能仅限内网访问')
            return redirect(url_for('main.index'))
        if current_app.config.get('LAN_REQUIRE_LOGIN', False):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def file_sha256(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_icon_from_ipa(ipa_path, output_dir, timestamp):
    try:
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

            for pattern in icon_patterns:
                if pattern_matches[pattern]:
                    icon_data = zip_ref.read(pattern_matches[pattern][0])
                    icon_filename = f"{timestamp}icon.png"
                    with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                        f.write(icon_data)
                    return icon_filename

            for name in fallback_matches:
                try:
                    icon_data = zip_ref.read(name)
                    if len(icon_data) > 1000:
                        icon_filename = f"{timestamp}icon.png"
                        with open(os.path.join(output_dir, icon_filename), 'wb') as f:
                            f.write(icon_data)
                        return icon_filename
                except (IOError, OSError):
                    continue

        return None
    except Exception as e:
        current_app.logger.error(f"Error extracting icon: {e}")
        return None


def extract_icon_from_hap(hap_path, output_dir, timestamp):
    try:
        with zipfile.ZipFile(hap_path, 'r') as z:
            for name in z.namelist():
                if name in ('module.json', 'module.json5'):
                    try:
                        content = z.read(name).decode('utf-8')
                        if name.endswith('.json5'):
                            try:
                                import json5
                                data = json5.loads(content)
                            except ImportError:
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
        current_app.logger.error(f"Error extracting HAP icon: {e}")
    return None


def extract_icon_from_apk(apk_path, output_dir, timestamp):
    try:
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
        current_app.logger.error(f"Error extracting APK icon: {e}")
    return None


def parse_apk_metadata(apk_path):
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
        current_app.logger.error(f"Error parsing APK metadata: {e}")
    return None


def _parse_resources_index(data):
    results = {}
    i = 0
    while i < len(data) - 10:
        if data[i] in (0x02, 0x05) and i + 2 < len(data):
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

    if not results:
        results = _scan_resources_index_strings(data)

    return results


def _scan_resources_index_strings(data):
    strings = []
    i = 0
    while i < len(data):
        if 0x20 <= data[i] < 0x7f:
            start = i
            while i < len(data) and 0x20 <= data[i] < 0x7f:
                i += 1
            s = data[start:i].decode('ascii')
            if len(s) >= 2:
                strings.append((start, s))
        i += 1

    key_candidates = {}
    for offset, s in strings:
        if '_' in s or s.islower():
            key_candidates[offset] = s

    results = {}
    for idx, (key_offset, key) in enumerate(key_candidates.items()):
        for val_offset, val in strings:
            if val_offset != key_offset and val not in key_candidates.values():
                if abs(val_offset - key_offset) < 100:
                    if val.isprintable() and not val.startswith('0x') and len(val) >= 2:
                        results[key] = val
                        break

    return results


def _resolve_hap_string_ref(z, ref):
    if not ref.startswith('$string:'):
        return ref
    key = ref[len('$string:'):]

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
    try:
        with zipfile.ZipFile(hap_path, 'r') as z:
            pack_info = None
            module_data = None
            module_key = None
            namelist = z.namelist()

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

            def resolve_ref(ref):
                if not ref or not isinstance(ref, str):
                    return ''
                if ref.startswith('$string:'):
                    return _resolve_hap_string_ref(z, ref)
                return ref

            name = ''
            label = app_info.get('label', '')
            resolved_label = resolve_ref(label)
            if resolved_label:
                name = resolved_label

            if not name and pack_info:
                pack_label = pack_info.get('summary', {}).get('app', {}).get('label', '')
                if pack_label:
                    name = pack_label

            if not name:
                name = app_info.get('bundleName', '')

            bundle_id = app_info.get('bundleName', '')
            version = app_info.get('versionName', '')
            build_number = ''

            if pack_info:
                summary_app = pack_info.get('summary', {}).get('app', {})
                version_info = summary_app.get('version', {})
                build_number = str(version_info.get('code', ''))

            if not build_number:
                build_number = str(app_info.get('versionCode', ''))

            icon_ref = app_info.get('icon', '')

            return {
                'name': name,
                'bundle_id': bundle_id,
                'version': version,
                'build_number': build_number,
                'icon_ref': icon_ref,
            }
    except Exception as e:
        current_app.logger.error(f"Error parsing HAP metadata: {e}")
    return None


def generate_certificates(cn):
    cert_path = os.path.join(current_app.config['CERT_FOLDER'], 'local.crt')
    key_path = os.path.join(current_app.config['CERT_FOLDER'], 'local.key')

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    os.makedirs(current_app.config['CERT_FOLDER'], exist_ok=True)

    import subprocess
    cmd = [
        'openssl', 'req', '-x509', '-nodes', '-days', '3650',
        '-newkey', 'rsa:2048',
        '-keyout', key_path,
        '-out', cert_path,
        '-subj', f'/CN={cn}'
    ]

    subprocess.run(cmd, check=True)
    return cert_path, key_path
