"""
Telegram Bot 通知推送适配器
支持本地 HTTP/SOCKS 代理与自定义反代 API 网关，彻底解决国内网络无法直连问题
"""
import logging
import re
from typing import Dict, Any, List, Optional
import httpx
from .base import BaseNotifier
from ..models import NotificationData
from ....models import database as db

logger = logging.getLogger("xiaocan.notifier.telegram")


def _telegram_client_kwargs(proxy_url: Optional[str] = None) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"timeout": 12.0}
    proxy = (proxy_url or "").strip()
    if proxy and proxy.startswith("http"):
        kwargs["proxy"] = proxy
    return kwargs


def _chat_label(chat: Dict[str, Any]) -> str:
    title = str(chat.get("title") or "").strip()
    if title:
        return title
    username = str(chat.get("username") or "").strip()
    if username:
        return f"@{username}"
    name = " ".join(
        part for part in (str(chat.get("first_name") or "").strip(), str(chat.get("last_name") or "").strip()) if part
    )
    return name or f"Chat {chat.get('id')}"


async def fetch_recent_chats(
    bot_token: str,
    proxy_url: Optional[str] = None,
    api_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """从 Telegram Bot API 的未确认更新中发现最近活跃的会话。

    Telegram 没有“列出机器人所在全部会话”的接口。getUpdates 只能看到最近 24 小时内
    尚未被确认的消息/入群事件，因此这里只做发现，不传 offset，避免确认(消耗)这些更新。
    """
    token = (bot_token or "").strip()
    if not token:
        return {"ok": False, "message": "请先填写 Telegram Bot Token"}
    base = (api_base_url or "").strip().rstrip("/") or "https://api.telegram.org"

    try:
        async with httpx.AsyncClient(**_telegram_client_kwargs(proxy_url)) as client:
            # 1. Webhook 与 getUpdates 互斥，先检测，避免给出误导性的空结果
            hook_res = await client.get(f"{base}/bot{token}/getWebhookInfo")
            if hook_res.status_code == 200:
                hook_data = hook_res.json()
                hook_result = hook_data.get("result") or {}
                webhook_url = str(hook_result.get("url") or "").strip()
                if hook_data.get("ok") and webhook_url:
                    return {
                        "ok": False,
                        "code": "WEBHOOK_CONFLICT",
                        "webhook_url": webhook_url,
                        "pending_update_count": hook_result.get("pending_update_count"),
                        "message": (
                            "该 Bot 已接入 Webhook（通常由外部 Agent/机器人框架占用），Telegram 不允许再用 getUpdates 读取会话。"
                            "所以即使你刚发过消息，这里也拿不到。请改用手动填写 Chat ID，或临时停用外部 Bot 的 Webhook 后再获取。"
                        ),
                    }

            # 2. 不传 offset：读取最早未确认更新，但不会确认/消耗它们
            resp = await client.get(
                f"{base}/bot{token}/getUpdates",
                params={
                    "limit": 100,
                    "allowed_updates": '["message","channel_post","my_chat_member","chat_join_request"]',
                },
            )
    except httpx.ConnectTimeout:
        return {"ok": False, "message": "连接 Telegram 超时，请配置本地代理或自定义 API 网关"}
    except Exception as e:
        logger.warning(f"Telegram 获取会话异常: {e}")
        return {"ok": False, "message": f"Telegram 通信异常: {e}"}

    if resp.status_code == 401:
        return {"ok": False, "message": "Telegram 认证失败(401): Bot Token 无效"}
    if resp.status_code == 409:
        return {"ok": False, "message": "该 Bot 正在使用 Webhook，无法通过 getUpdates 获取会话"}
    if resp.status_code != 200:
        return {"ok": False, "message": f"Telegram HTTP 状态码: {resp.status_code}"}

    data = resp.json()
    if not data.get("ok"):
        return {"ok": False, "message": f"Telegram 返回错误: {data.get('description') or data}"}

    updates = data.get("result") or []
    chats: Dict[str, Dict[str, Any]] = {}

    def add_chat(chat: Any) -> None:
        if not isinstance(chat, dict):
            return
        cid = str(chat.get("id") or "").strip()
        if not cid:
            return
        chats.setdefault(cid, {
            "id": cid,
            "type": str(chat.get("type") or "").strip(),
            "name": _chat_label(chat),
            "username": str(chat.get("username") or "").strip(),
        })

    for upd in updates if isinstance(updates, list) else []:
        if not isinstance(upd, dict):
            continue
        for key in ("message", "edited_message", "channel_post", "edited_channel_post", "business_message"):
            msg = upd.get(key)
            if isinstance(msg, dict):
                add_chat(msg.get("chat"))
        for key in ("my_chat_member", "chat_member", "chat_join_request"):
            item = upd.get(key)
            if isinstance(item, dict):
                add_chat(item.get("chat"))
        cq = upd.get("callback_query")
        if isinstance(cq, dict) and isinstance(cq.get("message"), dict):
            add_chat(cq["message"].get("chat"))

    type_names = {
        "private": "私聊", "group": "群组", "supergroup": "超级群组", "channel": "频道",
    }
    items: List[Dict[str, Any]] = []
    for cid, chat in chats.items():
        items.append({
            "id": cid,
            "name": chat["name"],
            "type": chat["type"],
            "typeName": type_names.get(chat["type"], chat["type"] or "会话"),
            "username": chat["username"],
        })
    items.sort(key=lambda c: (c["typeName"], c["name"]))
    hint = ""
    if not items:
        hint = (
            "；未发现未确认更新。即使刚给机器人发过消息，只要另一个客户端/外部 Agent 正在用长轮询消费更新，"
            "getUpdates 也会返回空。Telegram 不支持列出全部会话，此时请用 @userinfobot 查询 Chat ID 后手动填写"
        )
    return {
        "ok": True,
        "chats": items,
        "total": len(items),
        "update_count": len(updates) if isinstance(updates, list) else 0,
        "message": f"从最近未读更新中发现 {len(items)} 个会话（Telegram 不支持列出全部会话，仅显示最近活跃的）{hint}",
    }


class TelegramNotifier(BaseNotifier):
    name = "telegram"
    display_name = "Telegram 机器人"

    async def _do_send(
        self,
        bot_token: str,
        chat_id: str,
        text: str,
        proxy_url: Optional[str] = None,
        api_base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        token = (bot_token or "").strip()
        cid = (chat_id or "").strip()
        if not token or not cid:
            return {"ok": False, "channel": self.name, "message": "Telegram Bot Token 或 Chat ID 未配置"}

        base = (api_base_url or "").strip().rstrip("/")
        if not base:
            base = "https://api.telegram.org"

        url = f"{base}/bot{token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            async with httpx.AsyncClient(**_telegram_client_kwargs(proxy_url)) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    res_data = resp.json()
                    if res_data.get("ok"):
                        return {"ok": True, "channel": self.name, "message": "Telegram 消息发送成功"}
                    return {"ok": False, "channel": self.name, "message": f"Telegram 失败: {res_data.get('description')}"}
                if resp.status_code == 401:
                    return {"ok": False, "channel": self.name, "message": "Telegram 认证失败(401): Bot Token 无效"}
                if resp.status_code == 400:
                    return {"ok": False, "channel": self.name, "message": f"Telegram 参数错误(400): 请检查 Chat ID 是否正确或已向 Bot 发送过 /start"}
                return {"ok": False, "channel": self.name, "message": f"Telegram HTTP 状态码: {resp.status_code}"}
        except httpx.ConnectTimeout:
            hint = "连接超时。如在中国大陆网络环境下，请在下方配置本地网络代理(如 http://127.0.0.1:7890)或使用反代 API 网关" if not proxy else "代理连接超时，请检查代理端口是否正常开启"
            return {"ok": False, "channel": self.name, "message": f"Telegram 连接超时: {hint}"}
        except Exception as e:
            logger.warning(f"Telegram 推送异常: {e}")
            return {"ok": False, "channel": self.name, "message": f"Telegram 通信异常: {str(e)}"}

    async def send(self, data: NotificationData) -> Dict[str, Any]:
        if not db.get_setting("telegram_enabled", False):
            return {"ok": False, "channel": self.name, "skipped": True, "message": "Telegram 通道已关闭"}

        bot_token = db.get_setting("tg_bot_token", "")
        chat_id = db.get_setting("tg_chat_id", "")
        proxy_url = db.get_setting("tg_proxy_url", "")
        api_base_url = db.get_setting("tg_api_base_url", "")
        return await self._do_send(bot_token, chat_id, data.format_markdown(), proxy_url, api_base_url)

    async def test(self, config: Dict[str, Any]) -> Dict[str, Any]:
        bot_token = config.get("tg_bot_token") or db.get_setting("tg_bot_token", "")
        chat_id = config.get("tg_chat_id") or db.get_setting("tg_chat_id", "")
        proxy_url = config.get("tg_proxy_url") or db.get_setting("tg_proxy_url", "")
        api_base_url = config.get("tg_api_base_url") or db.get_setting("tg_api_base_url", "")
        test_title = "通知连通性测试"
        test_text = (
            f"*【XiaoCan Assistant】 {test_title}*\n\n"
            "这是一条来自XiaoCan Assistant的连通性测试消息。如果你收到此消息，"
            "说明 Telegram 机器人通道已成功连通并正常工作。"
        )
        return await self._do_send(bot_token, chat_id, test_text, proxy_url, api_base_url)
