"""
微信 ClawBot 原生客户端 (腾讯 iLink 官方灰度协议)
小蚕助手内置模块，完全脱离对外部第三方脚本或路径的依赖。
支持：
1. 原生获取二维码票据并转为 Base64 PNG 图片直接在 Web 界面呈现
2. 长轮询等待扫码、手机确认、双向数字配对码交互
3. 凭证持久化（优先 SQLite settings 表，兼顾 backend/data/clawbot-auth.json）
4. 通过 getupdates 监听微信发信以捕获并续期 context_token
5. 高可用消息推送（包含自动重试与鉴权失效预警）
"""

import os
import io
import json
import time
import uuid
import base64
import logging
from typing import Dict, Any, Optional, Tuple
import httpx
import qrcode
from PIL import Image

from ..models import database as db

logger = logging.getLogger("xiaocan.clawbot")

# 社区实测：context_token 是用户最后一条消息起算的约 24 小时滑动窗口；
# 官方接口未下发明确过期时间，因此这里采用保守本地预测，仅用于提前提醒，不作为服务端判定。
CONTEXT_TOKEN_TTL_SECONDS = 24 * 3600


def _extract_message_timestamp(message: Dict[str, Any]) -> Optional[int]:
    """提取官方消息时间，兼容秒/毫秒及多种字段命名。"""
    if not isinstance(message, dict):
        return None
    for key in ("create_time", "createTime", "timestamp", "msg_time", "msgTime", "time"):
        raw = message.get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 100_000_000_000:
            value /= 1000
        if value > 1_000_000_000:
            return int(value)
    return None


def _find_context_token(node: Any, depth: int = 0) -> Optional[str]:
    """递归查找官方消息中的 context_token，兼容消息体多一层嵌套的情况。"""
    if depth > 6 or node is None:
        return None
    if isinstance(node, dict):
        for key in ("context_token", "contextToken", "contextTokenStr"):
            value = node.get(key)
            if value and isinstance(value, (str, int, float)):
                return str(value)
        for value in node.values():
            found = _find_context_token(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_context_token(value, depth + 1)
            if found:
                return found
    return None


def get_session_status(auth: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """根据本地持久化的会话元数据计算可展示的 ClawBot 会话状态。"""
    if not auth or not auth.get("token") or not auth.get("userId"):
        return {
            "session_active": False,
            "session_status": "unbound",
            "has_context_token": False,
            "context_token_at": 0,
            "expires_at": 0,
            "remaining_seconds": 0,
            "last_verified_at": 0,
            "last_fail_code": 0,
        }

    has_token = bool(str(auth.get("contextToken") or "").strip())
    now = int(time.time())
    last_verified = int(auth.get("sessionLastVerifiedAt") or 0)
    last_fail_at = int(auth.get("sessionLastFailureAt") or 0)
    fail_code = int(auth.get("sessionLastFailCode") or 0)
    marked = str(auth.get("sessionStatus") or "").strip().lower()
    raw_context_at = int(auth.get("contextTokenAt") or auth.get("contextUpdatedAt") or 0)
    # 旧凭据可能没有独立的续期时间；最近一次验证成功可作为保守回退。
    context_at = raw_context_at or (last_verified if last_verified > last_fail_at else 0)

    expires_at = context_at + CONTEXT_TOKEN_TTL_SECONDS if context_at > 0 else 0
    remaining = max(0, expires_at - now) if expires_at else 0

    # 历史数据可能同时存在“已过期”标记和之后成功的推送时间。
    # 若成功验证时间/消息时间晚于失败时间，则以实际成功时间为准。
    stale_failure = raw_context_at > 0 and last_fail_at <= max(raw_context_at, last_verified)
    failure_active = (not stale_failure) and (
        marked in ("expired", "credential_expired") or fail_code in (-2, -14)
    )

    if not has_token:
        status = "pending"
    elif failure_active:
        status = marked if marked in ("expired", "credential_expired") else "expired"
    elif context_at <= 0:
        # 旧凭据没有续期时间：不误判为已过期，但也不宣称处于已验证活跃状态。
        status = "unverified"
    elif remaining <= 0:
        status = "expired"
    elif remaining <= 3600:
        status = "expiring"
    else:
        status = "active"

    return {
        "session_active": status in ("active", "expiring", "unverified"),
        "session_status": status,
        "has_context_token": has_token,
        "context_token_at": context_at,
        "expires_at": expires_at,
        "remaining_seconds": remaining,
        "last_verified_at": last_verified,
        "last_fail_code": fail_code,
        "last_failure_at": last_fail_at,
    }


def mark_session_success(auth: Dict[str, Any], custom_path: Optional[str] = None) -> None:
    """一次推送成功后刷新已验证时间，并清除会话失效标记。"""
    now = int(time.time())
    auth["sessionStatus"] = "active"
    auth["sessionLastFailCode"] = 0
    auth["sessionLastFailureAt"] = 0
    auth["sessionLastVerifiedAt"] = now
    # 旧凭据缺少续期时间时，用本次成功时间建立保守预测基准。
    if not auth.get("contextTokenAt") and auth.get("contextToken"):
        auth["contextTokenAt"] = now
    save_auth(auth, custom_path)


def mark_session_failure(
    auth: Dict[str, Any],
    fail_code: int,
    custom_path: Optional[str] = None,
    status: str = "expired"
) -> None:
    """官方明确拒绝会话时，持久化失效状态，避免界面继续显示活跃。"""
    auth["sessionStatus"] = status
    auth["sessionLastFailCode"] = int(fail_code)
    auth["sessionLastFailureAt"] = int(time.time())
    save_auth(auth, custom_path)


def get_daily_send_count() -> int:
    """读取本地自然日推送计数；跨天自动归零。"""
    today = time.strftime("%Y-%m-%d")
    stored_date = str(db.get_setting("clawbot_daily_sent_date", "") or "")
    if stored_date != today:
        db.set_setting("clawbot_daily_sent_date", today)
        db.set_setting("clawbot_daily_sent_count", 0)
        return 0
    try:
        return max(0, int(db.get_setting("clawbot_daily_sent_count", 0) or 0))
    except (TypeError, ValueError):
        return 0


def record_daily_send() -> int:
    """成功推送一条后累计本地计数。"""
    count = get_daily_send_count() + 1
    db.set_setting("clawbot_daily_sent_count", count)
    return count


# 腾讯 iLink 官方灰度协议标准参数
BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_CHANNEL_VERSION = "2.4.3"
# 编码: 0x00MMNNPP (major<<16 | minor<<8 | patch) -> (2<<16 | 4<<8 | 3) = 132100
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 3)
BOT_AGENT = "xiaocan-assistant/2.1.0"

# 本地数据文件路径 (backend/data/clawbot-auth.json)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
LOCAL_AUTH_FILE = os.path.join(DATA_DIR, "clawbot-auth.json")


def _random_wechat_uin() -> str:
    """X-WECHAT-UIN: 随机 4 字节 uint32 转十进制字符串后再 base64 编码"""
    uint32 = int.from_bytes(os.urandom(4), byteorder="big")
    return base64.b64encode(str(uint32).encode("utf-8")).decode("utf-8")


def _build_headers(token: Optional[str] = None) -> Dict[str, str]:
    """生成腾讯 iLink 协议认证请求头"""
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def save_auth(auth_data: Dict[str, Any], custom_path: Optional[str] = None) -> bool:
    """
    持久化 ClawBot 凭据：
    1. 存储至 SQLite 数据库 settings 表
    2. 存储至本地 backend/data/clawbot-auth.json 文件
    3. 如果指定了 custom_path 则同步写入该路径
    """
    try:
        # 1. 写入 SQLite
        db.set_setting("clawbot_auth", auth_data)

        # 2. 写入项目本地 data 目录
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOCAL_AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(auth_data, f, ensure_ascii=False, indent=2)

        # 3. 同步写入自定义路径 (若有)
        if custom_path and custom_path.strip():
            target_p = os.path.abspath(custom_path.strip())
            p_dir = os.path.dirname(target_p)
            if p_dir:
                os.makedirs(p_dir, exist_ok=True)
            with open(target_p, "w", encoding="utf-8") as f:
                json.dump(auth_data, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        logger.error(f"保存 ClawBot 凭证失败: {e}")
        return False


def clear_auth(custom_path: Optional[str] = None) -> bool:
    """清除本地存储的 ClawBot 凭据"""
    try:
        db.set_setting("clawbot_auth", None)
        if os.path.exists(LOCAL_AUTH_FILE):
            try:
                os.remove(LOCAL_AUTH_FILE)
            except Exception:
                pass
        if custom_path and os.path.exists(custom_path):
            try:
                os.remove(custom_path)
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error(f"清除 ClawBot 凭证异常: {e}")
        return False


def load_auth(
    custom_path: Optional[str] = None,
    auth_json_str: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    读取 ClawBot 凭据，读取优先级：
    1. 显式传入的 JSON 字符串
    2. SQLite 数据库设置 (clawbot_auth)
    3. 本地专属数据文件 (backend/data/clawbot-auth.json)
    4. 显式指定的文件路径 (custom_path) 或数据库设置的自定义路径
    """
    # 1. 内存直接 JSON
    if auth_json_str and auth_json_str.strip():
        try:
            data = json.loads(auth_json_str.strip())
            if isinstance(data, dict) and data.get("token") and data.get("userId"):
                return data, "使用前端传入的直接凭证"
        except Exception:
            pass

    # 2. SQLite 数据库
    db_auth = db.get_setting("clawbot_auth")
    if db_auth and isinstance(db_auth, dict) and db_auth.get("token") and db_auth.get("userId"):
        return db_auth, "使用本地 SQLite 存储的凭据"

    # 3. 本地专属数据文件
    if os.path.exists(LOCAL_AUTH_FILE):
        try:
            with open(LOCAL_AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("token") and data.get("userId"):
                    return data, f"使用项目本地数据凭据: {LOCAL_AUTH_FILE}"
        except Exception as e:
            logger.debug(f"读取本地凭据文件失败: {e}")

    # 4. 自定义路径
    candidate_paths = []
    if custom_path and custom_path.strip():
        candidate_paths.append(custom_path.strip())
    db_custom_path = (db.get_setting("clawbot_auth_path", "") or "").strip()
    if db_custom_path:
        candidate_paths.append(db_custom_path)

    for p in candidate_paths:
        try:
            if os.path.exists(p) and os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data.get("token") and data.get("userId"):
                        return data, f"从外部自定义文件读取: {p}"
        except Exception as e:
            logger.debug(f"读取自定义凭证文件 {p} 失败: {e}")

    return None, "未找到有效的微信 ClawBot 凭据"


def _generate_qr_data_url(content: str) -> str:
    """使用内存 qrcode 生成 PNG Base64 Data URL"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


async def get_qr_code(local_token: Optional[str] = None) -> Dict[str, Any]:
    """
    向腾讯 iLink 官方接口申请 ClawBot 登录二维码
    返回包含 qrcode 票据与 Base64 格式的 PNG 二维码图像
    """
    auth, _ = load_auth()
    tokens = []
    if local_token and local_token.strip():
        tokens.append(local_token.strip())
    elif auth and auth.get("token"):
        tokens.append(auth.get("token"))

    url = f"{BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3"
    payload = {"local_token_list": tokens}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=_build_headers())
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "message": f"腾讯接口 HTTP 响应异常: {resp.status_code}"
                }
            data = resp.json()
            qrcode_ticket = data.get("qrcode")
            qrcode_img_content = data.get("qrcode_img_content")

            if not qrcode_ticket:
                return {"ok": False, "message": "未返回有效的二维码票据"}

            # 生成 Base64 Data URL 图像直接返回供前端渲染
            qr_content_for_image = qrcode_img_content or qrcode_ticket
            qr_data_url = _generate_qr_data_url(qr_content_for_image)

            return {
                "ok": True,
                "qrcode": qrcode_ticket,
                "qr_image": qr_data_url,
                "qr_url": qrcode_img_content or "",
                "message": "二维码获取成功"
            }
    except Exception as e:
        logger.error(f"获取微信 ClawBot 二维码失败: {e}")
        return {"ok": False, "message": f"请求异常: {str(e)}"}


async def poll_qr_status(
    qrcode_ticket: str,
    verify_code: Optional[str] = None,
    timeout: float = 25.0
) -> Dict[str, Any]:
    """
    长轮询检查二维码状态
    处理 wait, scaned, need_verifycode, expired, verify_code_blocked, scaned_but_redirect, confirmed
    """
    if not qrcode_ticket or not qrcode_ticket.strip():
        return {"ok": False, "status": "error", "message": "二维码票据不能为空"}

    params = {"qrcode": qrcode_ticket.strip()}
    if verify_code and verify_code.strip():
        params["verify_code"] = verify_code.strip()

    url = f"{BASE_URL}/ilink/bot/get_qrcode_status"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=_build_headers())
            if resp.status_code != 200:
                return {"ok": False, "status": "network_error", "message": f"HTTP {resp.status_code}"}

            data = resp.json()
            status = data.get("status", "wait")

            if status == "wait":
                return {"ok": True, "status": "wait", "message": "等待手机微信扫码"}

            elif status == "scaned":
                return {"ok": True, "status": "scaned", "message": "微信已扫码，请在手机上点击确认授权"}

            elif status == "need_verifycode":
                return {
                    "ok": True,
                    "status": "need_verifycode",
                    "message": "需要在网页端输入手机微信展示的配对验证数字"
                }

            elif status in ("expired", "verify_code_blocked"):
                msg = "二维码已过期失效" if status == "expired" else "配对验证码输入错误次数过多已被拦截"
                return {"ok": False, "status": status, "message": msg}

            elif status == "binded_redirect":
                return {
                    "ok": False,
                    "status": "binded_redirect",
                    "message": "该微信号已在其他 ClawBot 客户端绑定，请在原客户端解绑后重试"
                }

            elif status == "confirmed":
                bot_token = data.get("bot_token")
                ilink_bot_id = data.get("ilink_bot_id")
                ilink_user_id = data.get("ilink_user_id")

                if not bot_token or not ilink_user_id:
                    return {"ok": False, "status": "error", "message": "授权成功但未返回完整凭证"}

                auth_data = {
                    "token": bot_token,
                    "accountId": ilink_bot_id or "",
                    "userId": ilink_user_id,
                    "contextToken": "",
                    "getUpdatesBuf": "",
                    "savedAt": str(uuid.uuid4())
                }
                save_auth(auth_data)
                return {
                    "ok": True,
                    "status": "confirmed",
                    "message": "微信 ClawBot 授权成功，凭证已保存",
                    "user_id": ilink_user_id,
                    "account_id": ilink_bot_id
                }

            elif status == "scaned_but_redirect":
                redirect_host = data.get("redirect_host")
                return {
                    "ok": True,
                    "status": "scaned_but_redirect",
                    "redirect_host": redirect_host,
                    "message": f"节点重定向: {redirect_host}"
                }

            else:
                return {"ok": True, "status": status, "message": f"当前状态: {status}"}

    except httpx.TimeoutException:
        # 长轮询正常超时，继续等待即可
        return {"ok": True, "status": "wait", "message": "长轮询等待中"}
    except Exception as e:
        logger.warning(f"轮询二维码状态异常: {e}")
        return {"ok": False, "status": "network_error", "message": str(e)}


async def check_activation(timeout: float = 45.0, retry_empty_cursor: bool = True) -> Dict[str, Any]:
    """
    通过 getupdates 接口长轮询捕获用户发给微信 ClawBot 的消息，
    提取 context_token 并持久化，完成会话双向激活。
    """
    auth, src = load_auth()
    if not auth or not auth.get("token"):
        return {"ok": False, "activated": False, "message": "未检测到有效 ClawBot 凭证"}

    token = auth["token"]
    get_updates_buf = auth.get("getUpdatesBuf", "")

    url = f"{BASE_URL}/ilink/bot/getupdates"
    payload = {
        "get_updates_buf": get_updates_buf,
        "base_info": {
            "channel_version": ILINK_CHANNEL_VERSION,
            "bot_agent": BOT_AGENT
        }
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=_build_headers(token))
            if resp.status_code in (401, 403):
                return {"ok": False, "activated": False, "message": "凭证已过期或鉴权失败"}
            if resp.status_code != 200:
                return {"ok": False, "activated": False, "message": f"HTTP {resp.status_code}"}

            data = resp.json()
            ret = data.get("ret", 0)
            if ret != 0:
                return {"ok": False, "activated": False, "message": f"接口返回错误: {ret}"}

            new_buf = data.get("get_updates_buf")
            if new_buf:
                auth["getUpdatesBuf"] = new_buf

            msgs = data.get("msgs") or []
            token_candidates = []
            for index, m in enumerate(msgs):
                token_value = _find_context_token(m)
                if not token_value:
                    continue
                msg_at = _extract_message_timestamp(m) or 0
                token_candidates.append((msg_at, index, token_value, m))
            found_token = None
            found_at = 0
            if token_candidates:
                # 空游标重试可能返回多条历史消息，优先取时间最新的一条。
                _, _, found_token, found_msg = max(token_candidates, key=lambda item: (item[0], item[1]))
                found_at = _extract_message_timestamp(found_msg) or int(time.time())
                if isinstance(found_msg, dict) and found_msg.get("from_user_id"):
                    auth["userId"] = found_msg.get("from_user_id")

            if found_token:
                auth["contextToken"] = found_token
                auth["contextTokenAt"] = found_at
                auth["sessionStatus"] = "active"
                auth["sessionLastFailCode"] = 0
                auth["sessionLastFailureAt"] = 0
                auth["sessionLastVerifiedAt"] = int(time.time())
                save_auth(auth)
                return {
                    "ok": True,
                    "activated": True,
                    "has_context_token": True,
                    **get_session_status(auth),
                    "message": "成功接收到微信会话消息，推送通道已激活就绪！"
                }

            # 游标可能已被其他端推进；回退空游标重试一次，避免漏掉刚发送的消息。
            if retry_empty_cursor and get_updates_buf:
                logger.info("ClawBot 当前游标未返回消息，尝试使用空游标恢复历史消息")
                auth["getUpdatesBuf"] = ""
                save_auth(auth)
                return await check_activation(timeout=min(timeout, 15.0), retry_empty_cursor=False)

            # 未捕获新消息不得报告激活成功：旧 context_token 可能是过期快照。
            save_auth(auth)
            status = get_session_status(auth)
            return {
                "ok": True,
                "activated": False,
                "has_context_token": bool(auth.get("contextToken")),
                **status,
                "message": "暂未检测到微信新消息，请在手机微信向 ClawBot 发送任意文字后再次检测"
            }
    except httpx.TimeoutException:
        if retry_empty_cursor and get_updates_buf:
            logger.info("ClawBot 当前游标长轮询超时，尝试使用空游标恢复历史消息")
            auth["getUpdatesBuf"] = ""
            save_auth(auth)
            return await check_activation(timeout=min(timeout, 15.0), retry_empty_cursor=False)
        save_auth(auth)
        status = get_session_status(auth)
        return {
            "ok": True,
            "activated": False,
            "has_context_token": bool(auth.get("contextToken")),
            **status,
            "message": "轮询超时，暂未检测到微信新消息"
        }
    except Exception as e:
        logger.error(f"检查 ClawBot 激活状态失败: {e}")
        return {"ok": False, "activated": False, "message": f"网络通信异常: {str(e)}"}


async def send_message(
    title: str,
    content: str,
    custom_path: Optional[str] = None,
    auth_json_str: Optional[str] = None,
    count_quota: bool = True
) -> Dict[str, Any]:
    """
    通过腾讯 iLink 官方接口向已绑定的微信发送通知消息
    """
    auth, src_msg = load_auth(custom_path, auth_json_str)
    if not auth:
        return {"ok": False, "channel": "clawbot", "message": f"ClawBot 未就绪: {src_msg}"}

    token = auth.get("token", "").strip()
    user_id = auth.get("userId", "").strip()
    context_token = auth.get("contextToken", "").strip() if auth.get("contextToken") else ""

    if not token or not user_id:
        return {"ok": False, "channel": "clawbot", "message": "ClawBot 凭证缺少 token 或 userId"}

    text = f"【XiaoCan Assistant】{title}\n\n{content}"
    client_id = f"openclaw-weixin-{uuid.uuid4().hex}"

    msg_body: Dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": user_id,
        "client_id": client_id,
        "message_type": 2,
        "message_state": 2,
        "item_list": [{"type": 1, "text_item": {"text": text}}]
    }
    if context_token:
        msg_body["context_token"] = context_token

    payload = {
        "msg": msg_body,
        "base_info": {
            "channel_version": ILINK_CHANNEL_VERSION,
            "bot_agent": BOT_AGENT
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{BASE_URL}/ilink/bot/sendmessage",
                json=payload,
                headers=_build_headers(token)
            )
            if resp.status_code in (401, 403):
                return {"ok": False, "channel": "clawbot", "message": "ClawBot 凭据鉴权失败或已过期 (HTTP 401/403)"}
            if resp.status_code != 200:
                return {"ok": False, "channel": "clawbot", "message": f"ClawBot 接口 HTTP 异常: {resp.status_code}"}

            data = resp.json()
            ret = data.get("ret", 0)
            if ret == 0:
                # 通知通道会固定传入空字符串覆盖参数；只要实际使用的是本地默认凭据，
                # 就应回写会话状态，否则会停留在旧的“已过期”显示但消息仍能送达。
                uses_local_auth = not auth_json_str and (not custom_path or str(custom_path).strip() == LOCAL_AUTH_FILE)
                if uses_local_auth:
                    mark_session_success(auth, custom_path if custom_path and str(custom_path).strip() == LOCAL_AUTH_FILE else None)
                daily_count = get_daily_send_count()
                if count_quota:
                    daily_count = record_daily_send()
                return {
                    "ok": True,
                    "channel": "clawbot",
                    "message": "微信 ClawBot 推送成功",
                    "daily_send_count": daily_count,
                    "quota_counted": count_quota,
                }
            elif ret == -14:
                uses_local_auth = not auth_json_str and (not custom_path or str(custom_path).strip() == LOCAL_AUTH_FILE)
                if uses_local_auth:
                    mark_session_failure(auth, -14, status="credential_expired")
                return {"ok": False, "channel": "clawbot", "return_code": ret, "message": "ClawBot 凭据已过期，请在设置中重新扫码登录"}
            elif ret == -2:
                uses_local_auth = not auth_json_str and (not custom_path or str(custom_path).strip() == LOCAL_AUTH_FILE)
                if uses_local_auth:
                    mark_session_failure(auth, -2, status="expired")
                return {
                    "ok": False,
                    "channel": "clawbot",
                    "return_code": ret,
                    "message": "ClawBot 会话尚未激活或上下文已过期，请在手机微信中向你的 ClawBot 机器人发送一条任意消息以建立会话"
                }
            else:
                errmsg = data.get("errmsg") or f"错误码 {ret}"
                return {"ok": False, "channel": "clawbot", "return_code": ret, "message": f"ClawBot 推送异常: {errmsg}"}
    except Exception as e:
        logger.warning(f"微信 ClawBot 推送请求异常: {e}")
        return {"ok": False, "channel": "clawbot", "message": f"网络通信错误: {str(e)}"}
