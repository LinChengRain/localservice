#!/bin/bash

echo "==================================="
echo "   使用ngrok进行内网穿透"
echo "==================================="
echo ""

# 检查是否安装ngrok
if ! command -v ngrok &> /dev/null; then
    echo "正在安装ngrok..."
    brew install ngrok
fi

echo "启动ngrok隧道..."
echo "请使用生成的公网URL访问"
echo ""

ngrok http 8443
