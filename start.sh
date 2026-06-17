#!/bin/bash

echo "==================================="
echo "   IPA内部分发系统启动脚本"
echo "==================================="
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python3"
    exit 1
fi

# 检查依赖
echo "检查并安装依赖..."
pip3 install -r requirements.txt -q

echo ""
echo "启动IPA分发服务..."
echo "请稍候，首次启动会自动生成自签名证书..."
echo ""

python3 app.py
