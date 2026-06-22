import argparse
import os
from app import create_app
from app.utils import get_server_ip, get_lan_ip, generate_certificates


def main():
    parser = argparse.ArgumentParser(description='应用分发服务')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8443, help='HTTPS端口')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP端口（用于ngrok）')
    parser.add_argument('--server', default=None, help='公网服务器地址（用于ngrok等场景）')
    parser.add_argument('--ngrok', action='store_true', help='ngrok模式：只启动HTTP，不启动HTTPS')
    args = parser.parse_args()

    app = create_app()

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CERT_FOLDER'], exist_ok=True)

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
        print(f"  1. 先启动本服务: python3 run.py --ngrok --server <ngrok地址>")
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


if __name__ == '__main__':
    main()
