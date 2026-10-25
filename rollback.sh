#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ ! -f .xiaocan_previous_commit ]; then
    echo "[XiaoCan] 没有找到可回滚的版本记录。"
    exit 1
fi

PREVIOUS_COMMIT=$(cat .xiaocan_previous_commit)

if ! git cat-file -e "${PREVIOUS_COMMIT}^{commit}" 2>/dev/null; then
    echo "[XiaoCan] 回滚目标不存在: $PREVIOUS_COMMIT"
    exit 1
fi

echo "[XiaoCan] 回滚到: $PREVIOUS_COMMIT"

git reset --hard "$PREVIOUS_COMMIT"

echo "[XiaoCan] Git 版本已回滚。"
echo "[XiaoCan] SQLite 数据库不会被删除或覆盖。"
