# IPA内部分发系统

一个基于Python Flask的企业IPA内部分发网站，支持自签名HTTPS、Web管理界面、一键安装。

## 功能特性

- ✅ 自签名HTTPS支持（自动生成10年有效期证书）
- ✅ Web管理界面（上传、删除、查看应用）
- ✅ 自动生成manifest.plist
- ✅ 一键安装链接（itms-services协议）
- ✅ 证书下载页面
- ✅ 响应式设计，支持移动端

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 启动服务

```bash
# 方式一：使用启动脚本
./start.sh

# 方式二：直接运行
python3 app.py
```

### 3. 访问管理界面

服务启动后，访问：
- 管理界面：https://你的IP:8443/
- 证书下载：https://你的IP:8443/cert

## 使用流程

### 第一步：iOS设备安装证书

1. 在iOS设备上访问 `https://服务器IP:8443/cert` 下载证书
2. 打开下载的证书文件，安装描述文件
3. 进入 **设置 → 通用 → 关于本机 → 证书信任设置**
4. 找到刚才安装的证书，开启 **完全信任**

### 第二步：上传IPA应用

1. 访问管理界面 `https://服务器IP:8443/`
2. 点击 **上传应用**
3. 填写应用信息（名称、Bundle ID、版本号）
4. 选择IPA文件（必须是企业签名）
5. 可选：上传应用图标
6. 点击上传

### 第三步：安装应用

1. 在应用列表中找到要安装的应用
2. 点击 **安装** 按钮
3. 在安装页面点击 **一键安装**
4. 系统会弹出安装确认对话框
5. 等待下载和安装完成

### 第四步：信任企业开发者

1. 安装完成后，首次打开会提示"未受信任的企业开发者"
2. 进入 **设置 → 通用 → VPN与设备管理**
3. 找到对应的企业证书
4. 点击 **信任**

## 目录结构

```
localservice/
├── app.py              # 主应用
├── requirements.txt    # Python依赖
├── start.sh           # 启动脚本
├── templates/         # HTML模板
│   ├── base.html      # 基础模板
│   ├── index.html     # 首页（应用列表）
│   ├── upload.html    # 上传页面
│   └── install.html   # 安装页面
├── static/            # 静态文件
│   ├── style.css      # 样式文件
│   └── icon.png       # 默认图标
├── uploads/           # IPA上传目录
├── certs/             # 证书目录
│   ├── local.crt      # 自签名证书
│   └── local.key      # 私钥
└── apps.db           # SQLite数据库
```

## API接口

- `GET /` - 应用列表页面
- `GET /upload` - 上传页面
- `POST /upload` - 上传应用
- `GET /install/<id>` - 安装页面
- `GET /manifest/<id>` - 获取manifest.plist
- `GET /download/<filename>` - 下载文件
- `GET /cert` - 下载证书
- `GET /api/apps` - 获取应用列表（JSON）

## 注意事项

1. **IPA签名要求**：必须使用企业证书签名，且包含正确的Provisioning Profile
2. **Bundle ID**：填写的Bundle ID必须与IPA中的保持一致
3. **证书信任**：每台iOS设备都需要安装并信任自签名证书
4. **网络要求**：iOS设备需要能访问服务器的8443端口
5. **Safari浏览器**：安装链接需要使用Safari浏览器打开

## 常见问题

### Q: 为什么安装链接没有反应？
A: 请确保：
- 使用Safari浏览器打开
- 已安装并信任自签名证书
- manifest.plist的URL使用HTTPS

### Q: 提示"无法安装应用"？
A: 可能原因：
- IPA文件签名问题
- Bundle ID不匹配
- 服务器HTTPS证书未信任

### Q: 如何修改端口号？
A: 编辑 `app.py` 文件，修改最后一行的端口号：
```python
app.run(host='0.0.0.0', port=8443, ssl_context=(cert_path, key_path))
```

### Q: 如何使用域名访问？
A: 修改 `generate_certificates` 函数中的CN参数为你的域名。

## 技术栈

- Python 3
- Flask
- SQLite
- OpenSSL（自签名证书）
- HTML/CSS/JavaScript

## 许可证

MIT License
