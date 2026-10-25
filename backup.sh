#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_FILE="$APP_DIR/backend/data/xiaocan.db"
BACKUP_DIR="$APP_DIR/backend/data/backups"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
    echo "[XiaoCan] SQLite 数据库不存在，跳过备份。"
    exit 0
fi

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/xiaocan_${TIMESTAMP}.db"

cp "$DB_FILE" "$BACKUP_FILE"

echo "[XiaoCan] SQLite 备份完成:"
echo "$BACKUP_FILE"

find "$BACKUP_DIR" -type f -name 'xiaocan_*.db' -printf '%T@ %p\n' \
    | sort -nr \
    | tail -n +11 \
    | cut -d' ' -f2- \
    | xargs -r rm -f

echo "[XiaoCan] 保留最近 10 份备份。"
