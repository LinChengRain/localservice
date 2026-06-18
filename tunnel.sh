#!/bin/bash

echo "==================================="
echo "   使用 Cloudflare Tunnel 内网穿透"
echo "==================================="
echo ""

cloudflared tunnel --url http://localhost:8080
