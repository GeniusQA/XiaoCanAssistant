"""
多端设备协同认证:
- PC (localhost) 直连信任, 免认证
- 移动端等远程设备通过「配对码」换取设备 JWT (30 天), 之后凭 JWT 访问 /api/**
- 小蚕官方凭据永不下发, 移动端仅作为瘦客户端通过后端代理访问
"""

import json
import logging
import secrets
import time
import uuid
from typing import Any, Dict, Optional

import jwt

from ..models.database import get_conn, set_setting, get_setting

logger = logging.getLogger("xiaocan.device_auth")

JWT_EXPIRE_DAYS = 30
PAIRING_TTL_SECONDS = 120

# 内存态配对码: code -> {secret, created_at, used}
_pairing_codes: Dict[str, Dict[str, Any]] = {}


def _jwt_secret() -> str:
    """首次调用生成持久化 JWT 签名密钥"""
    secret = get_setting("device_jwt_secret")
    if not secret:
        secret = secrets.token_hex(32)
        set_setting("device_jwt_secret", secret)
        logger.info("已生成设备认证 JWT 签名密钥")
    return secret


def ensure_device_table():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS paired_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT NOT NULL,
            jti TEXT NOT NULL UNIQUE,
            created_at TEXT,
            last_seen TEXT,
            revoked INTEGER DEFAULT 0
        )
        """)
        conn.commit()


def create_pairing_code() -> Dict[str, Any]:
    """生成一次性配对码 (6位数字, 有效期 120 秒)"""
    # 清理过期码
    now = time.time()
    for k in list(_pairing_codes.keys()):
        if now - _pairing_codes[k]["created_at"] > PAIRING_TTL_SECONDS:
            _pairing_codes.pop(k, None)

    code = f"{secrets.randbelow(1000000):06d}"
    secret = secrets.token_hex(16)
    _pairing_codes[code] = {"secret": secret, "created_at": now, "used": False}
    return {
        "code": code,
        "expires_in": PAIRING_TTL_SECONDS,
        "created_at": int(now),
    }


def redeem_pairing_code(code: str, device_name: str) -> Optional[Dict[str, Any]]:
    """校验配对码, 签发设备 JWT 并登记设备"""
    entry = _pairing_codes.get(str(code).strip())
    if not entry or entry["used"]:
        return None
    if time.time() - entry["created_at"] > PAIRING_TTL_SECONDS:
        _pairing_codes.pop(str(code).strip(), None)
        return None

    entry["used"] = True
    _pairing_codes.pop(str(code).strip(), None)

    ensure_device_table()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    jti = uuid.uuid4().hex
    name = (device_name or "").strip() or "未命名设备"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO paired_devices (device_name, jti, created_at, last_seen, revoked) VALUES (?, ?, ?, ?, 0)",
            (name, jti, now, now)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM paired_devices WHERE jti = ?", (jti,)).fetchone()

    token = jwt.encode(
        {"jti": jti, "device_id": row["id"], "device_name": name, "iat": int(time.time())},
        _jwt_secret(),
        algorithm="HS256"
    )
    return {"token": token, "device_id": row["id"], "device_name": name, "expires_days": JWT_EXPIRE_DAYS}


def verify_device_token(token: str) -> Optional[Dict[str, Any]]:
    """校验设备 JWT; 返回 payload, 无效/吊销返回 None"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except Exception:
        return None
    jti = payload.get("jti")
    if not jti:
        return None
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT revoked FROM paired_devices WHERE jti = ?", (jti,)).fetchone()
    except Exception:
        return None
    if not row or row["revoked"]:
        return None
    return payload


def mark_device_seen(payload: Dict[str, Any]):
    """节流更新设备最后活跃时间 (每设备每 60 秒最多写一次)"""
    device_id = payload.get("device_id")
    if not device_id:
        return
    now = time.time()
    cache_key = f"_dev_seen_{device_id}"
    last = globals().get(cache_key, 0)
    if now - last < 60:
        return
    globals()[cache_key] = now
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE paired_devices SET last_seen = ? WHERE id = ?",
                (time.strftime("%Y-%m-%d %H:%M:%S"), device_id)
            )
            conn.commit()
    except Exception:
        pass


def list_devices() -> list:
    ensure_device_table()
    with get_conn() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT id, device_name, created_at, last_seen, revoked FROM paired_devices ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_device(device_id: int) -> bool:
    ensure_device_table()
    with get_conn() as conn:
        cur = conn.execute("UPDATE paired_devices SET revoked = 1 WHERE id = ?", (device_id,))
        conn.commit()
        return cur.rowcount > 0


def export_state() -> str:
    """调试辅助: 返回模块状态概览 (不含敏感信息)"""
    return json.dumps({
        "pending_codes": len(_pairing_codes),
        "devices": len(list_devices()),
    }, ensure_ascii=False)


# 启动时确保表存在
try:
    ensure_device_table()
except Exception as e:
    logger.warning(f"设备表初始化提示: {e}")
