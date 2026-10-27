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
# 配对码有效期: 10 分钟 (跨设备输入 + 可能的中途切换 App, 给足操作时间; 一次性使用)
PAIRING_TTL_SECONDS = 600


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
            ip TEXT,
            expires_at TEXT,
            revoked INTEGER DEFAULT 0
        )
        """)
        # 兼容旧表: 补充 ip / expires_at 列
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(paired_devices)").fetchall()]
            if "ip" not in cols:
                conn.execute("ALTER TABLE paired_devices ADD COLUMN ip TEXT")
            if "expires_at" not in cols:
                conn.execute("ALTER TABLE paired_devices ADD COLUMN expires_at TEXT")
        except Exception:
            pass
        # 配对码持久化存储 (进程重启不丢; 一次性使用)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pairing_codes (
            code TEXT PRIMARY KEY,
            created_ts INTEGER NOT NULL,
            used INTEGER DEFAULT 0
        )
        """)
        conn.commit()


def create_pairing_code() -> Dict[str, Any]:
    """生成一次性配对码 (6位数字, 有效期 5 分钟); 持久化存储, 后端重启后依然可用"""
    ensure_device_table()
    now = int(time.time())
    code = f"{secrets.randbelow(1000000):06d}"
    with get_conn() as conn:
        # 清理过期码, 避免表膨胀
        conn.execute("DELETE FROM pairing_codes WHERE created_ts < ?", (now - PAIRING_TTL_SECONDS,))
        conn.execute(
            "INSERT OR REPLACE INTO pairing_codes (code, created_ts, used) VALUES (?, ?, 0)",
            (code, now)
        )
        conn.commit()
    return {"code": code, "expires_in": PAIRING_TTL_SECONDS, "created_at": now}


def redeem_pairing_code(code: str, device_name: str, return_reason: bool = False, client_ip: str = ""):
    """
    校验配对码, 签发设备 JWT 并登记设备。
    return_reason=True 时返回 (result, reason) 便于前端展示具体失败原因。
    """
    code = str(code or "").strip()
    ensure_device_table()
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT code, created_ts, used FROM pairing_codes WHERE code = ?", (code,)).fetchone()

    reason = ""
    if not row:
        reason = "配对码不存在，请确认输入的是 PC 端最新生成的 6 位数字"
    elif row["used"]:
        reason = "该配对码已被使用过（一次性），请在 PC 端重新生成"
    elif now - int(row["created_ts"]) > PAIRING_TTL_SECONDS:
        reason = "配对码已过期（有效期 10 分钟），请在 PC 端重新生成"

    if reason:
        return (None, reason) if return_reason else None

    # 标记已使用 (幂等: 只有仍为未使用状态才更新成功)
    with get_conn() as conn:
        cur = conn.execute("UPDATE pairing_codes SET used = 1 WHERE code = ? AND used = 0", (code,))
        conn.commit()
        if cur.rowcount == 0:
            return (None, "该配对码已被使用过（一次性），请在 PC 端重新生成") if return_reason else None
    now_ts = time.time()
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
    expires_ts = now_ts + JWT_EXPIRE_DAYS * 86400
    expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_ts))
    jti = uuid.uuid4().hex
    raw_name = (device_name or "").strip()
    ip = (client_ip or "").strip()
    with get_conn() as conn:
        # 复用原记录: 优先同名, 其次同 IP (同一局域网设备; 名称可能被改过或留空, IP 更稳定)
        existing = None
        if raw_name:
            existing = conn.execute(
                "SELECT id, device_name FROM paired_devices WHERE device_name = ? ORDER BY id DESC LIMIT 1", (raw_name,)
            ).fetchone()
        if not existing and ip and ip not in ("127.0.0.1", "::1"):
            existing = conn.execute(
                "SELECT id, device_name FROM paired_devices WHERE ip = ? ORDER BY id DESC LIMIT 1", (ip,)
            ).fetchone()

        if existing:
            dev_id = existing["id"]
            # 本次未填名称 → 保留用户此前编辑过的名称, 不覆盖为"未命名设备"
            final_name = raw_name or existing["device_name"] or "未命名设备"
            conn.execute(
                "UPDATE paired_devices SET device_name = ?, jti = ?, created_at = ?, last_seen = ?, ip = ?, expires_at = ?, revoked = 0 WHERE id = ?",
                (final_name, jti, now, now, ip or None, expires_at, dev_id)
            )
        else:
            final_name = raw_name or "未命名设备"
            conn.execute(
                "INSERT INTO paired_devices (device_name, jti, created_at, last_seen, ip, expires_at, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (final_name, jti, now, now, ip or None, expires_at)
            )
            dev_id = conn.execute("SELECT id FROM paired_devices WHERE jti = ?", (jti,)).fetchone()["id"]
        conn.commit()

    # 旧 JWT (旧 jti) 因 jti 已替换而自动失效, 同设备仅保留最新有效凭证
    # exp: 真正写入过期时间 (此前缺失导致凭证永不过期)
    token = jwt.encode(
        {
            "jti": jti,
            "device_id": dev_id,
            "device_name": final_name,
            "iat": int(now_ts),
            "exp": int(expires_ts),
        },
        _jwt_secret(),
        algorithm="HS256"
    )
    result = {
        "token": token,
        "device_id": dev_id,
        "device_name": final_name,
        "expires_days": JWT_EXPIRE_DAYS,
        "expires_at": expires_at,
    }
    return (result, "") if return_reason else result


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
            row = conn.execute("SELECT revoked, expires_at FROM paired_devices WHERE jti = ?", (jti,)).fetchone()
    except Exception:
        return None
    if not row or row["revoked"]:
        return None
    # 双保险: DB 侧过期校验 (老凭证无 exp 字段时也能按记录有效期失效)
    expires_at = row["expires_at"]
    if expires_at:
        try:
            if time.time() > time.mktime(time.strptime(str(expires_at), "%Y-%m-%d %H:%M:%S")):
                return None
        except Exception:
            pass
    return payload


def mark_device_seen(payload: Dict[str, Any], client_ip: str = ""):
    """节流更新设备最后活跃时间与 IP (每设备每 60 秒最多写一次)"""
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
            if client_ip:
                conn.execute(
                    "UPDATE paired_devices SET last_seen = ?, ip = ? WHERE id = ?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), client_ip, device_id)
                )
            else:
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
            "SELECT id, device_name, created_at, last_seen, ip, expires_at, revoked FROM paired_devices ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_device(device_id: int) -> bool:
    ensure_device_table()
    with get_conn() as conn:
        cur = conn.execute("UPDATE paired_devices SET revoked = 1 WHERE id = ?", (device_id,))
        conn.commit()
        return cur.rowcount > 0


def rename_device(device_id: int, new_name: str) -> tuple:
    """重命名已配对设备 (返回 (成功, 原因))"""
    name = (new_name or "").strip()
    if not name:
        return False, "设备名称不能为空"
    if len(name) > 24:
        return False, "设备名称最多 24 个字符"
    ensure_device_table()
    with get_conn() as conn:
        exists = conn.execute("SELECT id FROM paired_devices WHERE id = ?", (device_id,)).fetchone()
        if not exists:
            return False, "设备不存在"
        dup = conn.execute(
            "SELECT id FROM paired_devices WHERE device_name = ? AND id != ?", (name, device_id)
        ).fetchone()
        if dup:
            return False, f"已存在名为「{name}」的设备，请换一个名称"
        conn.execute("UPDATE paired_devices SET device_name = ? WHERE id = ?", (name, device_id))
        conn.commit()
    return True, ""


def purge_device(device_id: int) -> bool:
    """从配对列表彻底删除设备记录 (仅允许删除已吊销或已过期的设备)"""
    ensure_device_table()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM paired_devices WHERE id = ? AND (revoked = 1 OR (expires_at IS NOT NULL AND expires_at < ?))",
            (device_id, now_str)
        )
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
