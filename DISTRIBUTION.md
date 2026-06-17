# IPA分发方案（不依赖WiFi）

## 方案一：内网穿透（推荐）

使用ngrok将本地服务暴露到公网，iOS设备通过移动数据访问。

### 步骤

1. 安装ngrok
```bash
brew install ngrok
```

2. 注册ngrok账号并获取authtoken
```bash
ngrok config add-authtoken your_token
```

3. 启动服务和ngrok
```bash
# 终端1：启动IPA服务
python3 app.py

# 终端2：启动ngrok
ngrok http 8443
```

4. 使用生成的公网URL（如 `https://xxxx.ngrok-free.app`）
- iOS设备访问该URL即可
- 无需WiFi，可用移动数据

### 一键启动脚本
```bash
./tunnel.sh
```

## 方案二：公网服务器

将服务部署到云服务器（阿里云、腾讯云等）。

1. 购买云服务器（有公网IP）
2. 安装Python和依赖
3. 上传代码和IPA
4. 启动服务

```bash
# 在云服务器上
python3 app.py --server your-server-ip
```

## 方案三：云存储分发

将IPA上传到云存储，生成下载链接。

1. 上传IPA到阿里云OSS/腾讯云COS
2. 设置公开读取权限
3. 生成manifest.plist指向云存储链接

## 方案四：邮件分发

1. 将IPA上传到任意HTTPS服务器
2. 编写安装邮件，包含itms-services链接
3. 发送给目标用户

---

## 快速开始（ngrok方案）

```bash
# 1. 启动服务
python3 app.py

# 2. 启动ngrok（新终端）
ngrok http 8443

# 3. 复制ngrok生成的公网URL（如https://xxxx.ngrok-free.app）

# 4. 在iOS设备上：
#    - 访问 公网URL/cert 下载证书
#    - 信任证书
#    - 访问 公网URL/ 上传/安装应用
```

## 注意事项

1. **ngrok免费版限制**
   - 每次重启URL会变
   - 有连接数限制
   - 建议升级到付费版或使用固定子域名

2. **企业证书问题**
   - 确保证书未被苹果吊销
   - iOS 16+可能有额外限制

3. **安全性**
   - 公网暴露服务有风险
   - 建议添加登录认证
   - 限制访问IP
