#!/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

PID_FILE="$APP_DIR/.xiaocan.pid"
LOG_FILE="$APP_DIR/xiaocan.log"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)

    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[XiaoCan] 服务已经在运行，PID: $OLD_PID"
        exit 0
    fi

    rm -f "$PID_FILE"
fi

source backend/venv/bin/activate

export XIAOCAN_RELOAD=0

echo "[XiaoCan] 检查 Node.js..."
node --version

echo "[XiaoCan] 检查 SQLite..."
mkdir -p backend/data

echo "[XiaoCan] 启动服务..."

nohup python backend/main.py >> "$LOG_FILE" 2>&1 &
PID=$!

echo "$PID" > "$PID_FILE"

echo "[XiaoCan] 等待服务启动..."

for i in $(seq 1 30); do
    if curl -fsS --max-time 2 http://127.0.0.1:8690/health >/dev/null 2>&1; then
        echo "[XiaoCan] 服务已启动，PID: $PID"
        echo "[XiaoCan] 日志: $LOG_FILE"
        exit 0
    fi

    if ! kill -0 "$PID" 2>/dev/null; then
        echo "[XiaoCan] 服务进程已退出，启动失败。"
        rm -f "$PID_FILE"
        exit 1
    fi

    sleep 1
done

echo "[XiaoCan] 服务启动超时。"
echo "[XiaoCan] 日志: $LOG_FILE"
exit 1
