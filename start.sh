#!/bin/bash

echo "==================================="
echo "   应用分发系统启动脚本"
echo "==================================="
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python3"
    exit 1
fi

# 停止已有的服务
echo "停止已有的服务..."
pkill -f "python3 app.py" 2>/dev/null
pkill cloudflared 2>/dev/null
sleep 1

# 检查端口是否被占用
if lsof -i :8080 > /dev/null 2>&1; then
    echo "端口8080被占用，正在释放..."
    kill $(lsof -t -i :8080) 2>/dev/null
    sleep 1
fi

# 检查依赖
echo "检查并安装依赖..."
pip3 install -r requirements.txt -q 2>/dev/null

# 获取本机IP
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")

echo ""
echo "启动应用分发服务..."

# 启动Flask服务（后台运行）
python3 app.py --ngrok --server localhost &
FLASK_PID=$!

# 等待Flask启动
sleep 2

# 启动cloudflared隧道（后台运行）
echo "启动公网隧道..."
cloudflared tunnel --url http://localhost:8080 > /tmp/cloudflared.log 2>&1 &
CLOUDFLARED_PID=$!

# 等待cloudflared启动并获取URL
sleep 6
PUBLIC_URL=$(grep -o 'https://[^ ]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | tail -1)

echo ""
echo "==================================="
echo "   服务启动成功"
echo "==================================="
echo ""
echo "本地访问: http://127.0.0.1:8080"
echo "局域网访问: http://${LAN_IP}:8080"
if [ -n "$PUBLIC_URL" ]; then
    echo "公网访问: ${PUBLIC_URL}"
fi
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 捕获Ctrl+C，停止所有服务
trap "echo ''; echo '正在停止服务...'; kill $FLASK_PID $CLOUDFLARED_PID 2>/dev/null; echo '服务已停止'; exit 0" SIGINT SIGTERM

# 等待进程结束
wait
