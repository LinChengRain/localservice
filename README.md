# 企业应用分发平台

一个基于 Python Flask 的企业应用内部分发平台，支持 iOS IPA、HarmonyOS HAP 和 Android APK 应用的上传、管理和分发。

## 功能特性

### 核心功能
- ✅ **三平台支持**：iOS IPA、HarmonyOS HAP、Android APK 应用分发
- ✅ **自签名 HTTPS**：自动生成 10 年有效期证书
- ✅ **Web 管理界面**：响应式设计，支持移动端访问
- ✅ **自动解析**：自动提取应用名称、Bundle ID、版本号、图标
- ✅ **版本分组**：按应用分组显示，版本折叠/展开交互
- ✅ **构建管理**：构建号自动累加，区分同一版本的不同构建

### 安全特性
- ✅ **访问控制**：公网只读，内网可配置登录
- ✅ **CSRF 防护**：Flask-WTF 表单保护
- ✅ **登录认证**：Flask-Login + 密码哈希存储
- ✅ **Docker 部署**：一键容器化部署

### 平台特性
- ✅ **包类型选择**：支持正式版、准生产、测试版、调试版
- ✅ **平台标签**：iOS、鸿蒙、Android 应用用不同颜色标签区分
- ✅ **移动端过滤**：自动识别设备平台并筛选应用
- ✅ **PC 端筛选**：提供平台筛选标签（全部/iOS/鸿蒙/Android）

### 安装方式
- ✅ **iOS**：通过 `itms-services://` 协议一键安装
- ✅ **HarmonyOS**：通过 `store://enterprise/manifest` DeepLink 安装
- ✅ **Android**：直接下载 APK 安装
- ✅ **公网访问**：支持 Cloudflared 隧道实现公网分发

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 一键启动

```bash
./start.sh
```

脚本会自动：
- 停止已有服务
- 安装依赖
- 启动 Flask 本地服务（端口 8080）
- 启动 Cloudflared 公网隧道
- 显示访问地址

### 3. 访问管理界面

启动后访问：
- 本地访问：http://127.0.0.1:8080
- 局域网访问：http://你的IP:8080
- 公网访问：脚本输出的 Cloudflared URL

## 配置说明

### 环境变量配置

创建 `.env` 文件（参考 `.env.example`）：

```env
# Flask密钥（首次运行自动生成）
SECRET_KEY=

# 数据库路径
DATABASE=apps.db

# 上传文件存储目录
UPLOAD_FOLDER=uploads

# 证书存储目录
CERT_FOLDER=certs

# 最大上传文件大小（字节，默认500MB）
MAX_CONTENT_LENGTH=524288000

# 内网是否强制登录（true/false，默认false，内网免登录）
LAN_REQUIRE_LOGIN=false

# 管理员账户（首次启动时自动创建）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
```

### 访问控制

| 访问来源 | 可用功能 | 需要登录 |
|----------|----------|----------|
| **公网域名** | 查看应用列表、下载应用 | 不需要 |
| **内网/本地** | 全部功能（上传、删除、管理） | 取决于 `LAN_REQUIRE_LOGIN` |

- `LAN_REQUIRE_LOGIN=false`（默认）：内网免登录直接可用
- `LAN_REQUIRE_LOGIN=true`：内网需登录后才能操作

## 使用流程

### iOS 应用分发

#### 第一步：安装证书（首次）

1. iOS 设备访问 `https://服务器地址/cert` 下载证书
2. 安装描述文件
3. 进入 **设置 → 通用 → 关于本机 → 证书信任设置**
4. 开启 **完全信任**

#### 第二步：上传 IPA

1. 访问管理界面，点击 **上传应用**
2. 选择 IPA 文件（自动解析应用信息）
3. 选择包类型（测试版/正式版等）
4. 点击上传

#### 第三步：安装应用

1. 在应用列表找到目标应用
2. 点击 **安装**
3. 使用 **Safari 浏览器** 打开安装链接
4. 确认安装

#### 第四步：信任企业开发者

1. 进入 **设置 → 通用 → VPN与设备管理**
2. 找到企业证书，点击 **信任**

### HarmonyOS 应用分发

#### 第一步：上传 HAP

1. 访问管理界面，点击 **上传应用**
2. 选择 HAP 文件（自动解析 module.json）
3. 选择包类型
4. 点击上传

#### 第二步：安装应用

1. 在应用列表找到鸿蒙应用
2. 点击 **安装**
3. 使用 **鸿蒙系统浏览器** 打开安装链接
4. 确认安装

### Android 应用分发

#### 第一步：上传 APK

1. 访问管理界面，点击 **上传应用**
2. 选择 APK 文件（自动解析 AndroidManifest）
3. 选择包类型
4. 点击上传

#### 第二步：安装应用

1. 在应用列表找到 Android 应用
2. 点击 **安装** 或扫码下载
3. 在设备上打开 APK 安装

## 目录结构

```
localservice/
├── app/                    # 应用包
│   ├── __init__.py         # Flask app 工厂
│   ├── config.py           # 配置管理
│   ├── models.py           # 数据库模型
│   ├── utils.py            # 工具函数
│   └── routes/             # 路由模块
│       ├── main.py         # 首页、安装页、下载
│       ├── auth.py         # 登录认证
│       ├── upload.py       # 上传功能
│       ├── admin.py        # 管理功能
│       └── api.py          # JSON API 接口
├── templates/              # HTML 模板
│   ├── base.html           # 基础模板
│   ├── index.html          # 首页（应用列表）
│   ├── upload.html         # 上传页面
│   ├── install.html        # 安装页面
│   └── login.html          # 登录页面
├── static/                 # 静态文件
│   └── style.css           # 样式文件
├── run.py                  # 开发启动入口
├── wsgi.py                 # Gunicorn 生产入口
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── Dockerfile              # Docker 镜像
├── docker-compose.yml      # Docker Compose 配置
├── start.sh                # 一键启动脚本
├── uploads/                # 应用文件上传目录
├── certs/                  # 证书目录
│   ├── local.crt           # 自签名证书
│   └── local.key           # 私钥
└── apps.db                 # SQLite 数据库
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 应用列表页面 |
| `/upload` | GET/POST | 上传页面/上传应用（需内网） |
| `/install/<id>` | GET | 安装页面 |
| `/manifest/<id>` | GET | iOS manifest.plist |
| `/manifest-harmony/<id>.json5` | GET | 鸿蒙 manifest JSON5 |
| `/download/<filename>` | GET | 下载文件 |
| `/cert` | GET | 下载证书 |
| `/health` | GET | 健康检查 |
| `/auth/login` | GET/POST | 登录页面 |
| `/auth/logout` | GET | 退出登录 |
| `/api/apps` | GET | 应用列表（JSON） |
| `/api/apps/grouped` | GET | 分组应用列表（JSON） |
| `/api/parse-ipa` | POST | 解析 IPA 文件元数据 |
| `/api/parse-hap` | POST | 解析 HAP 文件元数据 |
| `/api/parse-apk` | POST | 解析 APK 文件元数据 |

## 数据库结构

```sql
-- 应用表
CREATE TABLE apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                  -- 应用名称
    bundle_id TEXT NOT NULL,             -- Bundle ID
    version TEXT NOT NULL,               -- 版本号
    filename TEXT NOT NULL,              -- 文件名
    upload_time TIMESTAMP,               -- 上传时间
    icon_filename TEXT,                  -- 图标文件名
    description TEXT,                    -- 描述
    build_number TEXT DEFAULT '',        -- 构建号
    build_type TEXT DEFAULT 'release',   -- 包类型
    platform TEXT DEFAULT 'ios'          -- 平台（ios/harmonyos/android）
);

-- 用户表
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,       -- 用户名
    password_hash TEXT NOT NULL,         -- 密码哈希
    role TEXT DEFAULT 'admin',           -- 角色
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 下载记录表
CREATE TABLE download_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,             -- 应用ID
    ip_address TEXT,                     -- 下载者IP
    user_agent TEXT,                     -- 浏览器信息
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 部署方式

### 方式一：直接运行（推荐）

```bash
./start.sh
```

### 方式二：Docker

```bash
docker-compose up -d
```

### 方式三：Gunicorn 生产部署

```bash
gunicorn wsgi:app -b 0.0.0.0:8080 --workers 4
```

## 注意事项

### iOS 应用
1. IPA 必须使用企业证书签名
2. Bundle ID 必须与 IPA 中一致
3. 安装链接需使用 Safari 浏览器打开
4. 每台设备需安装并信任自签名证书

### HarmonyOS 应用
1. HAP 必须使用企业证书签名
2. manifest URL 必须以 `.json5` 结尾
3. `deployDomain` 必须与 manifest URL 域名一致
4. DeepLink URL 需要 `encodeURIComponent` 编码

### Android 应用
1. APK 需确保已签名
2. 设备需开启"允许安装未知来源应用"

### 公网访问
1. 使用 Cloudflared 隧道实现公网分发
2. 每次重启会分配新的公网 URL
3. 大文件下载可能较慢，建议局域网内使用

## 常见问题

### Q: iOS 安装链接没有反应？
A: 请确保：
- 使用 Safari 浏览器打开
- 已安装并信任自签名证书
- manifest.plist URL 使用 HTTPS

### Q: HarmonyOS 提示"下载来源验证失败"？
A: 请检查：
- manifest URL 是否以 `.json5` 结尾
- `deployDomain` 是否与 URL 域名一致
- URL 是否正确编码

### Q: 如何修改端口号？
A: 启动时指定端口参数：
```bash
python3 run.py --ngrok --http-port 9090
```

### Q: 如何启用登录验证？
A: 创建 `.env` 文件，设置：
```env
LAN_REQUIRE_LOGIN=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的密码
```

### Q: 如何使用固定域名？
A: 启动时指定服务器地址：
```bash
python3 run.py --ngrok --server your-domain.com
```

## 技术栈

- **后端**：Python 3、Flask、SQLite、Flask-Login、Flask-WTF
- **前端**：HTML5、CSS3、JavaScript
- **工具**：OpenSSL（自签名证书）、Cloudflared（公网隧道）
- **解析**：plistlib（IPA）、zipfile + json5（HAP）、androguard（APK）
- **部署**：Gunicorn、Docker

## 许可证

MIT License
