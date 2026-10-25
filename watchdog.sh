#!/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "[XiaoCan] Watchdog 已启动。"

while true; do
    if curl -fsS --max-time 5 http://127.0.0.1:8690/health >/dev/null 2>&1; then
        :
    else
        echo "[XiaoCan] 健康检查失败，尝试启动服务..."
        ./start.sh
    fi

    sleep 30
done
