# -*- coding: utf-8 -*-
"""
SQLite 数据库初始化与轻量 ORM 封装
单文件零运维，自动建表
"""
import sqlite3
import datetime
import json
import os
import time
import uuid
import secrets
from typing import List, Dict, Any, Optional, Tuple
from ..core import time_service

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "xiaocan.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 企业级 SQLite 高并发调优：WAL 无锁并发读写、15s 防锁死超时、NORMAL 刷盘与 8MB 页缓存
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = NORMAL")
    c.execute("PRAGMA busy_timeout = 15000")
    c.execute("PRAGMA cache_size = -8000")

    # 1. 账号表 (无车位上限，永久激活)
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        key TEXT PRIMARY KEY,
        silk_id TEXT,
        nickname TEXT,
        avatar TEXT,
        token TEXT,
        vip_level INTEGER DEFAULT 5,
        city_code INTEGER DEFAULT 0,
        city_name TEXT DEFAULT '',
        longitude TEXT DEFAULT '',
        latitude TEXT DEFAULT '',
        address_name TEXT DEFAULT '',
        short_name TEXT DEFAULT '',
        full_address TEXT DEFAULT '',
        location_source TEXT DEFAULT '',
        location_source_name TEXT DEFAULT '',
        location_remark TEXT DEFAULT '',
        last_official_sync REAL DEFAULT 0,
        expires_at TEXT DEFAULT '2099-12-31',
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 动态检查 accounts 补充官方原生字段 (严格对齐小蚕官方用户模型，不臆造自定义字段)
    acc_cols = [r[1] for r in c.execute("PRAGMA table_info(accounts)").fetchall()]
    if "user_id" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN user_id TEXT DEFAULT ''")
    if "is_plus" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN is_plus INTEGER DEFAULT 0")
    if "phone" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN phone TEXT DEFAULT ''")
    if "real_name" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN real_name TEXT DEFAULT ''")
    if "vip_score" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN vip_score INTEGER DEFAULT 0")
    if "vip_expired_at" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN vip_expired_at INTEGER DEFAULT 0")
    if "silk" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN silk INTEGER DEFAULT 0")
    if "withdrawing" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN withdrawing INTEGER DEFAULT 0")
    if "withdraw_total" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN withdraw_total INTEGER DEFAULT 0")
    if "completed_number" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN completed_number INTEGER DEFAULT 0")
    if "yb_point" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN yb_point INTEGER DEFAULT 0")
    if "unreceived_points" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN unreceived_points INTEGER DEFAULT 0")
    if "notify_mode" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN notify_mode TEXT DEFAULT 'global'")
    if "notify_config" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN notify_config TEXT DEFAULT '{}'")
    if "client_mode" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN client_mode TEXT DEFAULT 'app'")
    if "platform" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN platform TEXT DEFAULT 'xiaocan'")
    if "saved_at" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN saved_at INTEGER DEFAULT 0")
    if "last_claimed_at" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN last_claimed_at INTEGER DEFAULT 0")
    if "last_claimed_count" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN last_claimed_count INTEGER DEFAULT 0")
    if "last_claimed_details" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN last_claimed_details TEXT DEFAULT '[]'")
    if "history_pool" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN history_pool TEXT DEFAULT '[]'")
    if "meituan_token" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_token TEXT DEFAULT ''")
    if "meituan_nickname" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_nickname TEXT DEFAULT ''")
    if "meituan_saved_at" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_saved_at INTEGER DEFAULT 0")
    if "meituan_last_claimed_at" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_last_claimed_at INTEGER DEFAULT 0")
    if "meituan_last_claimed_count" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_last_claimed_count INTEGER DEFAULT 0")
    if "meituan_last_claimed_details" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_last_claimed_details TEXT DEFAULT '[]'")
    if "meituan_history_pool" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_history_pool TEXT DEFAULT '[]'")
    if "meituan_is_active" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN meituan_is_active INTEGER DEFAULT 0")
    if "address_name" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN address_name TEXT DEFAULT ''")
    if "short_name" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN short_name TEXT DEFAULT ''")
    if "full_address" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN full_address TEXT DEFAULT ''")
    if "location_source" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN location_source TEXT DEFAULT ''")
    if "location_source_name" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN location_source_name TEXT DEFAULT ''")
    if "location_remark" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN location_remark TEXT DEFAULT ''")
    if "last_official_sync" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN last_official_sync REAL DEFAULT 0")
    if "nick_name" not in acc_cols:
        c.execute("ALTER TABLE accounts ADD COLUMN nick_name TEXT DEFAULT ''")

    # 2. 自动化任务开关与调度表
    c.execute("""
    CREATE TABLE IF NOT EXISTS task_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_key TEXT,
        task_id TEXT,
        enabled INTEGER DEFAULT 0,
        cron_time TEXT,
        params TEXT,
        UNIQUE(account_key, task_id)
    )
    """)

    # 3. 店铺预约与抢单队列
    c.execute("""
    CREATE TABLE IF NOT EXISTS store_appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_key TEXT,
        store_id TEXT,
        store_name TEXT,
        promotion_id TEXT,
        status TEXT DEFAULT 'pending',
        early_ms INTEGER DEFAULT 500,
        rebate_card_id TEXT,
        rebate_card_name TEXT DEFAULT '',
        redpack_mode INTEGER DEFAULT 0,
        outcome TEXT,
        created_at TEXT
    )
    """)

    # 4. 运行日志表
    c.execute("""
    CREATE TABLE IF NOT EXISTS job_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT,
        account_key TEXT,
        task_id TEXT,
        status TEXT,
        output TEXT,
        result TEXT DEFAULT '',
        created_at TEXT
    )
    """)

    # 运行日志表迁移：新增执行结果字段，用于记录官方接口返回的具体报错信息
    job_cols = {row[1] for row in c.execute("PRAGMA table_info(job_logs)")}
    if "result" not in job_cols:
        c.execute("ALTER TABLE job_logs ADD COLUMN result TEXT DEFAULT ''")
    if "account_name" not in job_cols:
        c.execute("ALTER TABLE job_logs ADD COLUMN account_name TEXT DEFAULT ''")
    if "account_type" not in job_cols:
        c.execute("ALTER TABLE job_logs ADD COLUMN account_type TEXT DEFAULT ''")

    # 历史日志账号快照回填：不依赖 output 文本猜测，只按真实账号表映射。
    try:
        c.execute("""
            UPDATE job_logs
            SET account_type = CASE WHEN TRIM(COALESCE(account_key, '')) = '' THEN 'system' ELSE 'user' END,
                account_name = CASE WHEN TRIM(COALESCE(account_key, '')) = '' THEN '系统任务' ELSE '历史任务' END
            WHERE COALESCE(account_name, '') = ''
        """)
        for log_row in c.execute(
            "SELECT DISTINCT account_key FROM job_logs WHERE account_type = 'user' AND account_key != ''"
        ).fetchall():
            key = str(log_row[0] or "")
            account_row = c.execute("SELECT nickname FROM accounts WHERE key = ? LIMIT 1", (key,)).fetchone()
            if not account_row:
                continue
            nickname = str(account_row[0] or "").strip()
            lowered = nickname.lower()
            if not nickname or lowered in {"system", "all", "unknown", "默认账号", "系统", "系统任务"} or any(
                token in lowered for token in ("验证码", "waf", "stgw", "风控", "拦截")
            ):
                suffix = key.split("_")[-1] if "_" in key else key
                nickname = f"账号 {suffix[:8]}"
            c.execute(
                "UPDATE job_logs SET account_name = ? WHERE account_type = 'user' AND account_key = ? AND COALESCE(account_name, '') = '历史任务'",
                (nickname, key),
            )
    except Exception:
        pass

    # 官方 GetClientUserInfo 的 nickname 可能为空字符串/不换行空格，真实展示名在 real_name。
    try:
        for account_row in c.execute("SELECT key, nickname, real_name FROM accounts").fetchall():
            key = str(account_row[0] or "")
            nickname = str(account_row[1] or "")
            real_name = str(account_row[2] or "").strip()
            if not nickname.strip() and real_name:
                c.execute("UPDATE accounts SET nickname = ? WHERE key = ?", (real_name, key))
    except Exception:
        pass

    # 登录/抓包可能把验证码文案写入昵称，启动时统一纠正，避免污染所有任务展示。
    try:
        for account_row in c.execute("SELECT key, nickname FROM accounts").fetchall():
            key = str(account_row[0] or "")
            nickname = str(account_row[1] or "").strip()
            lowered = nickname.lower()
            account_real_name = str(account_row["real_name"] if "real_name" in account_row.keys() else "").strip()
            if not nickname or lowered in {"system", "all", "unknown", "默认账号", "系统", "系统任务"} or any(
                token in lowered for token in ("验证码", "waf", "stgw", "风控", "拦截")
            ):
                suffix = key.split("_")[-1] if "_" in key else key
                replacement = account_real_name or f"账号 {suffix[:8]}"
                c.execute("UPDATE accounts SET nickname = ? WHERE key = ?", (replacement, key))
    except Exception:
        pass

    # 历史修复：抢单成功后，删除/停止监听动作曾把日志状态错误降级为 error。
    try:
        c.execute("""
            UPDATE job_logs
            SET status = 'success'
            WHERE status IN ('error', 'failed', 'aborted')
              AND (
                result LIKE '抢单成功%'
                OR output LIKE '%任务已达成并自动停止%'
                OR output LIKE '%抢单成功锁定%'
              )
        """)
    except Exception:
        pass

    # 5. 系统与通知配置表
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 5.5 设备协同：临时配对票据与已授权设备凭证
    c.execute("""
    CREATE TABLE IF NOT EXISTS device_pair_tickets (
        ticket TEXT PRIMARY KEY,
        status TEXT DEFAULT 'pending',
        created_at REAL,
        expires_at REAL,
        consumed_at REAL,
        device_id TEXT,
        device_name TEXT,
        client_ip TEXT,
        user_agent TEXT,
        snapshot TEXT DEFAULT ''
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS paired_devices (
        id TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        token_hash TEXT,
        device_id TEXT,
        created_at REAL,
        last_seen_at REAL,
        revoked_at REAL,
        client_ip TEXT,
        user_agent TEXT,
        peer_base_url TEXT DEFAULT '',
        peer_name TEXT DEFAULT '',
        revoked_by_name TEXT DEFAULT ''
    )
    """)
    pair_cols = {row[1] for row in c.execute("PRAGMA table_info(device_pair_tickets)")}
    if "snapshot" not in pair_cols:
        c.execute("ALTER TABLE device_pair_tickets ADD COLUMN snapshot TEXT DEFAULT ''")
    device_cols = {row[1] for row in c.execute("PRAGMA table_info(paired_devices)")}
    if "peer_base_url" not in device_cols:
        c.execute("ALTER TABLE paired_devices ADD COLUMN peer_base_url TEXT DEFAULT ''")
    if "peer_name" not in device_cols:
        c.execute("ALTER TABLE paired_devices ADD COLUMN peer_name TEXT DEFAULT ''")
    if "revoked_by_name" not in device_cols:
        c.execute("ALTER TABLE paired_devices ADD COLUMN revoked_by_name TEXT DEFAULT ''")
    c.execute("""
    CREATE TABLE IF NOT EXISTS device_sync_handoffs (
        code TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        consumed_at REAL
    )
    """)

    # 6. 霸王餐订单表
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_key TEXT,
        order_sn TEXT UNIQUE,
        platform_order_id TEXT,
        store_id TEXT,
        store_name TEXT,
        platform TEXT DEFAULT 'meituan',
        order_money REAL DEFAULT 0,
        rebate_money REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        condition TEXT DEFAULT '无需评价',
        receipt_img TEXT,
        reject_reason TEXT,
        expire_time TEXT,
        created_at TEXT,
        updated_at TEXT,
        promotion_order_id INTEGER DEFAULT 0
    )
    """)

    # 已删除订单墓碑：官方接口仍会返回用户已删除的历史订单，用墓碑阻止重新同步入库
    c.execute("""
    CREATE TABLE IF NOT EXISTS deleted_orders (
        order_sn TEXT PRIMARY KEY,
        deleted_at TEXT
    )
    """)

    # 7. 美团官方账号表 (多账号独立管理，支持扫码登录与历史池)
    c.execute("""
    CREATE TABLE IF NOT EXISTS meituan_accounts (
        key TEXT PRIMARY KEY,
        nickname TEXT DEFAULT '美团用户',
        avatar TEXT DEFAULT '',
        token TEXT,
        saved_at INTEGER DEFAULT 0,
        last_claimed_at INTEGER DEFAULT 0,
        last_claimed_count INTEGER DEFAULT 0,
        last_claimed_details TEXT DEFAULT '[]',
        is_active INTEGER DEFAULT 1,
        history_pool TEXT DEFAULT '[]',
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 动态检查补充 orders 字段
    cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
    if "promotion_order_id" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN promotion_order_id INTEGER DEFAULT 0")
    if "order_time" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN order_time INTEGER DEFAULT 0")
    if "store_icon" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN store_icon TEXT DEFAULT ''")
    if "redpack_reward_num" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN redpack_reward_num REAL DEFAULT 0")
    if "timeout_time" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN timeout_time INTEGER DEFAULT 0")
    if "original_user_rebate" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN original_user_rebate REAL DEFAULT 0")
    if "order_type" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN order_type INTEGER DEFAULT 0")
    if "rebate_ratio" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN rebate_ratio REAL DEFAULT 0")
    if "delay_count" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN delay_count INTEGER DEFAULT 0")
    if "delay_card_used_count" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN delay_card_used_count INTEGER DEFAULT 0")
    if "vip_extra_silk" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN vip_extra_silk INTEGER DEFAULT 0")
    if "vip_extra_silk_radio" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN vip_extra_silk_radio REAL DEFAULT 0")
    if "official_reduce" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN official_reduce TEXT DEFAULT ''")
    if "official_order_desc" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN official_order_desc TEXT DEFAULT ''")
    if "coupon_bonus" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN coupon_bonus REAL DEFAULT 0")
    if "total_rebate" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN total_rebate REAL DEFAULT 0")
    if "vip_extra_reward" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN vip_extra_reward REAL DEFAULT 0")
    if "receipt_uploaded_at" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN receipt_uploaded_at TEXT DEFAULT ''")
    if "expected_rebate" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN expected_rebate REAL DEFAULT 0")
    if "actual_paid_amount" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN actual_paid_amount REAL DEFAULT 0")
    if "threshold_shortfall" not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN threshold_shortfall REAL DEFAULT 0")
    apt_cols = [r[1] for r in c.execute("PRAGMA table_info(store_appointments)").fetchall()]
    if "auto_use_best_vip_card" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN auto_use_best_vip_card INTEGER DEFAULT 1")
    if "min_rebate_gap" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN min_rebate_gap REAL DEFAULT 0")
    if "high_rebate_only" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN high_rebate_only INTEGER DEFAULT 0")
    if "store_category" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN store_category TEXT DEFAULT ''")
    if "rebate_card_name" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN rebate_card_name TEXT DEFAULT ''")

    # 自动自愈 orders 中缺失 store_icon 的记录 (从已有历史同名/同 store_id 记录回填)
    try:
        c.execute("""
            UPDATE orders
            SET store_icon = (
                SELECT o2.store_icon FROM orders o2
                WHERE (o2.store_id = orders.store_id OR o2.store_name = orders.store_name)
                  AND o2.store_icon IS NOT NULL
                  AND o2.store_icon != ''
                LIMIT 1
            )
            WHERE (store_icon IS NULL OR store_icon = '')
        """)
    except Exception:
        pass

    # 动态检查补充 store_appointments 调度与监控字段
    apt_cols = [r[1] for r in c.execute("PRAGMA table_info(store_appointments)").fetchall()]
    if "task_type" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN task_type TEXT DEFAULT 'countdown'")
    if "start_time" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN start_time TEXT")
    if "until_time" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN until_time TEXT")
    if "notified_31m" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN notified_31m INTEGER DEFAULT 0")
    if "notified_1m" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN notified_1m INTEGER DEFAULT 0")
    if "check_interval" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN check_interval INTEGER DEFAULT 5")
    if "platform" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN platform TEXT DEFAULT 'meituan'")
    if "order_money" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN order_money REAL DEFAULT 0")
    if "rebate_price" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN rebate_price REAL DEFAULT 0")
    if "rebate_desc" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN rebate_desc TEXT")
    if "rebate_type" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN rebate_type TEXT DEFAULT 'fixed'")
    if "last_checked_at" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN last_checked_at TEXT")
    if "log_id" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN log_id INTEGER DEFAULT 0")
    if "store_icon" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN store_icon TEXT DEFAULT ''")
    if "use_advance_card" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN use_advance_card INTEGER DEFAULT 0")
    if "redpack_id" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN redpack_id TEXT DEFAULT ''")
    if "redpack_name" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN redpack_name TEXT DEFAULT ''")
    if "keyword" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN keyword TEXT DEFAULT ''")
    if "match_mode" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN match_mode TEXT DEFAULT 'contains'")
    if "listen_mode" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN listen_mode TEXT DEFAULT 'store'")
    if "activity_requirement" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN activity_requirement TEXT DEFAULT 'all'")
    if "min_rebate_price" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN min_rebate_price REAL DEFAULT 0")
    if "min_rebate_rate" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN min_rebate_rate REAL DEFAULT 0")
    if "rebate_mode_filter" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN rebate_mode_filter TEXT DEFAULT 'all'")
    if "auto_stop_on_success" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN auto_stop_on_success INTEGER DEFAULT 1")
    if "max_order_money" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN max_order_money REAL DEFAULT 0")
    if "distance_range" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN distance_range TEXT DEFAULT ''")
    if "max_distance_km" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN max_distance_km REAL DEFAULT 0")
    if "is_saved" not in apt_cols:
        c.execute("ALTER TABLE store_appointments ADD COLUMN is_saved INTEGER DEFAULT 0")

    # 自动自愈 store_appointments 中缺失 store_icon 的记录 (从 orders 表或同店名同ID回填)
    try:
        c.execute("""
            UPDATE store_appointments
            SET store_icon = (
                SELECT o.store_icon FROM orders o
                WHERE (o.store_id = store_appointments.store_id OR o.store_name = store_appointments.store_name)
                  AND o.store_icon IS NOT NULL
                  AND o.store_icon != ''
                LIMIT 1
            )
            WHERE (store_icon IS NULL OR store_icon = '')
        """)
    except Exception:
        pass

    # 历史 daily 综合任务平滑迁移至 yb_task，并清理已废弃的 yb_sign 配置
    try:
        daily_enabled_keys = [
            r[0] for r in c.execute("SELECT account_key FROM task_configs WHERE task_id = 'daily' AND enabled = 1").fetchall()
        ]
        for a_key in daily_enabled_keys:
            c.execute("""
                INSERT INTO task_configs (account_key, task_id, enabled, cron_time, params)
                VALUES (?, 'yb_task', 1, '08:05', '{}')
                ON CONFLICT(account_key, task_id) DO UPDATE SET enabled = 1
            """, (a_key,))
        c.execute("UPDATE task_configs SET enabled = 0 WHERE task_id = 'daily'")
        c.execute("DELETE FROM task_configs WHERE task_id = 'yb_sign'")
    except Exception:
        pass

    # 一次性迁移：清洗历史默认武汉占位定位（无 address_name 且坐标为旧默认 114.305393, 30.593099），强制引导用户绑定真实地址
    try:
        cleaned_flag = c.execute(
            "SELECT value FROM settings WHERE key = 'location_default_cleanup_v1'"
        ).fetchone()
        if not cleaned_flag:
            c.execute("""
                UPDATE accounts
                SET city_code = 0,
                    city_name = '',
                    longitude = '',
                    latitude = '',
                    address_name = ''
                WHERE COALESCE(address_name, '') = ''
                  AND COALESCE(longitude, '') = '114.305393'
                  AND COALESCE(latitude, '') = '30.593099'
            """)
            c.execute("""
                INSERT INTO settings (key, value)
                VALUES ('location_default_cleanup_v1', '1')
                ON CONFLICT(key) DO UPDATE SET value = '1'
            """)
    except Exception:
        pass

    # 自愈修复：将异常关机或超时残留的 running 孤儿日志自动更新为 aborted
    try:
        c.execute("""
            UPDATE job_logs 
            SET status = 'aborted', 
                output = output || char(10) || '[系统自愈] 服务重启或执行中断，挂起状态已解除。'
            WHERE status = 'running'
        """)
    except Exception:
        pass

    try:
        c.execute("""
            DELETE FROM orders WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id, promotion_order_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY promotion_order_id 
                               ORDER BY (platform_order_id != '') DESC, (status != 'pending') DESC, id DESC
                           ) as rn
                    FROM orders
                    WHERE promotion_order_id > 0
                ) WHERE rn = 1
            ) AND promotion_order_id > 0 AND promotion_order_id IN (
                SELECT promotion_order_id FROM orders WHERE promotion_order_id > 0 GROUP BY promotion_order_id HAVING COUNT(*) > 1
            )
        """)
    except Exception:
        pass

    # 自动自愈：系统启动时，将历史异常退出或重启遗留的处于 running 状态的孤儿任务置为 aborted
    try:
        now_time = time_service.format_now()
        running_logs = c.execute("SELECT id, output FROM job_logs WHERE status = 'running'").fetchall()
        for r in running_logs:
            lid = r[0]
            out = r[1] or ""
            tail_msg = f"\n[{now_time}] 服务重启自愈: 系统服务已重启，历史执行中任务已自动置为中断终止。"
            c.execute("UPDATE job_logs SET status = 'aborted', output = ? WHERE id = ?", (out.rstrip() + tail_msg, lid))
    except Exception:
        pass

    # 账号平台标识自愈：确保所有小蚕账号 (key LIKE 'acc_%') 的 platform 始终为 'xiaocan'，严禁被篡改
    c.execute("UPDATE accounts SET platform = 'xiaocan' WHERE key LIKE 'acc_%'")

    # 仅将独立美团账号 (key LIKE 'mt_%') 同步至 accounts 表（若不存在），绝不覆盖小蚕账号
    try:
        mt_rows = c.execute("SELECT * FROM meituan_accounts WHERE key LIKE 'mt_%'").fetchall()
        for r in mt_rows:
            m = dict(r)
            m_key = m["key"]
            chk = c.execute("SELECT key FROM accounts WHERE key = ?", (m_key,)).fetchone()
            if not chk:
                c.execute("""
                    INSERT INTO accounts (key, nickname, avatar, token, platform, is_active, saved_at, last_claimed_at, last_claimed_count, last_claimed_details, history_pool, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'meituan', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    m_key,
                    m.get("nickname") or "美团用户",
                    m.get("avatar") or "",
                    m.get("token") or "",
                    int(m.get("is_active", 1)),
                    int(m.get("saved_at", 0)),
                    int(m.get("last_claimed_at", 0)),
                    int(m.get("last_claimed_count", 0)),
                    m.get("last_claimed_details") or "[]",
                    m.get("history_pool") or "[]",
                    m.get("created_at") or time_service.format_now_dt(),
                    m.get("updated_at") or time_service.format_now_dt()
                ))
    except Exception:
        pass

    conn.commit()
    conn.close()


# 初始化建表
init_db()


# ---------------- 数据库便捷操作接口 ---------------- #

def _format_account_row(d: Dict[str, Any]) -> Dict[str, Any]:
    """统一解析账号字段中的 JSON 数据与默认平台标识"""
    if isinstance(d.get("last_claimed_details"), str):
        try:
            d["last_claimed_details"] = json.loads(d["last_claimed_details"])
        except Exception:
            d["last_claimed_details"] = []
    elif not d.get("last_claimed_details"):
        d["last_claimed_details"] = []
    if isinstance(d.get("history_pool"), str):
        try:
            d["history_pool"] = json.loads(d["history_pool"])
        except Exception:
            d["history_pool"] = []
    elif not d.get("history_pool"):
        d["history_pool"] = []
    if isinstance(d.get("meituan_last_claimed_details"), str):
        try:
            d["meituan_last_claimed_details"] = json.loads(d["meituan_last_claimed_details"])
        except Exception:
            d["meituan_last_claimed_details"] = []
    elif not d.get("meituan_last_claimed_details"):
        d["meituan_last_claimed_details"] = []
    if isinstance(d.get("meituan_history_pool"), str):
        try:
            d["meituan_history_pool"] = json.loads(d["meituan_history_pool"])
        except Exception:
            d["meituan_history_pool"] = []
    elif not d.get("meituan_history_pool"):
        d["meituan_history_pool"] = []
    if not d.get("platform"):
        d["platform"] = "xiaocan"

    # 计算与解析凭据有效状态
    is_expired = False
    exp_str = d.get("expires_at")
    if exp_str and exp_str not in ("长期有效", "无"):
        try:
            if time_service.parse_ts(exp_str, "%Y-%m-%d %H:%M:%S") < time_service.now_ts():
                is_expired = True
        except Exception:
            pass
    elif not exp_str and d.get("token") and "." in str(d["token"]):
        try:
            import base64
            parts = str(d["token"]).split(".")
            if len(parts) >= 2:
                b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                payload = json.loads(base64.urlsafe_b64decode(b64.encode()).decode("utf-8"))
                if payload.get("exp"):
                    exp_ts = int(payload["exp"])
                    d["expires_at"] = time_service.format_ts(exp_ts, "%Y-%m-%d %H:%M:%S")
                    if exp_ts < time_service.now_ts():
                        is_expired = True
        except Exception:
            pass
    d["is_token_expired"] = is_expired
    d["has_location"] = has_valid_location(d)
    return d


def get_all_accounts() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM accounts WHERE platform != 'meituan' ORDER BY created_at DESC").fetchall()
        return [_format_account_row(dict(r)) for r in rows]


def get_account_by_key(key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE key = ?", (key,)).fetchone()
        return _format_account_row(dict(row)) if row else None


get_account = get_account_by_key


def find_account(
    key: Optional[str] = None,
    silk_id: Optional[str] = None,
    user_id: Optional[str] = None,
    token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    # 根据 key, user_id, silk_id 或 token 查找已存在的小蚕账号，避免重复入库
    with get_conn() as conn:
        if key and str(key).strip():
            row = conn.execute("SELECT * FROM accounts WHERE key = ?", (str(key).strip(),)).fetchone()
            if row:
                return dict(row)
        if user_id and str(user_id).strip():
            row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (str(user_id).strip(),)).fetchone()
            if row:
                return dict(row)
        if silk_id and str(silk_id).strip():
            row = conn.execute("SELECT * FROM accounts WHERE silk_id = ?", (str(silk_id).strip(),)).fetchone()
            if row:
                return dict(row)
        if token and str(token).strip():
            row = conn.execute("SELECT * FROM accounts WHERE token = ?", (str(token).strip(),)).fetchone()
            if row:
                return dict(row)
            # 尝试从传入的 token 解码 UserId 并查重
            try:
                from ..core.jwt_utils import decode_jwt_payload, extract_user_id_from_payload
                _, p, _ = decode_jwt_payload(str(token).strip())
                jwt_uid = extract_user_id_from_payload(p)
                if jwt_uid:
                    row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (jwt_uid,)).fetchone()
                    if row:
                        return dict(row)
            except Exception:
                pass
    return None


def has_valid_location(acc: Optional[Dict[str, Any]]) -> bool:
    """校验账号是否已绑定完整有效的定位地址（城市代码、城市名、非零合法经纬度）"""
    if not isinstance(acc, dict):
        return False
    try:
        city_code = int(acc.get("city_code") or 0)
    except (TypeError, ValueError):
        return False
    if city_code <= 0:
        return False
    city_name = str(acc.get("city_name") or "").strip()
    if not city_name or city_name == "未知":
        return False
    lon_str = str(acc.get("longitude") or "").strip()
    lat_str = str(acc.get("latitude") or "").strip()
    if not lon_str or not lat_str:
        return False
    try:
        lon = float(lon_str)
        lat = float(lat_str)
    except (TypeError, ValueError):
        return False
    if lon == 0.0 or lat == 0.0:
        return False
    return -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0


def save_account(data: Dict[str, Any]) -> Dict[str, Any]:
    """保存或更新小蚕账号，具备完善的查重合并与用户配置保护能力"""
    now = time_service.format_now_dt()

    # 尝试自动从 JWT 提取真实的 UserId、Silk ID、有效期
    token = (data.get("token") or "").strip()
    user_id = str(data.get("user_id") or "").strip()
    silk_id = str(data.get("silk_id") or "").strip()
    exp_time = data.get("expires_at")

    if token:
        try:
            from ..core.jwt_utils import decode_jwt_payload, extract_user_id_from_payload, extract_silk_id_from_payload
            is_valid, payload, _ = decode_jwt_payload(token)
            if is_valid and payload:
                if not user_id:
                    user_id = extract_user_id_from_payload(payload)
                if not silk_id:
                    silk_id = extract_silk_id_from_payload(payload)
                exp = payload.get("exp")
                if exp and not exp_time:
                    exp_time = time_service.format_ts(int(exp), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # 查找已有账号以实现无缝去重更新 (通过 key / user_id / silk_id / token 全方位查重)
    existing = find_account(
        key=data.get("key"),
        silk_id=silk_id,
        user_id=user_id,
        token=token
    )

    # 确定唯一稳定的 key：优先沿用已有 key，否则以 user_id 或 silk_id 命名保证幂等
    if existing:
        key = existing["key"]
    elif data.get("key"):
        key = data["key"]
    elif user_id:
        key = f"acc_{user_id}"
    elif silk_id:
        key = f"acc_{silk_id}"
    else:
        key = f"acc_{uuid.uuid4().hex[:8]}"

    # 昵称保护：过滤抓包/WAF 页面误识别文案，避免“腾讯验证码”等污染任务执行账号。
    def _valid_nickname(value: Any) -> bool:
        text = str(value or "").strip()
        lowered = text.lower()
        return bool(text) and lowered not in INVALID_ACCOUNT_NICKNAMES and not any(
            token in lowered for token in ("验证码", "waf", "stgw", "风控", "拦截")
        )

    candidate_nickname = data.get("nickname")
    existing_nickname = existing.get("nickname") if existing else ""
    nickname = candidate_nickname if _valid_nickname(candidate_nickname) else ""
    if not nickname and _valid_nickname(existing_nickname):
        nickname = existing_nickname
    if not nickname:
        suffix = user_id or silk_id or key.split("_")[-1]
        nickname = f"小蚕用户_{str(suffix)[-4:]}"

    # 头像保护
    avatar = data.get("avatar") or (existing.get("avatar") if existing else "")

    # 会员等级与 PLUS 标识（严格对齐小蚕官方 vip_level_info 结构）
    vip_level = data.get("vip_level") or (existing.get("vip_level") if existing else 1)
    is_plus = int(data.get("is_plus", existing.get("is_plus", 0) if existing else 0))
    vip_score = data.get("vip_score") or (existing.get("vip_score") if existing else 0)
    vip_expired_at = data.get("vip_expired_at") or (existing.get("vip_expired_at") if existing else 0)
    phone = data.get("phone") or (existing.get("phone") if existing else "")
    real_name = data.get("real_name") or (existing.get("real_name") if existing else "")
    nick_name = data.get("nick_name") or (existing.get("nick_name") if existing else "")

    # 城市与定位保护：禁止任何默认城市/坐标兜底；仅接受完整合法坐标绑定或保留已有合法绑定
    has_existing_loc = bool(existing and has_valid_location(existing))
    if has_valid_location(data):
        city_code = int(data["city_code"])
        city_name = str(data["city_name"]).strip()
        longitude = str(data["longitude"]).strip()
        latitude = str(data["latitude"]).strip()
        address_name = str(data.get("address_name") or "").strip()
        short_name = str(data.get("short_name") or "").strip() or address_name
        full_address = str(data.get("full_address") or "").strip() or address_name
        location_source = str(data.get("location_source") or "").strip()
        location_source_name = str(data.get("location_source_name") or "").strip()
    elif has_existing_loc and existing is not None:
        city_code = int(existing["city_code"])
        city_name = str(existing["city_name"]).strip()
        longitude = str(existing["longitude"]).strip()
        latitude = str(existing["latitude"]).strip()
        address_name = str(existing.get("address_name") or "").strip()
        short_name = str(existing.get("short_name") or "").strip() or address_name
        full_address = str(existing.get("full_address") or "").strip() or address_name
        location_source = str(existing.get("location_source") or "").strip()
        location_source_name = str(existing.get("location_source_name") or "").strip()
    else:
        city_code = 0
        city_name = ""
        longitude = ""
        latitude = ""
        address_name = ""
        short_name = ""
        full_address = ""
        location_source = ""
        location_source_name = ""

    # 真实官方资产字段保护
    silk = int(data.get("silk", existing.get("silk", 0) if existing else 0))
    withdrawing = int(data.get("withdrawing", existing.get("withdrawing", 0) if existing else 0))
    withdraw_total = int(data.get("withdraw_total", existing.get("withdraw_total", 0) if existing else 0))
    completed_number = int(data.get("completed_number", existing.get("completed_number", 0) if existing else 0))
    yb_point = int(data.get("yb_point", existing.get("yb_point", 0) if existing else 0))
    unreceived_points = int(data.get("unreceived_points", existing.get("unreceived_points", 0) if existing else 0))

    # Silk ID 补全保护：若已有存在 silk_id，新包缺失时予以保留
    final_silk_id = silk_id or (existing.get("silk_id") if existing else "")
    final_user_id = user_id or (existing.get("user_id") if existing else "")
    final_token = token or (existing.get("token") if existing else "")
    final_expires_at = exp_time or (existing.get("expires_at") if existing else "2099-12-31")
    client_mode = data.get("client_mode") or (existing.get("client_mode") if existing else "app")
    created_at = existing.get("created_at") if existing else data.get("created_at", now)

    with get_conn() as conn:
        conn.execute("""
        INSERT INTO accounts (key, user_id, silk_id, nickname, avatar, token, vip_level, is_plus, phone, real_name, nick_name, vip_score, vip_expired_at, silk, withdrawing, withdraw_total, completed_number, yb_point, unreceived_points, city_code, city_name, longitude, latitude, address_name, short_name, full_address, location_source, location_source_name, location_remark, last_official_sync, expires_at, client_mode, is_active, created_at, updated_at)
        VALUES (:key, :user_id, :silk_id, :nickname, :avatar, :token, :vip_level, :is_plus, :phone, :real_name, :nick_name, :vip_score, :vip_expired_at, :silk, :withdrawing, :withdraw_total, :completed_number, :yb_point, :unreceived_points, :city_code, :city_name, :longitude, :latitude, :address_name, :short_name, :full_address, :location_source, :location_source_name, :location_remark, :last_official_sync, :expires_at, :client_mode, :is_active, :created_at, :updated_at)
        ON CONFLICT(key) DO UPDATE SET
            user_id=excluded.user_id,
            silk_id=CASE WHEN excluded.silk_id != '' THEN excluded.silk_id ELSE accounts.silk_id END,
            nickname=excluded.nickname,
            avatar=excluded.avatar,
            token=excluded.token,
            vip_level=excluded.vip_level,
            is_plus=excluded.is_plus,
            phone=excluded.phone,
            real_name=excluded.real_name,
            nick_name=excluded.nick_name,
            vip_score=excluded.vip_score,
            vip_expired_at=excluded.vip_expired_at,
            silk=excluded.silk,
            withdrawing=excluded.withdrawing,
            withdraw_total=excluded.withdraw_total,
            completed_number=excluded.completed_number,
            yb_point=excluded.yb_point,
            unreceived_points=excluded.unreceived_points,
            city_code=excluded.city_code,
            city_name=excluded.city_name,
            longitude=excluded.longitude,
            latitude=excluded.latitude,
            address_name=excluded.address_name,
            short_name=excluded.short_name,
            full_address=excluded.full_address,
            location_source=excluded.location_source,
            location_source_name=excluded.location_source_name,
            location_remark=excluded.location_remark,
            last_official_sync=COALESCE(excluded.last_official_sync, accounts.last_official_sync),
            expires_at=excluded.expires_at,
            client_mode=COALESCE(excluded.client_mode, accounts.client_mode),
            is_active=1,
            updated_at=excluded.updated_at
        """, {
            "key": key,
            "user_id": final_user_id,
            "silk_id": final_silk_id,
            "nickname": nickname,
            "avatar": avatar,
            "token": final_token,
            "vip_level": vip_level,
            "is_plus": is_plus,
            "phone": phone,
            "real_name": real_name,
            "nick_name": nick_name,
            "vip_score": vip_score,
            "vip_expired_at": vip_expired_at,
            "silk": silk,
            "withdrawing": withdrawing,
            "withdraw_total": withdraw_total,
            "completed_number": completed_number,
            "yb_point": yb_point,
            "unreceived_points": unreceived_points,
            "city_code": city_code,
            "city_name": city_name,
            "longitude": longitude,
            "latitude": latitude,
            "address_name": address_name,
            "short_name": short_name,
            "full_address": full_address,
            "location_source": location_source,
            "location_source_name": location_source_name,
            "location_remark": str(data.get("location_remark") or (existing.get("location_remark") if existing else "") or "")[:40],
            "last_official_sync": float(data.get("last_official_sync") or (existing.get("last_official_sync") if existing else 0) or 0),
            "expires_at": final_expires_at,
            "client_mode": client_mode,
            "is_active": 1,
            "created_at": created_at,
            "updated_at": now
        })
        # 如果本次写入有 user_id，同时清理其他可能同属于同一个 user_id 的旧 key 重复行！
        if final_user_id:
            conn.execute("DELETE FROM accounts WHERE user_id = ? AND key != ?", (final_user_id, key))
        conn.commit()

    saved = get_account_by_key(key)
    if saved:
        saved["is_updated"] = bool(existing)
    return saved


def update_account_profile(key: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新账号资料字段 (严格对齐官方字段)"""
    allowed_fields = [
        "silk_id", "nickname", "avatar", "vip_level", "is_plus",
        "phone", "real_name", "vip_score", "vip_expired_at",
        "silk", "withdrawing", "withdraw_total", "completed_number",
        "yb_point", "unreceived_points",
        "city_code", "city_name", "expires_at", "longitude", "latitude", "address_name", "short_name", "full_address", "location_source", "location_source_name", "location_remark", "last_official_sync",
        "notify_mode", "notify_config", "client_mode",
        "meituan_token", "meituan_nickname", "meituan_saved_at",
        "meituan_last_claimed_at", "meituan_last_claimed_count",
        "meituan_last_claimed_details", "meituan_history_pool", "meituan_is_active"
    ]
    updates = []
    params = {"key": key, "updated_at": time_service.format_now_dt()}
    for field in allowed_fields:
        if field in profile:
            updates.append(f"{field} = :{field}")
            params[field] = profile[field]
    if not updates:
        return get_account_by_key(key)

    sql = f"UPDATE accounts SET {', '.join(updates)}, updated_at = :updated_at WHERE key = :key"
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()
    return get_account_by_key(key)


def update_account(key: str, **kwargs) -> Optional[Dict[str, Any]]:
    """更新账号资料字段便捷包装器 (兼容 update_account 命名)"""
    return update_account_profile(key, kwargs)


def get_account_notify_config(key: str) -> Dict[str, Any]:
    """获取指定账号的通知模式及配置"""
    acc = get_account_by_key(key)
    if not acc:
        return {"notify_mode": "global", "notify_config": {}}
    mode = acc.get("notify_mode") or "global"
    raw_cfg = acc.get("notify_config") or "{}"
    cfg = {}
    if isinstance(raw_cfg, str) and raw_cfg.strip():
        try:
            cfg = json.loads(raw_cfg)
        except Exception:
            cfg = {}
    elif isinstance(raw_cfg, dict):
        cfg = raw_cfg
    return {"notify_mode": mode, "notify_config": cfg}


def set_account_notify_config(key: str, mode: str, config: Dict[str, Any]) -> bool:
    """更新指定账号的通知模式及配置"""
    cfg_str = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else str(config or "{}")
    res = update_account_profile(key, {
        "notify_mode": mode or "global",
        "notify_config": cfg_str
    })
    return res is not None



def delete_account(key: str) -> bool:
    """级联物理彻底删除账号及一切关联数据，杜绝任何历史孤儿残留"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE key = ?", (key,)).fetchone()
        silk_id = ""
        user_id = ""
        if row:
            acc_data = dict(row)
            silk_id = str(acc_data.get("silk_id") or "")
            user_id = str(acc_data.get("user_id") or "")

        keys_to_clean = {key}
        if silk_id:
            keys_to_clean.add(f"acc_{silk_id}")
            keys_to_clean.add(silk_id)
        if user_id:
            keys_to_clean.add(f"acc_{user_id}")
            keys_to_clean.add(user_id)

        # 1. 账号主表
        conn.execute("DELETE FROM accounts WHERE key = ?", (key,))

        # 2. 美团账号凭证与配置
        for k in keys_to_clean:
            conn.execute("DELETE FROM meituan_accounts WHERE key = ?", (k,))

        # 3. 任务配置
        for k in keys_to_clean:
            conn.execute("DELETE FROM task_configs WHERE account_key = ?", (k,))

        # 4. 订单历史
        for k in keys_to_clean:
            conn.execute("DELETE FROM orders WHERE account_key = ?", (k,))

        # 5. 抢店预约
        for k in keys_to_clean:
            conn.execute("DELETE FROM store_appointments WHERE account_key = ?", (k,))

        # 6. 任务执行日志与流水
        for k in keys_to_clean:
            conn.execute("DELETE FROM job_logs WHERE account_key = ?", (k,))

        # 7. settings 表中的快照与缓存
        for k in keys_to_clean:
            if k:
                conn.execute("DELETE FROM settings WHERE key LIKE ?", (f"%{k}%",))

        conn.commit()
        return True


def get_task_configs(account_key: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM task_configs WHERE account_key = ?", (account_key,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("params"), str):
                try:
                    d["params"] = json.loads(d["params"])
                except Exception:
                    d["params"] = {}
            elif not d.get("params"):
                d["params"] = {}
            result.append(d)
        return result


def save_task_config(account_key: str, task_id: str, enabled: bool, cron_time: Optional[str] = None, params: Optional[Dict[str, Any]] = None):
    with get_conn() as conn:
        params_str = json.dumps(params) if params is not None else None
        conn.execute("""
        INSERT INTO task_configs (account_key, task_id, enabled, cron_time, params)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(account_key, task_id) DO UPDATE SET
            enabled=excluded.enabled,
            cron_time=COALESCE(excluded.cron_time, task_configs.cron_time),
            params=COALESCE(excluded.params, task_configs.params)
        """, (account_key, task_id, 1 if enabled else 0, cron_time, params_str))
        conn.commit()


def summarize_job_result(output: str, status: str = "") -> str:
    """从执行步骤输出中抽取真实执行结果，作为「执行结果」字段。

    优先级：官方/执行异常 > 业务跳过或条件不满足 > 具体成功事件 > 通用完成文案。
    这样即使任务整体状态为成功，也能在列表中直接看到“余额不足/资格拦截/名额售罄”等真实原因，
    不会被最后一行「处理完毕」覆盖。
    """
    lines = [ln.strip() for ln in (output or "").split("\n") if ln.strip()]
    if not lines:
        return "无执行输出"

    def clean(line: str) -> str:
        return line.split("] ", 1)[-1] if line.startswith("[") else line

    normalized_status = str(status or "").strip().lower()
    error_keys = (
        "HTTP 403", "HTTP 429", "WAF", "STGW", "STGM", "风控", "拦截",
        "返回失败", "错误码", "异常:", "异常 ", "接口返回失败", "被拒绝", "冷却",
        "账户校验", "未达到", "不满足", "无资格", "权限不足", "暂不可用",
        "条件不足", "未开通", "未绑定", "缺少有效", "失败", "出错", "中断",
        "查询失败", "核验失败", "获取失败", "领取失败", "调用失败", "提交失败",
    )
    # 这些属于“任务正常结束但业务未执行”，状态可保持成功，结果必须明确展示原因。
    skip_keys = (
        "跳过提现", "自动跳过", "已安全跳过", "本次跳过", "无需重复",
        "低于门槛", "超过可用余额", "余额不足", "元宝不足", "已达上限", "达到上限",
        "未中签", "未命中", "未分配到有效红包", "库存告罄", "已售罄", "名额已发完",
        "名额已用完", "已领完", "无待收取", "暂无待开启", "暂无生效中的红包雨活动场次",
        "当前暂无满足条件的剩余名额", "暂无即将", "长期有效", "状态良好",
        "资格拦截", "等级预警", "暂无资格", "缺少资格", "今日已完成", "今日已签到",
        "今日已提现", "继续余额核验", "领取上限", "状态码 1014",
    )
    generic_keys = ("处理完毕", "执行完成 (无异常)", "开始执行")

    for line in reversed(lines):
        if any(k in line for k in error_keys):
            return clean(line)

    if normalized_status not in ("success", ""):
        for line in reversed(lines):
            if any(k in line for k in skip_keys) and not any(k in line for k in generic_keys):
                return clean(line)

    for line in reversed(lines):
        if any(k in line for k in skip_keys) and not any(k in line for k in generic_keys):
            return clean(line)

    success_keys = (
        "成功锁定", "抢单成功", "成功入库", "领取成功", "打卡成功",
        "成功获取定位", "提现申请已提交", "奖励已入账", "同步成功",
    )
    for line in reversed(lines):
        if any(k in line for k in success_keys):
            return clean(line)

    for line in reversed(lines):
        if not any(k in line for k in generic_keys):
            return clean(line)

    for line in reversed(lines):
        if "处理完毕" in line or "执行完成" in line:
            return clean(line)
    return "—"


INVALID_ACCOUNT_NICKNAMES = {
    "system", "all", "unknown", "默认账号", "系统", "系统任务", "全局任务",
    "腾讯验证码", "验证码", "验证", "waf", "stgw", "风控拦截",
}


def _normalize_log_account(account_key: str) -> Tuple[str, str, str]:
    """返回日志的稳定账号 key、显示名和类型，避免昵称污染显示。"""
    key = str(account_key or "").strip()
    if not key or key in ("system", "all", "__system__", "__global__"):
        return "", "系统任务", "system"

    row = None
    with get_conn() as conn:
        row = conn.execute("SELECT key, nickname FROM accounts WHERE key = ? LIMIT 1", (key,)).fetchone()
    if not row:
        return key, "历史任务", "unknown"

    nickname = str(row["nickname"] or "").strip()
    lowered = nickname.lower()
    if not nickname or lowered in INVALID_ACCOUNT_NICKNAMES or any(
        token in lowered for token in ("验证码", "waf", "stgw", "风控", "拦截")
    ):
        suffix = key.split("_")[-1] if "_" in key else key
        nickname = f"账号 {suffix[:8]}"
    return key, nickname, "user"


def add_job_log(job_id: str, account_key: str, task_id: str, status: str, output: str, result: str = "") -> int:
    now = time_service.format_now_dt()
    final_result = result or summarize_job_result(output, status)
    stable_key, account_name, account_type = _normalize_log_account(account_key)
    with get_conn() as conn:
        cur = conn.execute("""
        INSERT INTO job_logs (job_id, account_key, task_id, status, output, result, account_name, account_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (job_id, stable_key, task_id, status, output, final_result, account_name, account_type, now))
        conn.commit()
        return cur.lastrowid


def append_job_log_note(log_id: int, text: str, fallback_status: str = "error") -> bool:
    """追加日志说明；已成功完成的任务不得被后续删除/停止动作降级。"""
    if not log_id:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, result, output FROM job_logs WHERE id = ? LIMIT 1",
            (log_id,)
        ).fetchone()
        if not row:
            return False
        prev_status = str(row["status"] or "")
        new_output = ((row["output"] or "") + "\n" + str(text or "")).strip()
        if prev_status in ("success", "completed"):
            conn.execute(
                "UPDATE job_logs SET output = ?, result = ? WHERE id = ?",
                (new_output, row["result"] or summarize_job_result(new_output, prev_status), log_id)
            )
        else:
            conn.execute(
                "UPDATE job_logs SET status = ?, output = ?, result = ? WHERE id = ?",
                (fallback_status, new_output, summarize_job_result(new_output, fallback_status), log_id)
            )
        conn.commit()
        return True


def update_job_log(log_id: int, status: Optional[str] = None, output: Optional[str] = None, result: Optional[str] = None) -> bool:
    """动态更新某条日志的状态、详细步骤输出与执行结果"""
    if not log_id:
        return False
    updates = []
    vals = []
    if status is not None:
        updates.append("status = ?")
        vals.append(status)
    if output is not None:
        updates.append("output = ?")
        vals.append(output)
    if result is not None or output is not None:
        updates.append("result = ?")
        vals.append(result if result is not None else summarize_job_result(output or "", status or ""))
    if not updates:
        return False
    vals.append(log_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE job_logs SET {', '.join(updates)} WHERE id = ?", vals)
        conn.commit()
        return True


def auto_clean_stale_running_jobs():
    """运行时自愈：对于 running 状态超过 10 分钟未更新的普通短任务判定为超时僵尸任务，自动置为 aborted；但必须豁免合法长周期的预约与监听任务"""
    try:
        with get_conn() as conn:
            cur_ts = time_service.now_int()
            stale_threshold = 600  # 10 分钟
            # 1. 扫描处于 running 状态的任务，左连接 store_appointments 查验实际预约状态
            rows = conn.execute("""
            SELECT j.id, j.created_at, j.output, j.task_id, sa.status as apt_status
            FROM job_logs j
            LEFT JOIN store_appointments sa ON sa.log_id = j.id
            WHERE j.status = 'running'
            """).fetchall()
            for r in rows:
                task_id = r["task_id"]
                apt_status = r["apt_status"]
                # 豁免：若属于定时预约或名额监听等长周期任务，且对应预约依然处于活跃等待中，绝对严禁误杀
                if task_id in ("store_appoint", "store_monitor", "name_monitor", "keyword", "keyword_monitor"):
                    if apt_status in ("pending", "scheduled", "primed", "monitoring", "running") or apt_status is None:
                        continue

                c_at = r["created_at"]
                try:
                    c_ts = int(time_service.parse_ts(c_at, "%Y-%m-%d %H:%M:%S"))
                    if cur_ts - c_ts > stale_threshold:
                        old_out = r["output"] or ""
                        now_str = time_service.format_now()
                        new_out = old_out.rstrip() + f"\n[{now_str}] 执行超时自愈: 任务运行已超过 10 分钟未响应，已被系统自动置为中断终止。"
                        conn.execute("UPDATE job_logs SET status = 'aborted', output = ? WHERE id = ?", (new_out, r["id"]))
                except Exception:
                    pass

            # 2. 自愈纠正：若之前被误打为 aborted 但底层预约依然活跃的日志，自动恢复为 running 状态并清洗误判文本
            mis_aborted = conn.execute("""
            SELECT j.id, j.output
            FROM job_logs j
            JOIN store_appointments sa ON sa.log_id = j.id
            WHERE j.status = 'aborted' AND sa.status IN ('pending', 'scheduled', 'primed', 'monitoring', 'running')
            """).fetchall()
            for m in mis_aborted:
                m_out = m["output"] or ""
                # 剔除误杀日志中的执行超时自愈行
                clean_lines = [l for l in m_out.split("\n") if "执行超时自愈: 任务运行已超过 10 分钟未响应" not in l]
                conn.execute("UPDATE job_logs SET status = 'running', output = ? WHERE id = ?", ("\n".join(clean_lines).strip(), m["id"]))

            conn.commit()
    except Exception:
        pass


_JOB_STORE_TASK_IDS = (
    "store_grab", "store_appoint", "store_monitor", "store_keyword",
    "store_search", "store_cancel", "dual_rebate_scan", "dual_rebate_monitor",
)


def _build_job_log_filters(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if account_key:
        clauses.append("account_key = ?")
        params.append(account_key)
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if category == "store":
        placeholders = ",".join("?" for _ in _JOB_STORE_TASK_IDS)
        clauses.append(f"task_id IN ({placeholders})")
        params.extend(_JOB_STORE_TASK_IDS)
    elif category == "daily":
        placeholders = ",".join("?" for _ in _JOB_STORE_TASK_IDS)
        clauses.append(f"task_id NOT IN ({placeholders})")
        params.extend(_JOB_STORE_TASK_IDS)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def get_job_logs(
    account_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    auto_clean_stale_running_jobs()
    where, params = _build_job_log_filters(account_key, status, category)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM job_logs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def count_job_logs(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> int:
    where, params = _build_job_log_filters(account_key, status, category)
    with get_conn() as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM job_logs{where}", tuple(params)).fetchone()
        return int(row[0] if row else 0)


def clear_job_logs(account_key: Optional[str] = None):
    with get_conn() as conn:
        if account_key:
            conn.execute("DELETE FROM job_logs WHERE account_key = ?", (account_key,))
        else:
            conn.execute("DELETE FROM job_logs")
        conn.commit()


def get_appointments(account_key: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        if account_key:
            rows = conn.execute("SELECT * FROM store_appointments WHERE account_key = ? ORDER BY id DESC", (account_key,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM store_appointments ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_appointment_by_id(aid: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM store_appointments WHERE id = ?", (aid,)).fetchone()
        return dict(row) if row else None


def get_active_appointments() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("""
        SELECT * FROM store_appointments 
        WHERE status IN ('pending', 'scheduled', 'primed', 'monitoring')
          AND COALESCE(is_saved, 0) = 0
        ORDER BY id ASC
        """).fetchall()
        return [dict(r) for r in rows]


def add_appointment(data: Dict[str, Any]) -> int:
    now = time_service.format_now_dt()
    status = data.get("status")
    if not status:
        status = "monitoring" if data.get("task_type") in ("monitor", "name_monitor", "keyword") else "scheduled"

    store_icon = (data.get("store_icon") or data.get("icon") or "").strip()
    with get_conn() as conn:
        if not store_icon:
            s_id = str(data.get("store_id", "")).strip()
            s_name = (data.get("store_name") or "").strip()
            row = conn.execute(
                "SELECT store_icon FROM orders WHERE (store_id = ? OR store_name = ?) AND store_icon IS NOT NULL AND store_icon != '' LIMIT 1",
                (s_id, s_name)
            ).fetchone()
            if row and row["store_icon"]:
                store_icon = row["store_icon"]

        cur = conn.execute("""
        INSERT INTO store_appointments (
            account_key, store_id, store_name, store_icon, promotion_id, status, 
            early_ms, rebate_card_id, rebate_card_name, redpack_mode, outcome, created_at,
            task_type, start_time, until_time, notified_31m, notified_1m,
            check_interval, platform, order_money, rebate_price, rebate_desc, rebate_type, log_id,
            use_advance_card, redpack_id, redpack_name, auto_use_best_vip_card, min_rebate_gap,
            high_rebate_only, store_category,
            keyword, match_mode, listen_mode, activity_requirement, min_rebate_price, min_rebate_rate, rebate_mode_filter, auto_stop_on_success, max_order_money,
            distance_range, max_distance_km
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["account_key"],
            str(data.get("store_id", "")),
            data.get("store_name", "店铺活动"),
            store_icon,
            str(data["promotion_id"]),
            status,
            int(data.get("early_ms", 500)),
            str(data.get("rebate_card_id") or ""),
            str(data.get("rebate_card_name") or ""),
            int(data.get("redpack_mode", 0)),
            data.get("outcome", ""),
            now,
            data.get("task_type", "countdown"),
            data.get("start_time", ""),
            data.get("until_time", ""),
            int(data.get("notified_31m", 0)),
            int(data.get("notified_1m", 0)),
            int(data.get("check_interval", 5)),
            data.get("platform", "meituan"),
            float(data.get("order_money", 0.0)),
            float(data.get("rebate_price", 0.0)),
            data.get("rebate_desc", ""),
            data.get("rebate_type", "fixed"),
            int(data.get("log_id") or 0),
            int(data.get("use_advance_card") or 0),
            str(data.get("redpack_id") or ""),
            str(data.get("redpack_name") or ""),
            int(bool(data.get("auto_use_best_vip_card", True))),
            float(data.get("min_rebate_gap") or 0),
            int(bool(data.get("high_rebate_only"))),
            str(data.get("store_category") or ""),
            str(data.get("keyword") or ""),
            str(data.get("match_mode") or "contains"),
            str(data.get("listen_mode") or "store"),
            str(data.get("activity_requirement") or "all"),
            float(data.get("min_rebate_price") or 0.0),
            float(data.get("min_rebate_rate") or 0.0),
            str(data.get("rebate_mode_filter") or "all"),
            int(data.get("auto_stop_on_success") if data.get("auto_stop_on_success") is not None else 1),
            float(data.get("max_order_money") or 0.0),
            str(data.get("distance_range") or ""),
            float(data.get("max_distance_km") or 0.0)
        ))
        conn.commit()
        return cur.lastrowid


def update_appointment(aid: int, fields: Dict[str, Any]) -> bool:
    if not fields:
        return False
    keys = list(fields.keys())
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    vals = [fields[k] for k in keys] + [aid]
    with get_conn() as conn:
        conn.execute(f"UPDATE store_appointments SET {set_clause} WHERE id = ?", vals)
        conn.commit()
        return True


def delete_appointment(aid: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM store_appointments WHERE id = ?", (aid,))
        conn.commit()
        return True


def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default


def set_setting(key: str, value: Any):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, json.dumps(value)))
        conn.commit()


# ---------------- 设备协同接口 ---------------- #

def create_pair_ticket(ticket: str, ttl_seconds: int = 300, snapshot: Optional[Dict[str, Any]] = None) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO device_pair_tickets (ticket, status, created_at, expires_at, snapshot)
        VALUES (?, 'pending', ?, ?, ?)
        """, (ticket, now, now + ttl_seconds, json.dumps(snapshot or {}, ensure_ascii=False)))
        conn.commit()


def get_pair_ticket(ticket: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM device_pair_tickets WHERE ticket = ?", (ticket,)).fetchone()
        return dict(row) if row else None


def claim_pair_ticket(ticket: str, device_id: str, device_name: str, client_ip: str = "", user_agent: str = "") -> bool:
    """原子认领票据：仅 pending 且未过期可认领，防止同一票据被重复消费。"""
    with get_conn() as conn:
        cur = conn.execute("""
        UPDATE device_pair_tickets
        SET status = 'claimed', consumed_at = ?, device_id = ?, device_name = ?, client_ip = ?, user_agent = ?
        WHERE ticket = ? AND status = 'pending' AND expires_at > ?
        """, (time.time(), device_id, device_name, client_ip, user_agent, ticket, time.time()))
        conn.commit()
        return cur.rowcount > 0


def mark_pair_ticket_used(ticket: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE device_pair_tickets SET status = 'used' WHERE ticket = ?", (ticket,))
        conn.commit()


def save_paired_device(
    device_id: str,
    name: str,
    token_hash: str,
    client_ip: str = "",
    user_agent: str = "",
    peer_base_url: str = "",
    peer_name: str = "",
) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO paired_devices (id, name, token_hash, device_id, created_at, last_seen_at, revoked_at, client_ip, user_agent, peer_base_url, peer_name)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            token_hash = excluded.token_hash,
            device_id = excluded.device_id,
            last_seen_at = excluded.last_seen_at,
            revoked_at = 0,
            revoked_by_name = '',
            client_ip = excluded.client_ip,
            user_agent = excluded.user_agent,
            peer_base_url = excluded.peer_base_url,
            peer_name = excluded.peer_name
        """, (device_id, name, token_hash, device_id, now, now, client_ip, user_agent, str(peer_base_url or ""), str(peer_name or "")))
        conn.commit()


def list_paired_devices() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM paired_devices ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_paired_device_by_token_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM paired_devices WHERE token_hash = ?", (token_hash,)).fetchone()
        return dict(row) if row else None


def get_paired_device(device_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM paired_devices WHERE id = ?", (device_id,)).fetchone()
        return dict(row) if row else None


def touch_paired_device(device_id: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE paired_devices SET last_seen_at = ? WHERE id = ?", (time.time(), device_id))
        conn.commit()


def revoke_paired_device(device_id: str, revoked_by_name: str = "") -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE paired_devices SET revoked_at = ?, revoked_by_name = ? WHERE id = ? AND revoked_at = 0",
            (time.time(), str(revoked_by_name or ""), device_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_paired_device(device_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM paired_devices WHERE id = ?", (device_id,))
        conn.commit()
        return cur.rowcount > 0


def delete_expired_pair_tickets() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM device_pair_tickets WHERE expires_at < ?", (time.time() - 86400,))
        conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> set:
    allowed = {"settings", "accounts", "task_configs", "orders", "job_logs", "store_appointments"}
    if table not in allowed:
        raise ValueError(f"Unsupported sync table: {table}")
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _insert_snapshot_rows(conn: sqlite3.Connection, table: str, rows: List[Dict[str, Any]]) -> int:
    columns = _table_columns(conn, table)
    inserted = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        values = {key: value for key, value in raw.items() if key in columns}
        if not values:
            continue
        keys = list(values.keys())
        placeholders = ", ".join("?" for _ in keys)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({', '.join(keys)}) VALUES ({placeholders})",
            [values[key] for key in keys],
        )
        inserted += 1
    return inserted


def apply_device_sync_snapshot(snapshot: Dict[str, Any]) -> Dict[str, int]:
    """将 PC 端完整快照导入当前（手机本地）数据库，返回各表写入数量。"""
    counts: Dict[str, int] = {}
    with get_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM settings")
            counts["settings"] = _insert_snapshot_rows(
                conn, "settings",
                [{"key": key, "value": json.dumps(value, ensure_ascii=False)} for key, value in (snapshot.get("settings") or {}).items()],
            )
            for table in ("store_appointments", "job_logs", "orders", "task_configs", "accounts"):
                conn.execute(f"DELETE FROM {table}")
                counts[table] = _insert_snapshot_rows(conn, table, snapshot.get(table) or [])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return counts


def create_device_sync_handoff(payload: Dict[str, Any], ttl_seconds: int = 600) -> str:
    code = uuid.uuid4().hex + secrets.token_hex(8)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO device_sync_handoffs (code, payload, created_at, expires_at, consumed_at) VALUES (?, ?, ?, ?, NULL)",
            (code, json.dumps(payload, ensure_ascii=False), now, now + ttl_seconds),
        )
        conn.commit()
    return code


def consume_device_sync_handoff(code: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload FROM device_sync_handoffs WHERE code = ? AND consumed_at IS NULL AND expires_at > ?",
            (code, now),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE device_sync_handoffs SET consumed_at = ? WHERE code = ?", (now, code))
        conn.commit()
        try:
            return json.loads(row["payload"])
        except Exception:
            return None


# ---------------- 霸王餐订单操作接口 ---------------- #

def deduplicate_orders() -> int:
    """
    自动自愈历史重复订单记录：
    若存在相同的 promotion_order_id > 0，保留已绑定单号或状态已流转的一条，删除未绑定单号的冗余 pending 幽灵记录。
    """
    cleaned = 0
    try:
        with get_conn() as conn:
            dups = conn.execute("""
                SELECT promotion_order_id FROM orders 
                WHERE promotion_order_id > 0 
                GROUP BY promotion_order_id HAVING COUNT(*) > 1
            """).fetchall()
            for d in dups:
                pid = d["promotion_order_id"]
                rows = conn.execute(
                    "SELECT id, order_sn, platform_order_id, status FROM orders WHERE promotion_order_id = ? ORDER BY (platform_order_id != '') DESC, (status != 'pending') DESC, id DESC",
                    (pid,)
                ).fetchall()
                if len(rows) > 1:
                    keep_id = rows[0]["id"]
                    conn.execute("DELETE FROM orders WHERE promotion_order_id = ? AND id != ?", (pid, keep_id))
                    cleaned += (len(rows) - 1)
            conn.commit()
    except Exception:
        pass
    return cleaned


def auto_cancel_expired_orders(account_key: Optional[str] = None) -> int:
    """
    自动检测并批量更新所有已超时的待处理订单为已取消 (cancelled)。
    判定规则：
    1. status == 'pending' 且 (timeout_time > 0 且 timeout_time < 当前时间戳)
    2. 或 status == 'pending' 且 (expire_time != '' 且 expire_time < 当前日期时间)
    3. 或未设置 timeout_time / expire_time 但已超过 2 小时未同步且未绑定单号的待处理记录
    """
    deduplicate_orders()

    now_str = time_service.format_now_dt()
    now_ts = time_service.now_int()
    sql = """
        UPDATE orders
        SET status = 'cancelled', updated_at = :now_str
        WHERE status != 'cancelled' AND (
            (status = 'pending' AND (
                (timeout_time > 0 AND timeout_time < :now_ts) OR
                (expire_time != '' AND expire_time < :now_str)
            )) OR
            ((platform_order_id = '' OR platform_order_id IS NULL) AND timeout_time > 0 AND timeout_time < :now_ts) OR
            ((timeout_time <= 0 OR timeout_time IS NULL) AND (expire_time = '' OR expire_time IS NULL) AND (platform_order_id = '' OR platform_order_id IS NULL) AND order_time > 0 AND (:now_ts - order_time) > 28800)
        )
    """
    params: Dict[str, Any] = {"now_str": now_str, "now_ts": now_ts}
    if account_key:
        sql += " AND account_key = :account_key"
        params["account_key"] = account_key
    try:
        with get_conn() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
    except Exception:
        return 0


def get_orders(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
    platform: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    auto_cancel_expired_orders(account_key=account_key)
    # 查询前先执行过期超时订单自动自愈与取消
    auto_cancel_expired_orders(account_key=account_key)

    sql = "SELECT * FROM orders WHERE 1=1"
    params: Dict[str, Any] = {}
    if account_key:
        sql += " AND account_key = :account_key"
        params["account_key"] = account_key
    if status and status != "all":
        sql += " AND status = :status"
        params["status"] = status
    if platform and platform != "all":
        if platform in ("jingdong", "jd"):
            sql += " AND platform IN ('jingdong', 'jd')"
        elif platform in ("eleme", "taobao"):
            sql += " AND platform IN ('eleme', 'taobao')"
        else:
            sql += " AND platform = :platform"
            params["platform"] = platform
    if keyword:
        sql += " AND (store_name LIKE :kw OR order_sn LIKE :kw OR platform_order_id LIKE :kw)"
        params["kw"] = f"%{keyword}%"
    sql += " ORDER BY order_time DESC, created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def count_orders(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
    platform: Optional[str] = None,
    keyword: Optional[str] = None,
) -> int:
    sql = "SELECT COUNT(*) FROM orders WHERE 1=1"
    params: Dict[str, Any] = {}
    if account_key:
        sql += " AND account_key = :account_key"
        params["account_key"] = account_key
    if status and status != "all":
        sql += " AND status = :status"
        params["status"] = status
    if platform and platform != "all":
        if platform in ("jingdong", "jd"):
            sql += " AND platform IN ('jingdong', 'jd')"
        elif platform in ("eleme", "taobao"):
            sql += " AND platform IN ('eleme', 'taobao')"
        else:
            sql += " AND platform = :platform"
            params["platform"] = platform
    if keyword:
        sql += " AND (store_name LIKE :kw OR order_sn LIKE :kw OR platform_order_id LIKE :kw)"
        params["kw"] = f"%{keyword}%"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] if row else 0)


def get_order_by_id(order_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def save_order(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = time_service.format_now_dt()
    promo_id = int(data.get("promotion_order_id") or 0)
    sn = str(data.get("order_sn") or "")
    acc_key = str(data.get("account_key") or "")
    # 用户已手动删除的订单不再被官方同步重新写回
    if is_order_deleted(sn):
        return None
    if promo_id > 0 and is_order_deleted(f"promo:{promo_id}"):
        return None
    with get_conn() as conn:
        existing = None
        if promo_id > 0:
            if acc_key:
                existing = conn.execute(
                    "SELECT id, order_sn, platform_order_id, status, delay_count, delay_card_used_count, timeout_time, expire_time, receipt_uploaded_at FROM orders WHERE promotion_order_id = ? AND account_key = ? ORDER BY (platform_order_id != '') DESC, (status != 'pending') DESC, id DESC LIMIT 1",
                    (promo_id, acc_key)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id, order_sn, platform_order_id, status, delay_count, delay_card_used_count, timeout_time, expire_time, receipt_uploaded_at FROM orders WHERE promotion_order_id = ? ORDER BY (platform_order_id != '') DESC, (status != 'pending') DESC, id DESC LIMIT 1",
                    (promo_id,)
                ).fetchone()
        if not existing and sn:
            if acc_key:
                existing = conn.execute(
                    "SELECT id, order_sn, platform_order_id, status, delay_count, delay_card_used_count, timeout_time, expire_time, receipt_uploaded_at FROM orders WHERE order_sn = ? AND account_key = ? LIMIT 1",
                    (sn, acc_key)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id, order_sn, platform_order_id, status, delay_count, delay_card_used_count, timeout_time, expire_time, receipt_uploaded_at FROM orders WHERE order_sn = ? LIMIT 1",
                    (sn,)
                ).fetchone()

        if existing:
            existing = dict(existing)
            target_id = existing["id"]
            # 优先采用更长/更规范的官方订单号 (如 202610131541802692184 优于 802692184)
            chosen_sn = sn if (len(sn) >= len(existing["order_sn"]) or existing["order_sn"].isdigit()) else existing["order_sn"]
            chosen_plat_id = (data.get("platform_order_id") or "").strip() or existing.get("platform_order_id") or ""
            new_status = data.get("status") or existing.get("status") or "pending"
            chosen_delay_count = max(int(existing.get("delay_count") or 0), int(data.get("delay_count") or 0))
            chosen_delay_card_count = max(int(existing.get("delay_card_used_count") or 0), int(data.get("delay_card_used_count") or 0))
            chosen_tt = max(int(existing.get("timeout_time") or 0), int(data.get("timeout_time") or 0))
            chosen_exp = existing.get("expire_time") if (chosen_tt == int(existing.get("timeout_time") or 0) and existing.get("expire_time")) else data.get("expire_time", "")
            chosen_uploaded_at = str(data.get("receipt_uploaded_at") or "").strip() or str(existing.get("receipt_uploaded_at") or "").strip()
            if not chosen_plat_id and chosen_tt > 0 and chosen_tt < time_service.now_int():
                new_status = "cancelled"

            conn.execute("""
            UPDATE orders SET
                order_sn = :order_sn,
                promotion_order_id = :promotion_order_id,
                platform_order_id = :platform_order_id,
                store_id = :store_id,
                store_name = :store_name,
                store_icon = :store_icon,
                platform = :platform,
                order_money = :order_money,
                rebate_money = :rebate_money,
                original_user_rebate = :original_user_rebate,
                redpack_reward_num = :redpack_reward_num,
                timeout_time = :timeout_time,
                status = :status,
                condition = :condition,
                receipt_img = :receipt_img,
                receipt_uploaded_at = :receipt_uploaded_at,
                reject_reason = :reject_reason,
                expire_time = :expire_time,
                order_time = :order_time,
                order_type = :order_type,
                rebate_ratio = :rebate_ratio,
                delay_count = :delay_count,
                delay_card_used_count = :delay_card_used_count,
                vip_extra_silk = :vip_extra_silk,
                vip_extra_silk_radio = :vip_extra_silk_radio,
                official_reduce = :official_reduce,
                official_order_desc = :official_order_desc,
                coupon_bonus = :coupon_bonus,
                total_rebate = :total_rebate,
                vip_extra_reward = :vip_extra_reward,
                expected_rebate = :expected_rebate,
                actual_paid_amount = :actual_paid_amount,
                threshold_shortfall = :threshold_shortfall,
                updated_at = :updated_at
            WHERE id = :id
            """, {
                "id": target_id,
                "order_sn": chosen_sn,
                "promotion_order_id": promo_id or int(data.get("promotion_order_id") or 0),
                "platform_order_id": chosen_plat_id,
                "store_id": str(data.get("store_id", "")),
                "store_name": data.get("store_name", ""),
                "store_icon": data.get("store_icon", ""),
                "platform": data.get("platform", "meituan"),
                "order_money": float(data.get("order_money", 0)),
                "rebate_money": float(data.get("rebate_money", 0)),
                "original_user_rebate": float(data.get("original_user_rebate", 0)),
                "redpack_reward_num": float(data.get("redpack_reward_num", 0)),
                "timeout_time": chosen_tt,
                "status": new_status,
                "condition": data.get("condition", "无需评价"),
                "receipt_img": data.get("receipt_img", ""),
                "receipt_uploaded_at": chosen_uploaded_at,
                "reject_reason": data.get("reject_reason", ""),
                "expire_time": chosen_exp,
                "updated_at": now,
                "order_time": int(data.get("order_time") or 0),
                "order_type": int(data.get("order_type") or 0),
                "rebate_ratio": float(data.get("rebate_ratio") or 0),
                "delay_count": chosen_delay_count,
                "delay_card_used_count": chosen_delay_card_count,
                "vip_extra_silk": int(bool(data.get("vip_extra_silk"))),
                "vip_extra_silk_radio": float(data.get("vip_extra_silk_radio") or 0),
                "official_reduce": str(data.get("official_reduce") or ""),
                "official_order_desc": str(data.get("official_order_desc") or ""),
                "coupon_bonus": float(data.get("coupon_bonus") or 0),
                "total_rebate": float(data.get("total_rebate") or 0),
                "vip_extra_reward": float(data.get("vip_extra_reward") or 0),
                "expected_rebate": float(data.get("expected_rebate") or 0),
                "actual_paid_amount": float(data.get("actual_paid_amount") or 0),
                "threshold_shortfall": float(data.get("threshold_shortfall") or 0)
            })
            if promo_id > 0:
                conn.execute(
                    "DELETE FROM orders WHERE promotion_order_id = ? AND id != ?",
                    (promo_id, target_id)
                )
            conn.commit()
            return get_order_by_id(target_id)

        cursor = conn.execute("""
        INSERT INTO orders (account_key, order_sn, promotion_order_id, platform_order_id, store_id, store_name, store_icon, platform, order_money, rebate_money, original_user_rebate, redpack_reward_num, timeout_time, status, condition, receipt_img, receipt_uploaded_at, reject_reason, expire_time, created_at, updated_at, order_time, order_type, rebate_ratio, delay_count, delay_card_used_count, vip_extra_silk, vip_extra_silk_radio, official_reduce, official_order_desc, coupon_bonus, total_rebate, vip_extra_reward, expected_rebate, actual_paid_amount, threshold_shortfall)
        VALUES (:account_key, :order_sn, :promotion_order_id, :platform_order_id, :store_id, :store_name, :store_icon, :platform, :order_money, :rebate_money, :original_user_rebate, :redpack_reward_num, :timeout_time, :status, :condition, :receipt_img, :receipt_uploaded_at, :reject_reason, :expire_time, :created_at, :updated_at, :order_time, :order_type, :rebate_ratio, :delay_count, :delay_card_used_count, :vip_extra_silk, :vip_extra_silk_radio, :official_reduce, :official_order_desc, :coupon_bonus, :total_rebate, :vip_extra_reward, :expected_rebate, :actual_paid_amount, :threshold_shortfall)
        ON CONFLICT(order_sn) DO UPDATE SET
            promotion_order_id = excluded.promotion_order_id,
            platform_order_id = excluded.platform_order_id,
            store_name = excluded.store_name,
            store_icon = excluded.store_icon,
            status = excluded.status,
            order_money = excluded.order_money,
            rebate_money = excluded.rebate_money,
            original_user_rebate = excluded.original_user_rebate,
            redpack_reward_num = excluded.redpack_reward_num,
            timeout_time = excluded.timeout_time,
            receipt_img = excluded.receipt_img,
            receipt_uploaded_at = CASE WHEN excluded.receipt_uploaded_at != '' THEN excluded.receipt_uploaded_at ELSE orders.receipt_uploaded_at END,
            reject_reason = excluded.reject_reason,
            order_time = excluded.order_time,
            expire_time = excluded.expire_time,
            condition = excluded.condition,
            order_type = excluded.order_type,
            rebate_ratio = excluded.rebate_ratio,
            delay_count = excluded.delay_count,
            vip_extra_silk = excluded.vip_extra_silk,
            vip_extra_silk_radio = excluded.vip_extra_silk_radio,
            official_reduce = excluded.official_reduce,
            official_order_desc = excluded.official_order_desc,
            coupon_bonus = excluded.coupon_bonus,
            total_rebate = excluded.total_rebate,
            vip_extra_reward = excluded.vip_extra_reward,
            expected_rebate = excluded.expected_rebate,
            actual_paid_amount = excluded.actual_paid_amount,
            threshold_shortfall = excluded.threshold_shortfall,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """, {
            "account_key": data.get("account_key", ""),
            "order_sn": data.get("order_sn", f"XC{time_service.now_millis()}"),
            "promotion_order_id": int(data.get("promotion_order_id") or 0),
            "platform_order_id": data.get("platform_order_id", ""),
            "store_id": str(data.get("store_id", "")),
            "store_name": data.get("store_name", ""),
            "store_icon": data.get("store_icon", ""),
            "platform": data.get("platform", "meituan"),
            "order_money": float(data.get("order_money", 0)),
            "rebate_money": float(data.get("rebate_money", 0)),
            "original_user_rebate": float(data.get("original_user_rebate", 0)),
            "redpack_reward_num": float(data.get("redpack_reward_num", 0)),
            "timeout_time": int(data.get("timeout_time") or 0),
            "status": "cancelled" if (not data.get("platform_order_id") and int(data.get("timeout_time") or 0) > 0 and int(data.get("timeout_time") or 0) < time_service.now_int()) else data.get("status", "pending"),
            "condition": data.get("condition", "无需评价"),
            "receipt_img": data.get("receipt_img", ""),
            "receipt_uploaded_at": str(data.get("receipt_uploaded_at") or ""),
            "reject_reason": data.get("reject_reason", ""),
            "expire_time": data.get("expire_time", ""),
            "created_at": data.get("created_at", now),
            "updated_at": now,
            "order_time": int(data.get("order_time") or 0),
            "order_type": int(data.get("order_type") or 0),
            "rebate_ratio": float(data.get("rebate_ratio") or 0),
            "delay_count": int(data.get("delay_count") or 0),
            "delay_card_used_count": int(data.get("delay_card_used_count") or 0),
            "vip_extra_silk": int(bool(data.get("vip_extra_silk"))),
            "vip_extra_silk_radio": float(data.get("vip_extra_silk_radio") or 0),
            "official_reduce": str(data.get("official_reduce") or ""),
            "official_order_desc": str(data.get("official_order_desc") or ""),
            "coupon_bonus": float(data.get("coupon_bonus") or 0),
            "total_rebate": float(data.get("total_rebate") or 0),
            "vip_extra_reward": float(data.get("vip_extra_reward") or 0),
            "expected_rebate": float(data.get("expected_rebate") or 0),
            "actual_paid_amount": float(data.get("actual_paid_amount") or 0),
            "threshold_shortfall": float(data.get("threshold_shortfall") or 0)
            })
        conn.commit()
        last_id = cursor.lastrowid
        return get_order_by_id(last_id) if last_id else None


def update_order(order_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = [
        "platform_order_id", "status", "receipt_img", "receipt_uploaded_at", "reject_reason",
        "order_money", "rebate_money", "original_user_rebate",
        "redpack_reward_num", "timeout_time", "expire_time", "store_icon",
        "delay_count", "delay_card_used_count"
    ]
    updates = []
    params: Dict[str, Any] = {"id": order_id, "updated_at": time_service.format_now_dt()}
    for k in allowed:
        if k in data:
            updates.append(f"{k} = :{k}")
            params[k] = data[k]
    if not updates:
        return get_order_by_id(order_id)
    sql = f"UPDATE orders SET {', '.join(updates)}, updated_at = :updated_at WHERE id = :id"

    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()
    return get_order_by_id(order_id)


def is_order_deleted(order_sn: str) -> bool:
    if not order_sn:
        return False
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM deleted_orders WHERE order_sn = ? LIMIT 1", (order_sn,)
        ).fetchone() is not None


def clear_order_tombstones(order_sns: List[str], promotion_ids: List[int]) -> int:
    """清除指定官方订单的本地删除标记，使后续同步可以重新入库。"""
    keys = [str(sn).strip() for sn in order_sns if str(sn).strip()]
    keys.extend(f"promo:{int(pid)}" for pid in promotion_ids if int(pid or 0) > 0)
    keys = list(dict.fromkeys(keys))
    if not keys:
        return 0
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in keys)
        row = conn.execute(
            f"SELECT COUNT(*) FROM deleted_orders WHERE order_sn IN ({placeholders})",
            keys,
        ).fetchone()
        removed = int(row[0] if row else 0)
        if removed:
            conn.execute(
                f"DELETE FROM deleted_orders WHERE order_sn IN ({placeholders})",
                keys,
            )
            conn.commit()
        return removed


def delete_order(order_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT order_sn, promotion_order_id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            return False
        order_sn = str(row[0] or "").strip()
        promo_id = int(row[1] or 0)
        now_del = time_service.format_now_dt()
        if order_sn:
            conn.execute(
                "INSERT OR IGNORE INTO deleted_orders (order_sn, deleted_at) VALUES (?, ?)",
                (order_sn, now_del)
            )
        if promo_id > 0:
            conn.execute(
                "INSERT OR IGNORE INTO deleted_orders (order_sn, deleted_at) VALUES (?, ?)",
                (f"promo:{promo_id}", now_del)
            )
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
    return True


def get_order_stats(account_key: Optional[str] = None) -> Dict[str, Any]:
    auto_cancel_expired_orders(account_key=account_key)
    with get_conn() as conn:
        sql = "SELECT status, order_money, rebate_money, redpack_reward_num FROM orders WHERE 1=1"
        params: Dict[str, Any] = {}
        if account_key:
            sql += " AND account_key = :account_key"
            params["account_key"] = account_key
        rows = conn.execute(sql, params).fetchall()

    total_orders = len([r for r in rows if r["status"] != "cancelled"])
    completed_orders = sum(1 for r in rows if r["status"] == "completed")
    pending_orders = sum(1 for r in rows if r["status"] in ("pending", "auditing"))
    total_rebate = sum(
        float(r["rebate_money"] or 0.0) + float(r["redpack_reward_num"] or 0.0)
        for r in rows if r["status"] == "completed"
    )
    pending_rebate = sum(
        float(r["rebate_money"] or 0.0) + float(r["redpack_reward_num"] or 0.0)
        for r in rows if r["status"] in ("pending", "auditing")
    )
    total_spent = sum(float(r["order_money"] or 0.0) for r in rows if r["status"] == "completed")

    return {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "pending_orders": pending_orders,
        "total_rebate": round(total_rebate, 2),
        "pending_rebate": round(pending_rebate, 2),
        "total_spent": round(total_spent, 2)
    }


def get_dashboard_chart_data(account_key: Optional[str] = None) -> Dict[str, Any]:
    auto_cancel_expired_orders(account_key=account_key)
    with get_conn() as conn:
        sql = "SELECT status, platform, order_money, rebate_money, redpack_reward_num, created_at, order_time FROM orders WHERE 1=1"
        params: Dict[str, Any] = {}
        if account_key:
            sql += " AND account_key = :account_key"
            params["account_key"] = account_key
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    today = datetime.date.today()
    days_map = {}
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        d_str = d.strftime("%m-%d")
        days_map[d.strftime("%Y-%m-%d")] = {
            "date": d_str,
            "full_date": d.strftime("%Y-%m-%d"),
            "rebate": 0.0,
            "orders": 0,
            "spent": 0.0
        }

    status_counts = {
        "completed": 0,
        "auditing": 0,
        "pending": 0,
        "rejected": 0,
        "cancelled": 0
    }
    platform_counts = {
        "meituan": 0,
        "eleme": 0,
        "jingdong": 0
    }

    today_str = today.strftime("%Y-%m-%d")
    today_rebate = 0.0
    today_orders = 0
    today_savings_retail = 0.0
    today_completed_orders = 0
    today_completed_rebate = 0.0
    today_pending_orders = 0
    today_pending_rebate = 0.0

    for r in rows:
        st = r.get("status") or "pending"
        plat = r.get("platform") or "meituan"
        if plat == "jd":
            plat = "jingdong"
        elif plat == "taobao":
            plat = "eleme"
        rebate = float(r.get("rebate_money") or 0.0) + float(r.get("redpack_reward_num") or 0.0)
        spent = float(r.get("order_money") or 0.0)

        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["pending"] += 1

        if plat in platform_counts:
            platform_counts[plat] += 1
        else:
            platform_counts["meituan"] += 1

        row_date = None
        c_at = r.get("created_at") or ""
        if len(c_at) >= 10:
            row_date = c_at[:10]
        elif r.get("order_time"):
            try:
                row_date = datetime.datetime.fromtimestamp(r["order_time"]).strftime("%Y-%m-%d")
            except Exception:
                pass

        if row_date in days_map:
            if st != "cancelled":
                days_map[row_date]["orders"] += 1
                days_map[row_date]["spent"] = round(days_map[row_date]["spent"] + spent, 2)
            if st == "completed":
                days_map[row_date]["rebate"] = round(days_map[row_date]["rebate"] + rebate, 2)

        if row_date == today_str:
            if st != "cancelled":
                today_orders += 1
            if st == "completed":
                today_completed_orders += 1
                today_completed_rebate = round(today_completed_rebate + rebate, 2)
                today_savings_retail = round(today_savings_retail + spent, 2)
            elif st in ("pending", "auditing"):
                today_pending_orders += 1
                today_pending_rebate = round(today_pending_rebate + rebate, 2)

    trend_list = [days_map[k] for k in sorted(days_map.keys())]

    status_dist = [
        {"name": "已到账", "value": status_counts["completed"], "color": "#10B981"},
        {"name": "审核中", "value": status_counts["auditing"], "color": "#3B82F6"},
        {"name": "待提交", "value": status_counts["pending"], "color": "#F59E0B"},
        {"name": "已驳回", "value": status_counts["rejected"], "color": "#EF4444"},
        {"name": "已取消", "value": status_counts["cancelled"], "color": "#9CA3AF"},
    ]

    platform_dist = [
        {"name": "美团外卖", "value": platform_counts["meituan"], "color": "#FFC300"},
        {"name": "饿了么/淘宝", "value": platform_counts["eleme"], "color": "#0091FF"},
        {"name": "京东外卖", "value": platform_counts["jingdong"], "color": "#E1251B"},
    ]

    return {
        "trend": trend_list,
        "status_distribution": status_dist,
        "platform_distribution": platform_dist,
        "today_summary": {
            "today_rebate": today_completed_rebate,
            "today_orders": today_orders,
            "today_completed_orders": today_completed_orders,
            "today_pending_orders": today_pending_orders,
            "today_savings": today_completed_rebate,
            "today_savings_retail": today_savings_retail,
        }
    }


# ---------------- 美团官方账号操作接口 ---------------- #

def get_all_meituan_accounts() -> List[Dict[str, Any]]:
    """
    返回所有拥有美团领券凭证的账号列表：
    优先收集已绑定美团的小蚕账号，其次兼容未关联的独立美团账号。
    """
    with get_conn() as conn:
        result = []
        # 1. 查询绑定了美团的小蚕账号
        xiaocan_rows = conn.execute("""
            SELECT * FROM accounts 
            WHERE meituan_token IS NOT NULL AND meituan_token != '' AND platform != 'meituan'
        """).fetchall()
        for r in xiaocan_rows:
            d = _format_account_row(dict(r))
            result.append({
                "key": d["key"],
                "account_key": d["key"],
                "nickname": d.get("meituan_nickname") or f"美团 ({d.get('nickname')})",
                "token": d["meituan_token"],
                "saved_at": d.get("meituan_saved_at") or 0,
                "last_claimed_at": d.get("meituan_last_claimed_at") or 0,
                "last_claimed_count": d.get("meituan_last_claimed_count") or 0,
                "last_claimed_details": d.get("meituan_last_claimed_details") or [],
                "is_active": d.get("meituan_is_active", 1),
                "history_pool": d.get("meituan_history_pool") or [],
                "is_bound_to_xiaocan": True,
                "xiaocan_nickname": d.get("nickname")
            })

        # 2. 查询独立 meituan_accounts (未绑定的)
        mt_rows = conn.execute("SELECT * FROM meituan_accounts ORDER BY created_at ASC").fetchall()
        bound_keys = {item["key"] for item in result}
        for r in mt_rows:
            d = dict(r)
            if d["key"] in bound_keys:
                continue
            if isinstance(d.get("last_claimed_details"), str):
                try:
                    d["last_claimed_details"] = json.loads(d["last_claimed_details"])
                except Exception:
                    d["last_claimed_details"] = []
            if isinstance(d.get("history_pool"), str):
                try:
                    d["history_pool"] = json.loads(d["history_pool"])
                except Exception:
                    d["history_pool"] = []
            d["is_bound_to_xiaocan"] = False
            result.append(d)
        return result


def get_meituan_account(key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM meituan_accounts WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("last_claimed_details"), str):
            try:
                d["last_claimed_details"] = json.loads(d["last_claimed_details"])
            except Exception:
                d["last_claimed_details"] = []
        elif not d.get("last_claimed_details"):
            d["last_claimed_details"] = []
        if isinstance(d.get("history_pool"), str):
            try:
                d["history_pool"] = json.loads(d["history_pool"])
            except Exception:
                d["history_pool"] = []
        elif not d.get("history_pool"):
            d["history_pool"] = []
        return d


def save_meituan_account(data: Dict[str, Any]) -> Dict[str, Any]:
    key = str(data.get("key") or "").strip()
    if not key:
        key = f"mt_acc_{time_service.now_int()}_{uuid.uuid4().hex[:4]}"

    now = time_service.format_now_dt()
    now_ts = time_service.now_int()
    existing = get_meituan_account(key)

    nickname = data.get("nickname") or (existing.get("nickname") if existing else f"美团账号 {key[-4:]}")
    avatar = data.get("avatar") or (existing.get("avatar") if existing else "")
    token = data.get("token") or (existing.get("token") if existing else "")
    saved_at = int(data.get("saved_at") or now_ts)
    last_claimed_at = int(data.get("last_claimed_at") or (existing.get("last_claimed_at") if existing else 0))
    last_claimed_count = int(data.get("last_claimed_count") or (existing.get("last_claimed_count") if existing else 0))
    is_active = int(data.get("is_active") if data.get("is_active") is not None else (existing.get("is_active") if existing else 1))

    # 维护历史池 (最多保留 5 份历史 token)
    pool = existing.get("history_pool") or [] if existing else []
    if token and token not in pool:
        pool.append(token)
        pool = pool[-5:]
    if data.get("history_pool") and isinstance(data["history_pool"], list):
        for t in data["history_pool"]:
            if t and t not in pool:
                pool.append(t)
        pool = pool[-5:]

    details_str = json.dumps(data.get("last_claimed_details") or (existing.get("last_claimed_details") if existing else []), ensure_ascii=False)
    pool_str = json.dumps(pool, ensure_ascii=False)

    with get_conn() as conn:
        conn.execute("""
        INSERT INTO meituan_accounts (
            key, nickname, avatar, token, saved_at, last_claimed_at, 
            last_claimed_count, last_claimed_details, is_active, history_pool, created_at, updated_at
        )
        VALUES (:key, :nickname, :avatar, :token, :saved_at, :last_claimed_at, 
                :last_claimed_count, :last_claimed_details, :is_active, :history_pool, :created_at, :updated_at)
        ON CONFLICT(key) DO UPDATE SET
            nickname = excluded.nickname,
            avatar = CASE WHEN excluded.avatar != '' THEN excluded.avatar ELSE meituan_accounts.avatar END,
            token = CASE WHEN excluded.token != '' THEN excluded.token ELSE meituan_accounts.token END,
            saved_at = CASE WHEN excluded.token != '' THEN excluded.saved_at ELSE meituan_accounts.saved_at END,
            last_claimed_at = CASE WHEN excluded.last_claimed_at > 0 THEN excluded.last_claimed_at ELSE meituan_accounts.last_claimed_at END,
            last_claimed_count = CASE WHEN excluded.last_claimed_count > 0 THEN excluded.last_claimed_count ELSE meituan_accounts.last_claimed_count END,
            last_claimed_details = CASE WHEN excluded.last_claimed_details != '[]' THEN excluded.last_claimed_details ELSE meituan_accounts.last_claimed_details END,
            is_active = excluded.is_active,
            history_pool = excluded.history_pool,
            updated_at = excluded.updated_at
        """, {
            "key": key,
            "nickname": nickname,
            "avatar": avatar,
            "token": token,
            "saved_at": saved_at,
            "last_claimed_at": last_claimed_at,
            "last_claimed_count": last_claimed_count,
            "last_claimed_details": details_str,
            "is_active": is_active,
            "history_pool": pool_str,
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now
        })

        # 仅对非小蚕账号 (如独立美团账号 mt_*) 同步写入 accounts 统一账号表 (标记 platform='meituan')
        if not key.startswith("acc_"):
            conn.execute("""
            INSERT INTO accounts (
                key, nickname, avatar, token, platform, saved_at, last_claimed_at, 
                last_claimed_count, last_claimed_details, is_active, history_pool, created_at, updated_at
            )
            VALUES (:key, :nickname, :avatar, :token, 'meituan', :saved_at, :last_claimed_at, 
                    :last_claimed_count, :last_claimed_details, :is_active, :history_pool, :created_at, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                nickname = excluded.nickname,
                avatar = CASE WHEN excluded.avatar != '' THEN excluded.avatar ELSE accounts.avatar END,
                token = CASE WHEN excluded.token != '' THEN excluded.token ELSE accounts.token END,
                platform = 'meituan',
                saved_at = CASE WHEN excluded.token != '' THEN excluded.saved_at ELSE accounts.saved_at END,
                last_claimed_at = CASE WHEN excluded.last_claimed_at > 0 THEN excluded.last_claimed_at ELSE accounts.last_claimed_at END,
                last_claimed_count = CASE WHEN excluded.last_claimed_count > 0 THEN excluded.last_claimed_count ELSE accounts.last_claimed_count END,
                last_claimed_details = CASE WHEN excluded.last_claimed_details != '[]' THEN excluded.last_claimed_details ELSE accounts.last_claimed_details END,
                is_active = excluded.is_active,
                history_pool = excluded.history_pool,
                updated_at = excluded.updated_at
            """, {
                "key": key,
                "nickname": nickname,
                "avatar": avatar,
                "token": token,
                "saved_at": saved_at,
                "last_claimed_at": last_claimed_at,
                "last_claimed_count": last_claimed_count,
                "last_claimed_details": details_str,
                "is_active": is_active,
                "history_pool": pool_str,
                "created_at": existing.get("created_at") if existing else now,
                "updated_at": now
            })
        conn.commit()

    return get_meituan_account(key)


def delete_meituan_account(key: str) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM meituan_accounts WHERE key = ?", (key,))
        conn.execute("DELETE FROM accounts WHERE key = ?", (key,))
        conn.execute("DELETE FROM task_configs WHERE account_key = ?", (key,))
        conn.commit()
        return True


def bind_meituan_to_account(account_key: str, data: Dict[str, Any]) -> bool:
    """为指定小蚕账号绑定美团凭证"""
    token = (data.get("token") or "").strip()
    nickname = (data.get("nickname") or f"美团账号 ({token[-4:] if token else '已绑定'})").strip()
    saved_at = int(data.get("saved_at") or time_service.now_ts())
    
    acc = get_account_by_key(account_key)
    pool = acc.get("meituan_history_pool") or [] if acc else []
    if token and token not in pool:
        pool.append(token)
        pool = pool[-5:]
    if data.get("history_pool") and isinstance(data["history_pool"], list):
        for t in data["history_pool"]:
            if t and t not in pool:
                pool.append(t)
        pool = pool[-5:]
    pool_str = json.dumps(pool, ensure_ascii=False)
    
    with get_conn() as conn:
        conn.execute("""
        UPDATE accounts
        SET meituan_token = ?,
            meituan_nickname = ?,
            meituan_saved_at = ?,
            meituan_is_active = 1,
            meituan_history_pool = ?,
            updated_at = ?
        WHERE key = ?
        """, (token, nickname, saved_at, pool_str, time_service.format_now_dt(), account_key))
        
        # 同时在 meituan_accounts 中留存一份以保持数据对称
        now_str = time_service.format_now_dt()
        conn.execute("""
        INSERT INTO meituan_accounts (key, nickname, token, saved_at, is_active, history_pool, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            nickname = excluded.nickname,
            token = excluded.token,
            saved_at = excluded.saved_at,
            is_active = 1,
            history_pool = excluded.history_pool,
            updated_at = excluded.updated_at
        """, (account_key, nickname, token, saved_at, pool_str, now_str, now_str))
        conn.commit()
    return True


def unbind_meituan_from_account(account_key: str) -> bool:
    """解除指定小蚕账号的美团凭证绑定"""
    with get_conn() as conn:
        conn.execute("""
        UPDATE accounts
        SET meituan_token = '',
            meituan_nickname = '',
            meituan_saved_at = 0,
            meituan_is_active = 0,
            meituan_last_claimed_count = 0,
            meituan_last_claimed_details = '[]',
            updated_at = ?
        WHERE key = ?
        """, (time_service.format_now_dt(), account_key))
        conn.execute("DELETE FROM meituan_accounts WHERE key = ?", (account_key,))
        conn.commit()
    return True


def clear_all_meituan_data() -> bool:
    """彻底清空全部美团凭证（清空 meituan_accounts、清理伪账号及小蚕账号美团字段）"""
    now = time_service.format_now_dt()
    with get_conn() as conn:
        conn.execute("DELETE FROM meituan_accounts")
        conn.execute("DELETE FROM accounts WHERE (platform = 'meituan' AND key NOT LIKE 'acc_%') OR key LIKE 'mt_%'")
        conn.execute("""
        UPDATE accounts
        SET meituan_token = '',
            meituan_nickname = '',
            meituan_saved_at = 0,
            meituan_last_claimed_at = 0,
            meituan_last_claimed_count = 0,
            meituan_last_claimed_details = '[]',
            meituan_history_pool = '[]',
            meituan_is_active = 0,
            updated_at = ?
        """, (now,))
        conn.commit()
    return True


def update_meituan_claim_stats(key: str, count: int, details: List[Dict[str, Any]], new_token: Optional[str] = None):
    now = time_service.format_now_dt()
    now_ts = time_service.now_int()
    acc = get_account_by_key(key) or get_meituan_account(key)
    if not acc:
        return

    details_str = json.dumps(details, ensure_ascii=False)
    
    # 检查是否为绑定美团的小蚕账号
    if acc.get("meituan_token"):
        pool = acc.get("meituan_history_pool") or []
        tok = (new_token or acc.get("meituan_token") or "").strip()
        if tok and tok not in pool:
            pool.append(tok)
            pool = pool[-5:]
        pool_str = json.dumps(pool, ensure_ascii=False)
        with get_conn() as conn:
            conn.execute("""
            UPDATE accounts
            SET meituan_last_claimed_at = ?,
                meituan_last_claimed_count = ?,
                meituan_last_claimed_details = ?,
                meituan_token = ?,
                meituan_history_pool = ?,
                meituan_is_active = 1,
                last_claimed_at = ?,
                last_claimed_count = ?,
                last_claimed_details = ?,
                updated_at = ?
            WHERE key = ?
            """, (now_ts, count, details_str, tok, pool_str, now_ts, count, details_str, now, key))
            conn.execute("""
            UPDATE meituan_accounts
            SET last_claimed_at = ?,
                last_claimed_count = ?,
                last_claimed_details = ?,
                token = ?,
                history_pool = ?,
                is_active = 1,
                updated_at = ?
            WHERE key = ?
            """, (now_ts, count, details_str, tok, pool_str, now, key))
            conn.commit()
    else:
        # 兼容传统独立 meituan_accounts
        pool = acc.get("history_pool") or []
        tok = (new_token or acc.get("token") or "").strip()
        if tok and tok not in pool:
            pool.append(tok)
            pool = pool[-5:]
        pool_str = json.dumps(pool, ensure_ascii=False)
        with get_conn() as conn:
            conn.execute("""
            UPDATE meituan_accounts
            SET last_claimed_at = ?,
                last_claimed_count = ?,
                last_claimed_details = ?,
                token = ?,
                history_pool = ?,
                is_active = 1,
                updated_at = ?
            WHERE key = ?
            """, (now_ts, count, details_str, tok, pool_str, now, key))
            conn.execute("""
            UPDATE accounts
            SET last_claimed_at = ?,
                last_claimed_count = ?,
                last_claimed_details = ?,
                token = CASE WHEN platform = 'meituan' THEN ? ELSE token END,
                history_pool = ?,
                updated_at = ?
            WHERE key = ?
            """, (now_ts, count, details_str, tok, pool_str, now, key))
            conn.commit()




