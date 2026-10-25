#!/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$APP_DIR/.xiaocan.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[XiaoCan] 没有找到服务 PID 文件，服务可能未由 start.sh 启动。"
    exit 0
fi

PID=$(cat "$PID_FILE" 2>/dev/null || true)

if [ -z "$PID" ]; then
    rm -f "$PID_FILE"
    echo "[XiaoCan] PID 文件为空，已清理。"
    exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
    echo "[XiaoCan] 停止服务，PID: $PID"
    kill "$PID"

    for i in 1 2 3 4 5; do
        sleep 1
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
    done

    if kill -0 "$PID" 2>/dev/null; then
        echo "[XiaoCan] 服务未正常退出，强制停止..."
        kill -9 "$PID" 2>/dev/null || true
    fi
else
    echo "[XiaoCan] PID $PID 已不存在。"
fi

rm -f "$PID_FILE"
echo "[XiaoCan] 服务已停止。"
