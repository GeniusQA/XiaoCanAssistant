"""
WxPusher 微信推送服务适配器
微信扫码关注 WxPusher 公众号，免搭建且配额充足
"""
import logging
import re
from typing import Dict, Any, List
import httpx
from .base import BaseNotifier
from ..models import NotificationData
from ....models import database as db

logger = logging.getLogger("xiaocan.notifier.wxpusher")


async def fetch_users(app_token: str, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
    """调用 WxPusher 官方开放接口「查询用户列表V2」拉取关注该应用的微信用户。

    官方文档: https://wxpusher.zjiecode.com/docs/#/?id=user-list
    GET https://wxpusher.zjiecode.com/api/fun/wxuser/v2?appToken=...&page=1&pageSize=100
    """
    token = (app_token or "").strip()
    if not token:
        return {"ok": False, "message": "请先填写 WxPusher 应用 Token (appToken)"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                "https://wxpusher.zjiecode.com/api/fun/wxuser/v2",
                params={
                    "appToken": token,
                    "page": max(1, int(page)),
                    "pageSize": min(max(1, int(page_size)), 100),
                    "isBlock": "false",  # 只查正常（未拉黑）用户，与官方后台一致
                    "type": 0,           # 0=关注应用的用户，1=关注主题的用户
                },
            )
            if resp.status_code != 200:
                return {"ok": False, "message": f"WxPusher HTTP 状态异常: {resp.status_code}"}
            data = resp.json()
    except Exception as e:
        logger.warning(f"WxPusher 拉取用户列表异常: {e}")
        return {"ok": False, "message": f"WxPusher 通信异常: {e}"}

    if int(data.get("code") or 0) != 1000:
        return {"ok": False, "message": f"WxPusher 返回错误: {data.get('msg') or data}"}

    # 官方 V2 返回: {"code":1000,"data":{"total":N,"page":1,"pageSize":20,"records":[...]}}
    # 兼容 data 直接是 list 的旧版/异常返回
    payload = data.get("data")
    raw_users = payload.get("records") if isinstance(payload, dict) else payload
    if raw_users is None and isinstance(payload, dict):
        raw_users = payload.get("list") or []
    users: List[Dict[str, Any]] = []
    for u in raw_users if isinstance(raw_users, list) else []:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("uid") or "").strip()
        if not uid:
            continue
        users.append({
            "uid": uid,
            "nickname": str(u.get("nickName") or u.get("nickname") or "").strip(),
            "status": u.get("enable", u.get("status")),
            "face": str(u.get("headImg") or u.get("face") or "").strip(),
            "createTime": u.get("createTime") or u.get("create_time"),
        })
    total = int(payload.get("total") or len(users)) if isinstance(payload, dict) else len(users)
    return {
        "ok": True,
        "users": users,
        "total": total,
        "page": int(payload.get("page") or page) if isinstance(payload, dict) else page,
        "message": f"已从 WxPusher 获取 {len(users)} 个用户（共 {total} 个，第 {page} 页）",
    }


class WxPusherNotifier(BaseNotifier):
    name = "wxpusher"
    display_name = "WxPusher 微信推送"

    async def _do_send(self, app_token: str, uids_str: str, title: str, content: str) -> Dict[str, Any]:
        token = (app_token or "").strip()
        if not token:
            return {"ok": False, "channel": self.name, "message": "WxPusher appToken 未配置"}

        raw_uids = (uids_str or "").strip()
        # 兼容逗号、中文逗号、分号、换行等多种粘贴方式，去重且过滤空项
        split_uids = re.split(r"[,，;；\n\r\s]+", raw_uids)
        uids: List[str] = []
        for u in split_uids:
            u = u.strip()
            if u and u not in uids:
                uids.append(u)
        if not uids:
            return {"ok": False, "channel": self.name, "message": "WxPusher 目标用户 UID 未配置（请先获取关注用户并勾选至少一个用户）"}

        url = "https://wxpusher.zjiecode.com/api/send/message"
        payload = {
            "appToken": token,
            "content": content,
            "summary": title[:30],
            "contentType": 3,  # 3 表示 Markdown
            "uids": uids
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    res_data = resp.json()
                    code = res_data.get("code")
                    top_msg = res_data.get("msg") or ""
                    # 保留脱敏后的官方原始响应，便于「测试成功但收不到」时排查
                    data_list = res_data.get("data")
                    logger.info(
                        "[WxPusher] 官方响应 code=%s msg=%s data=%s",
                        code, top_msg, data_list,
                    )
                    if code == 1000:
                        # code=1000 仅代表请求被受理，不代表 UID 真正送达。
                        # 必须逐 UID 校验送达结果；无 data 明细时不能报「成功」。
                        if not isinstance(data_list, list) or not data_list:
                            logger.warning("[WxPusher] 官方未返回任何 UID 送达明细，不判定为成功")
                            return {
                                "ok": False,
                                "channel": self.name,
                                "message": f"WxPusher 接口已受理但未返回送达明细（{top_msg or '无说明'}），无法确认已推送到微信。请确认 UID 属于当前 appToken 对应的应用且已扫码关注该应用公众号",
                                "official_code": code,
                                "official_msg": top_msg,
                            }
                        ok_count = 0
                        failed_msgs: List[str] = []
                        for item in data_list:
                            if not isinstance(item, dict):
                                continue
                            item_code = item.get("code")
                            item_uid = item.get("uid") or ""
                            item_status = item.get("status") or item.get("msg") or f"错误码 {item_code}"
                            if item_code == 1000:
                                ok_count += 1
                            else:
                                failed_msgs.append(f"{item_uid or 'UID'}: {item_status}")
                        if failed_msgs:
                            # 任一 UID 投递失败就视为失败，避免「部分成功」被当成整体成功
                            return {
                                "ok": False,
                                "channel": self.name,
                                "message": f"WxPusher 投递失败（成功 {ok_count} 个，失败: {'; '.join(failed_msgs)}）。请确认 UID 属于当前 appToken 对应的应用且已扫码关注该应用公众号",
                                "official_code": code,
                                "official_msg": top_msg,
                            }
                        if ok_count == 0:
                            return {
                                "ok": False,
                                "channel": self.name,
                                "message": f"WxPusher 未返回有效送达结果（{top_msg or '无说明'}），请检查 UID 是否有效",
                                "official_code": code,
                                "official_msg": top_msg,
                            }
                        return {
                            "ok": True,
                            "channel": self.name,
                            "message": f"WxPusher 已送达 {ok_count} 个 UID（{top_msg or '发送成功'}）",
                            "official_code": code,
                            "official_msg": top_msg,
                        }
                    err_msg = top_msg or str(res_data)
                    return {"ok": False, "channel": self.name, "message": f"WxPusher 返回错误: {err_msg}", "official_code": code, "official_msg": top_msg}
                return {"ok": False, "channel": self.name, "message": f"WxPusher HTTP 状态异常: {resp.status_code}"}
        except Exception as e:
            logger.warning(f"WxPusher 推送异常: {e}")
            return {"ok": False, "channel": self.name, "message": f"WxPusher 通信异常: {str(e)}"}

    async def send(self, data: NotificationData) -> Dict[str, Any]:
        if not db.get_setting("wxpusher_enabled", False):
            return {"ok": False, "channel": self.name, "skipped": True, "message": "WxPusher 通道已关闭"}

        app_token = db.get_setting("wxpusher_app_token", "")
        uids = db.get_setting("wxpusher_uids", "")
        return await self._do_send(app_token, uids, f"【XiaoCan Assistant】 {data.title}", data.format_markdown())

    async def test(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # 表单显式传入的值（包括空值）优先：用户取消勾选后不能回退到已保存的旧 UID，
        # 否则会出现「界面未勾选用户但测试仍发给旧 UID」的误判。
        app_token = (
            config["wxpusher_app_token"]
            if "wxpusher_app_token" in config
            else db.get_setting("wxpusher_app_token", "")
        )
        uids = (
            config["wxpusher_uids"]
            if "wxpusher_uids" in config
            else db.get_setting("wxpusher_uids", "")
        )
        test_title = "【XiaoCan Assistant】 通知连通性测试"
        test_content = (
            "### 【XiaoCan Assistant】 通知连通性测试\n\n"
            "这是一条来自XiaoCan Assistant的连通性测试消息。如果你在微信公众号中收到此卡片，"
            "说明 WxPusher 微信推送通道已成功接入并正常工作。"
        )
        res = await self._do_send(app_token, uids, test_title, test_content)
        # 返回测试消息明细，供日志展示具体标题/正文/目标 UID（appToken 脱敏，不落库）
        clean_uids = [u.strip() for u in re.split(r"[,，;；\n\r\s]+", str(uids or "")) if u.strip()]
        token_str = str(app_token or "").strip()
        token_masked = f"{token_str[:6]}...{token_str[-4:]}" if len(token_str) > 12 else "未配置"
        res.update({
            "test_title": test_title,
            "test_summary": test_title[:30],
            "test_content": test_content,
            "test_uids": clean_uids,
            "test_content_type": "Markdown",
            "app_token_masked": token_masked,
        })
        return res
