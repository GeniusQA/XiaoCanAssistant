#!/bin/bash
set -e

URL="http://127.0.0.1:8690/health"

echo "[XiaoCan] 检查服务健康状态..."

if curl -fsS --max-time 10 "$URL" >/tmp/xiaocan_health.json; then
    echo "[XiaoCan] 健康检查通过:"
    cat /tmp/xiaocan_health.json
else
    echo "[XiaoCan] 健康检查失败。"
    exit 1
fi
