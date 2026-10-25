#!/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "[XiaoCan] Watchdog 已启动。"

while true; do
    if [ ! -f "$APP_DIR/.xiaocan.pid" ]; then
        echo "[XiaoCan] 未检测到 PID 文件，尝试启动服务..."
        ./start.sh
    else
        PID=$(cat "$APP_DIR/.xiaocan.pid" 2>/dev/null || true)

        if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
            echo "[XiaoCan] 服务进程异常退出，尝试重新启动..."
            rm -f "$APP_DIR/.xiaocan.pid"
            ./start.sh
        fi
    fi

    sleep 30
done
