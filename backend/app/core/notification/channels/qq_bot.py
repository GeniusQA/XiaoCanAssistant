"""
QQ 聊天机器人推送适配器 (遵循 OneBot V11 HTTP 标准)
直连本地 NoneBot2 / mystool-bot / SnowLuma / NapCat 等协议端
"""
import logging
from typing import Dict, Any, List, Optional
import httpx
from .base import BaseNotifier
from ..models import NotificationData
from ....models import database as db

logger = logging.getLogger("xiaocan.notifier.qq_bot")


async def fetch_targets(api_url: str, token: Optional[str] = None) -> Dict[str, Any]:
    """通过 OneBot V11 标准公开 API 获取机器人所在群列表与好友列表。

    文档: https://flyqie.github.io/ob11-docs/api/public
    - get_group_list -> group_id / group_name
    - get_friend_list -> user_id / nickname / remark
    """
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "message": "QQ 机器人 API 地址未配置"}
    headers = {"Content-Type": "application/json"}
    auth_token = (token or "").strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async def call_action(action: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(base, json={"action": action, "params": {}}, headers=headers)
        except httpx.ConnectTimeout:
            return {"ok": False, "message": "连接 OneBot 协议端超时，请检查 HTTP 接口地址"}
        except Exception as e:
            return {"ok": False, "message": f"OneBot 通信异常: {e}"}
        if resp.status_code == 401:
            return {"ok": False, "message": "OneBot 鉴权失败(401): Access Token 错误"}
        if resp.status_code != 200:
            return {"ok": False, "message": f"OneBot HTTP 状态码: {resp.status_code}"}
        try:
            data = resp.json()
        except Exception:
            return {"ok": False, "message": f"OneBot {action} 响应不是合法 JSON"}
        if data.get("retcode") not in (0, None) or (data.get("status") not in ("ok", None)):
            return {"ok": False, "message": f"OneBot {action} 返回失败: {data.get('message') or data.get('wording') or data}"}
        rows = data.get("data")
        return {"ok": True, "rows": rows if isinstance(rows, list) else []}

    group_res = await call_action("get_group_list")
    friend_res = await call_action("get_friend_list")
    errors = [r["message"] for r in (group_res, friend_res) if not r["ok"]]
    if errors and not group_res["ok"] and not friend_res["ok"]:
        return {"ok": False, "message": "获取群与好友列表均失败：" + "; ".join(errors)}

    groups: List[Dict[str, Any]] = []
    for row in group_res.get("rows") or []:
        if not isinstance(row, dict):
            continue
        gid = str(row.get("group_id") or "").strip()
        if not gid or gid == "0":
            continue
        groups.append({
            "id": gid,
            "name": str(row.get("group_name") or f"QQ群 {gid}").strip(),
            "memberCount": row.get("member_count"),
        })

    friends: List[Dict[str, Any]] = []
    for row in friend_res.get("rows") or []:
        if not isinstance(row, dict):
            continue
        uid = str(row.get("user_id") or "").strip()
        if not uid or uid == "0":
            continue
        remark = str(row.get("remark") or "").strip()
        nickname = str(row.get("nickname") or "").strip()
        friends.append({
            "id": uid,
            "name": remark or nickname or f"QQ {uid}",
            "nickname": nickname,
            "remark": remark,
        })

    groups.sort(key=lambda g: g["name"])
    friends.sort(key=lambda f: f["name"])
    msg_parts = [f"发现 {len(groups)} 个群、{len(friends)} 个好友"]
    if errors:
        msg_parts.append("部分接口失败: " + "; ".join(errors))
    return {
        "ok": True,
        "groups": groups,
        "friends": friends,
        "groupError": None if group_res["ok"] else group_res["message"],
        "friendError": None if friend_res["ok"] else friend_res["message"],
        "message": "；".join(msg_parts),
    }


class QqBotNotifier(BaseNotifier):
    name = "qq_bot"
    display_name = "QQ 机器人 (OneBot V11)"

    async def _do_send(
        self,
        api_url: str,
        target_type: str,
        group_id: Optional[str],
        user_id: Optional[str],
        token: Optional[str],
        text: str
    ) -> Dict[str, Any]:
        raw_api = (api_url or "").strip().rstrip("/")
        if not raw_api:
            return {"ok": False, "channel": self.name, "message": "QQ 机器人 API 地址未配置"}

        ttype = (target_type or "group").strip()
        gid_str = (group_id or "").strip()
        uid_str = (user_id or "").strip()
        auth_token = (token or "").strip()

        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        sub_results = []
        errors = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 群聊推送
            if ttype in ("group", "both") and gid_str:
                try:
                    gid = int(gid_str)
                    endpoint = f"{raw_api}/send_group_msg"
                    payload = {"group_id": gid, "message": text}
                    resp = await client.post(endpoint, json=payload, headers=headers)
                    if resp.status_code == 200:
                        rdata = resp.json()
                        if rdata.get("status") == "ok" or rdata.get("retcode") == 0:
                            sub_results.append(f"群聊({gid})推送成功")
                        else:
                            errors.append(f"群聊({gid})响应失败: {rdata.get('message') or rdata}")
                    else:
                        errors.append(f"群聊 HTTP 状态码: {resp.status_code}")
                except Exception as e:
                    errors.append(f"群聊发送异常: {str(e)}")

            # 私聊推送
            if ttype in ("private", "both") and uid_str:
                try:
                    uid = int(uid_str)
                    endpoint = f"{raw_api}/send_private_msg"
                    payload = {"user_id": uid, "message": text}
                    resp = await client.post(endpoint, json=payload, headers=headers)
                    if resp.status_code == 200:
                        rdata = resp.json()
                        if rdata.get("status") == "ok" or rdata.get("retcode") == 0:
                            sub_results.append(f"私聊({uid})推送成功")
                        else:
                            errors.append(f"私聊({uid})响应失败: {rdata.get('message') or rdata}")
                    else:
                        errors.append(f"私聊 HTTP 状态码: {resp.status_code}")
                except Exception as e:
                    errors.append(f"私聊发送异常: {str(e)}")

        if not sub_results and not errors:
            return {"ok": False, "channel": self.name, "message": "未配置有效的群号或管理员 QQ 号"}

        ok = len(sub_results) > 0
        msg = "; ".join(sub_results) if ok else "; ".join(errors)
        return {"ok": ok, "channel": self.name, "message": msg, "errors": errors}

    async def send(self, data: NotificationData) -> Dict[str, Any]:
        if not db.get_setting("qq_bot_enabled", False):
            return {"ok": False, "channel": self.name, "skipped": True, "message": "QQ 机器人通道已关闭"}

        api_url = db.get_setting("qq_bot_api", "http://127.0.0.1:8080")
        target_type = db.get_setting("qq_bot_target_type", "group")
        group_id = db.get_setting("qq_bot_group_id", "")
        user_id = db.get_setting("qq_bot_user_id", "")
        token = db.get_setting("qq_bot_token", "")
        return await self._do_send(api_url, target_type, group_id, user_id, token, data.format_plain_text())

    async def test(self, config: Dict[str, Any]) -> Dict[str, Any]:
        api_url = config.get("qq_bot_api") or db.get_setting("qq_bot_api", "http://127.0.0.1:8080")
        target_type = config.get("qq_bot_target_type") or db.get_setting("qq_bot_target_type", "group")
        group_id = config.get("qq_bot_group_id") or db.get_setting("qq_bot_group_id", "")
        user_id = config.get("qq_bot_user_id") or db.get_setting("qq_bot_user_id", "")
        token = config.get("qq_bot_token") or db.get_setting("qq_bot_token", "")

        test_title = "通知连通性测试"
        test_content = (
            f"【XiaoCan Assistant】 {test_title}\n"
            "这是一条来自XiaoCan Assistant的连通性测试消息。如果你收到此消息，说明 OneBot V11 协议端已成功接入并正常工作。"
        )
        return await self._do_send(api_url, target_type, group_id, user_id, token, test_content)
