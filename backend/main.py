"""
小蚕助理 (XiaoCan Assistant)
基于 FastAPI + APScheduler + 逆向 RPC 协议驱动
"""
import os
import sys

# 排除宿主机或外部代理工具注入的 SOCKS 代理环境变量污染，保证本地服务与国内接口纯净直连
for proxy_k in ["ALL_PROXY", "all_proxy"]:
    if proxy_k in os.environ and "socks" in os.environ[proxy_k].lower():
        os.environ.pop(proxy_k, None)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router as api_router
from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.models.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("xiaocan.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在启动小蚕助手系统...")
    init_db()
    # 全局 RPS 限速 (设置项 global_rps_limit, 默认 8 次/秒; 设为 0 表示不限速)
    try:
        from app.models.database import get_setting
        from app.protocol.rate_limiter import set_global_rate
        _rps = get_setting("global_rps_limit", None)
        if _rps is not None:
            set_global_rate(float(_rps))
        logger.info(f"全局请求限速已启用: {get_setting('global_rps_limit', 8)} 次/秒")
    except Exception as _rate_err:
        logger.warning(f"全局限速初始化提示: {_rate_err}")
    start_scheduler()
    try:
        from app.meituan.runner import ensure_meituan_assets
        ensure_meituan_assets()
    except Exception as e:
        logger.warning(f"美团运行环境自愈检查提示: {e}")
    # Alt+Q 全局热键截屏识别 (滚动多帧 OCR, 服务「下单流程」弹窗自动回填单号)
    try:
        import asyncio
        from app.core.hotkey_capture import set_event_loop, start_hotkey_listener, stop_hotkey_listener
        set_event_loop(asyncio.get_running_loop())
        start_hotkey_listener()
    except Exception as e:
        logger.warning(f"Alt+Q 截屏识别热键启用失败: {e}")
    yield
    logger.info("正在关闭小蚕助手系统...")
    try:
        from app.core.hotkey_capture import stop_hotkey_listener
        stop_hotkey_listener()
    except Exception:
        pass
    shutdown_scheduler()


app = FastAPI(
    title="小蚕助理",
    description="自动化挂机、秒杀与抢单小帮手",
    version="1.0.1",
    lifespan=lifespan
)

# 允许跨域请求 (支持前端 Vite 开发服务器 http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由
app.include_router(api_router)

APP_PORT = 8690

# ---------------- 多端设备协同鉴权 ----------------
# 本机 (localhost) 直连信任免认证; 非本机来源访问 /api/** 需携带配对换发的设备 JWT
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.device_auth import verify_device_token, mark_device_seen

_TRUSTED_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}

@app.middleware("http")
async def device_auth_middleware(request: Request, call_next):
    path = request.url.path
    client_host = request.client.host if request.client else ""
    # 1) 非 API 路径 (前端页面/静态资源/健康检查) 与本机来源: 直接放行
    if not path.startswith("/api") or client_host in _TRUSTED_HOSTS:
        return await call_next(request)
    # 2) 配对端点免认证 (移动端换取 JWT 的唯一入口)
    if path.startswith("/api/pairing/redeem") or path.startswith("/api/pairing/create"):
        return await call_next(request)
    # 3) 其余 /api/** 要求设备 JWT
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    payload = verify_device_token(token.strip())
    if not payload:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "detail": "设备未配对或凭证已失效，请在 PC 端生成配对码重新登录"}
        )
    mark_device_seen(payload, client_host)
    request.state.device_id = payload.get("device_id")
    return await call_next(request)


from fastapi.responses import RedirectResponse

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "xiaocan-assistant", "version": "2.0.0", "license": "free"}


@app.get("/m/bind")
async def root_m_bind(ticket: str = ""):
    return RedirectResponse(f"/api/m/bind?ticket={ticket}")


# 若前端已打包 (frontend/dist)，则支持前后端合并一键部署
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # run.bat 设置 XIAOCAN_RELOAD=0 以生产模式运行；dev.bat 设置为 1 启用代码热重载
    # XIAOCAN_PORT 可自定义服务端口 (默认 8690)
    reload_enabled = os.environ.get("XIAOCAN_RELOAD", "1") != "0"
    app_port = int(os.environ.get("XIAOCAN_PORT", "8690"))
    logger.info(f"启动本地 Web 服务: http://0.0.0.0:{app_port} (热重载: {'开启' if reload_enabled else '关闭'})")
    uvicorn.run("main:app", host="0.0.0.0", port=app_port, reload=reload_enabled)
