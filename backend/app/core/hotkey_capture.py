"""
全局热键截屏识别流水线 (Alt+Q):
热键触发 -> 全屏截图 -> 官方 OCR 提取外卖平台单号 -> 未命中则滚动鼠标滚轮翻页再截再识 (滚动多帧 OCR)
-> 命中后写入状态槽, 由前端「下单流程」弹窗轮询回填。

设计要点:
- 热键: ctypes 低级键盘钩子 (WH_KEYBOARD_LL), 零第三方依赖, 仅监听 Alt+Q 不拦截原按键;
- 截屏: PIL ImageGrab (已装), JPEG 压缩后走官方 SilkwormService.OcrPromotionOrder;
- 滚动: mouse_event 滚轮事件作用于**鼠标指针所在窗口**——使用前请把鼠标停在订单详情页上;
- 目标订单: 自动挑选最紧急的「已下单待反馈且未绑单号」订单。
"""
import asyncio
import base64
import ctypes
import io
import logging
import threading
import time
from ctypes import wintypes
from typing import Any, Dict, Optional

from PIL import Image, ImageGrab

from app.models.database import get_account_by_key, get_orders
from app.protocol.client import client, XiaoCanRPCError

logger = logging.getLogger("xiaocan.hotkey_capture")

# Alt+Q (VK_Q=0x51)
_HOTKEY_VK = 0x51
VK_MENU = 0x12
WM_KEYDOWN = 0x0100
WH_KEYBOARD_LL = 13
WHEEL_DOWN = -600   # 每帧向下滚 5 格 (每格 ±120), 确保翻过一屏
WHEEL_UP = 600

_MAX_FRAMES = 6          # 最多识别 6 屏
_FRAME_INTERVAL = 1.0    # 每次滚动后的等待 (页面渲染)

_state_lock = threading.Lock()
_state: Dict[str, Any] = {
    "stage": "idle",       # idle | capturing | found | not_found | error
    "message": "",
    "order_id_str": "",
    "target_order_id": 0,
    "target_store": "",
    "frame": 0,
    "seq": 0,
    "ts": 0.0,
}
_loop: Optional[asyncio.AbstractEventLoop] = None
_pipeline_running = False
_listener_started = False


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _set_state(**kw) -> None:
    with _state_lock:
        _state.update(kw)
        if kw.get("stage") not in (None, "capturing"):
            _state["seq"] = _state.get("seq", 0) + 1
            _state["ts"] = time.time()


def get_state() -> Dict[str, Any]:
    with _state_lock:
        return dict(_state)


# ---------------- 低级键盘钩子 ---------------- #
_LP_KBDLLHOOKSTRUCT = ctypes.POINTER(wintypes.KBDLLHOOKSTRUCT) if hasattr(wintypes, "KBDLLHOOKSTRUCT") else ctypes.c_void_p

if hasattr(wintypes, "KBDLLHOOKSTRUCT"):
    _HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, _LP_KBDLLHOOKSTRUCT)
else:  # 老版本 python 兜底
    _HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, ctypes.c_void_p)


def _low_level_keyboard_proc(nCode, wParam, lParam):
    try:
        if nCode >= 0 and wParam == WM_KEYDOWN:
            struct = ctypes.cast(lParam, _LP_KBDLLHOOKSTRUCT).contents
            if struct.vkCode == _HOTKEY_VK:
                alt_down = ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000
                if alt_down:
                    _schedule_pipeline()
    except Exception:
        pass
    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)


_hook_proc_ref = None  # 防 GC
_hook_handle = None


def start_hotkey_listener() -> None:
    global _listener_started, _hook_proc_ref, _hook_handle
    if _listener_started or not hasattr(wintypes, "KBDLLHOOKSTRUCT"):
        if not hasattr(wintypes, "KBDLLHOOKSTRUCT"):
            logger.warning("当前 Python 版本缺少 KBDLLHOOKSTRUCT 定义, Alt+Q 截屏识别不可用")
        return

    def _thread():
        global _hook_handle
        _hook_proc_ref = _HOOKPROC(_low_level_keyboard_proc)
        _hook_handle = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, _hook_proc_ref, ctypes.windll.kernel32.GetModuleHandleW(None), 0
        )
        if not _hook_handle:
            logger.warning("Alt+Q 全局热键注册失败 (SetWindowsHookExW 返回空)")
            return
        logger.info("Alt+Q 全局截屏识别热键已启用")
        msg = wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

    threading.Thread(target=_thread, name="hotkey-listener", daemon=True).start()
    _listener_started = True


def stop_hotkey_listener() -> None:
    global _hook_handle, _listener_started
    if _hook_handle:
        ctypes.windll.user32.UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None
    _listener_started = False


def _schedule_pipeline() -> None:
    global _pipeline_running
    if _pipeline_running:
        _set_state(stage="capturing", message="上一轮识别仍在进行中，已忽略本次热键")
        return
    if _loop is None:
        logger.warning("热键触发但事件循环未就绪")
        return
    try:
        asyncio.run_coroutine_threadsafe(_run_pipeline(), _loop)
    except Exception as e:
        logger.warning(f"热键识别任务调度失败: {e}")


async def trigger_from_async() -> None:
    """前端手动触发入口 (与热键等效)"""
    _schedule_pipeline()


# ---------------- 截屏与滚动 ---------------- #
def _grab_frame_jpeg_b64() -> str:
    img = ImageGrab.grab()
    if img.width > 1280:
        ratio = 1280 / img.width
        img = img.resize((1280, max(1, int(img.height * ratio))))
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _scroll_wheel(delta: int) -> None:
    """滚轮事件作用于鼠标指针所在的窗口: delta<0 向下翻页, >0 向上回滚"""
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta, 0)


# ---------------- 单号提取 ---------------- #
def _extract_platform_order_id(res: Any) -> str:
    """从官方 OCR 响应递归提取最长的纯数字串 (美团单号通常 15~19 位)"""
    found = []

    def _walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
        elif isinstance(obj, str):
            s = obj.strip()
            if s.isdigit() and 10 <= len(s) <= 25:
                found.append(s)

    _walk(res)
    return max(found, key=len) if found else ""


# ---------------- 识别流水线 ---------------- #
def _pick_pending_order() -> Optional[Dict[str, Any]]:
    """挑选最紧急的「已下单待反馈且未绑单号」订单 (未超时优先)"""
    now = int(time.time())
    rows = get_orders(status="pending") or []
    candidates = [r for r in rows if not r.get("platform_order_id")]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (0 if (r.get("timeout_time") or 0) > now else 1, r.get("timeout_time") or 0))
    return candidates[0]


async def _run_pipeline() -> None:
    global _pipeline_running
    if _pipeline_running:
        return
    _pipeline_running = True
    scrolled_total = 0
    try:
        order = _pick_pending_order()
        if not order:
            _set_state(stage="not_found", message="当前没有「待提交单号」的订单，无需截屏识别")
            return
        acc = get_account_by_key(order.get("account_key"))
        if not acc or not acc.get("token"):
            _set_state(stage="error", message="该订单对应的小蚕账号凭据已失效，无法识别")
            return

        _set_state(stage="capturing", message="正在截屏识别...", frame=0)
        found_id = ""
        for frame in range(_MAX_FRAMES):
            _set_state(stage="capturing", message=f"第 {frame + 1}/{_MAX_FRAMES} 屏识别中...", frame=frame + 1)
            b64 = await asyncio.to_thread(_grab_frame_jpeg_b64)
            try:
                res = await client.ocr_promotion_order(
                    image_base64=b64,
                    token=acc["token"],
                    silk_id=acc.get("silk_id"),
                    user_id=acc.get("user_id"),
                    city_code=acc.get("city_code") or 440303,
                )
            except XiaoCanRPCError as e:
                _set_state(stage="error", message=f"官方 OCR 接口失败: {e.msg} (错误码: {e.code})")
                return
            oid = _extract_platform_order_id(res)
            if oid:
                found_id = oid
                break
            if frame < _MAX_FRAMES - 1:
                _scroll_wheel(WHEEL_DOWN)
                scrolled_total += 1
                await asyncio.sleep(_FRAME_INTERVAL)

        if found_id:
            _set_state(
                stage="found",
                order_id_str=found_id,
                target_order_id=order.get("id"),
                target_store=order.get("store_name") or "",
                message=f"识别成功: {found_id}",
            )
            logger.info(f"[Alt+Q截屏识别] 订单#{order.get('id')} {order.get('store_name')} 识别到单号 {found_id}")
        else:
            _set_state(stage="not_found", message=f"滚动 {_MAX_FRAMES} 屏仍未识别到单号，请手动输入或 Ctrl+V 粘贴截图")
        # 回滚到页顶, 恢复用户浏览位置
        for _ in range(scrolled_total):
            _scroll_wheel(WHEEL_UP)
    except Exception as e:
        logger.exception("[Alt+Q截屏识别] 异常")
        _set_state(stage="error", message=f"截屏识别异常: {e}")
    finally:
        _pipeline_running = False
