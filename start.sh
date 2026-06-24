#!/bin/bash

HTTP_PORT=8808

echo "==================================="
echo "   应用分发系统启动脚本"
echo "==================================="
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python3"
    exit 1
fi

# 检查依赖
echo "检查并安装依赖..."
if ! pip3 install -r requirements.txt -q 2>/dev/null; then
    echo "警告: 依赖安装可能存在问题，继续启动..."
fi

# 停止已有的服务
echo "停止已有的服务..."
pkill -f "python3 run.py" 2>/dev/null
pkill cloudflared 2>/dev/null
sleep 1

# 检查端口是否被占用
if lsof -i :${HTTP_PORT} > /dev/null 2>&1; then
    echo "端口${HTTP_PORT}被占用，正在释放..."
    kill $(lsof -t -i :${HTTP_PORT}) 2>/dev/null
    sleep 2
    if lsof -i :${HTTP_PORT} > /dev/null 2>&1; then
        kill -9 $(lsof -t -i :${HTTP_PORT}) 2>/dev/null
        sleep 1
    fi
fi

# 获取本机IP（基于默认路由接口）
DEFAULT_IF=$(route get default 2>/dev/null | grep interface | awk '{print $2}')
LAN_IP=$(ipconfig getifaddr ${DEFAULT_IF} 2>/dev/null || echo "127.0.0.1")

# 清理旧日志
> /tmp/cloudflared.log

echo ""
echo "启动应用分发服务..."

# 先启动Flask服务（后台运行），确保端口就绪
python3 run.py --ngrok --http-port ${HTTP_PORT} &
FLASK_PID=$!

# 等待Flask端口就绪
echo "等待服务就绪..."
FLASK_READY=false
for i in $(seq 1 10); do
    if lsof -i :${HTTP_PORT} > /dev/null 2>&1; then
        FLASK_READY=true
        break
    fi
    sleep 1
done

if [ "$FLASK_READY" = false ]; then
    echo "错误: Flask服务启动超时"
    kill $FLASK_PID 2>/dev/null
    exit 1
fi

echo ""
echo "启动公网隧道..."
cloudflared tunnel --url http://localhost:${HTTP_PORT} > /tmp/cloudflared.log 2>&1 &
CLOUDFLARED_PID=$!

# 等待cloudflared启动并获取URL
for i in $(seq 1 15); do
    PUBLIC_URL=$(grep -o 'https://[^ ]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | tail -1)
    if [ -n "$PUBLIC_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$PUBLIC_URL" ]; then
    echo "警告: 未能获取公网隧道地址，请检查网络或DNS设置"
fi

echo ""
echo "==================================="
echo "   服务启动成功"
echo "==================================="
echo ""
echo "本地访问: http://127.0.0.1:${HTTP_PORT}"
echo "局域网访问: http://${LAN_IP}:${HTTP_PORT}"
if [ -n "$PUBLIC_URL" ]; then
    echo "公网访问: ${PUBLIC_URL}"
fi

# 健康检查
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${HTTP_PORT}/ 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "健康检查: 通过"
else
    echo "健康检查: 失败 (HTTP ${HTTP_CODE})"
fi

echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $FLASK_PID 2>/dev/null
    kill $CLOUDFLARED_PID 2>/dev/null
    wait $FLASK_PID $CLOUDFLARED_PID 2>/dev/null
    echo "服务已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 等待进程结束
wait
