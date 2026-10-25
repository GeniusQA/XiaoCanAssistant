#!/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "[XiaoCan] 开始检查更新..."

git fetch origin main

CURRENT_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/main)

if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo "[XiaoCan] 当前已经是最新版本。"
    exit 0
fi

echo "[XiaoCan] 当前版本: $CURRENT_COMMIT"
echo "[XiaoCan] 最新版本: $REMOTE_COMMIT"

echo "$CURRENT_COMMIT" > .xiaocan_previous_commit

echo "[XiaoCan] 创建 SQLite 备份..."
./backup.sh

echo "[XiaoCan] 停止当前服务..."
./stop.sh || true

echo "[XiaoCan] 更新 Git 版本..."
if ! git reset --hard origin/main; then
    echo "[XiaoCan] Git 更新失败，开始回滚..."
    ./rollback.sh
    ./start.sh
    exit 1
fi

echo "[XiaoCan] 更新 Python 依赖..."
source backend/venv/bin/activate

if ! pip install -r backend/requirements.txt; then
    echo "[XiaoCan] Python 依赖更新失败，开始回滚..."
    ./rollback.sh
    ./start.sh
    exit 1
fi

echo "[XiaoCan] 更新前端依赖..."
cd frontend

if ! npm ci; then
    cd "$APP_DIR"
    echo "[XiaoCan] 前端依赖更新失败，开始回滚..."
    ./rollback.sh
    ./start.sh
    exit 1
fi

echo "[XiaoCan] 构建前端..."

if ! npm run build; then
    cd "$APP_DIR"
    echo "[XiaoCan] 前端构建失败，开始回滚..."
    ./rollback.sh
    ./start.sh
    exit 1
fi

cd "$APP_DIR"

echo "[XiaoCan] 启动更新后的服务..."
./start.sh &
START_PID=$!

sleep 5

echo "[XiaoCan] 执行健康检查..."

if ./healthcheck.sh; then
    echo "[XiaoCan] 更新成功，健康检查通过。"
    exit 0
fi

echo "[XiaoCan] 更新后的服务健康检查失败。"
echo "[XiaoCan] 开始自动回滚..."

./stop.sh || true
./rollback.sh

echo "[XiaoCan] 启动回滚后的服务..."
./start.sh &

sleep 5

echo "[XiaoCan] 检查回滚后的服务..."

if ./healthcheck.sh; then
    echo "[XiaoCan] 回滚成功，服务已恢复。"
    exit 1
fi

echo "[XiaoCan] 回滚后的服务仍然异常，请人工检查。"
exit 2
