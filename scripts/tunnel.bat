@echo off
chcp 65001 >nul
title 小蚕助理 - 公网隧道 (Cloudflare Tunnel)
setlocal

rem ============================================================
rem  用途: 让不在同一局域网的手机 (移动数据 / 其他 WiFi)
rem        也能访问 PC 上的小蚕助手 (自动获得公网 HTTPS 地址)
rem  前提: 先正常启动 run.bat (8690 服务运行中)
rem  首次使用: 需下载 cloudflared.exe 放到 scripts 目录
rem    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
rem ============================================================

set "CLOUDFLARED=%~dp0cloudflared.exe"

if not exist "%CLOUDFLARED%" (
    where cloudflared >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   [提示] 未找到 cloudflared.exe
        echo.
        echo   请下载后放到本目录并重命名为 cloudflared.exe:
        echo   https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
        echo.
        pause
        exit /b 1
    )
    set "CLOUDFLARED=cloudflared"
)

echo.
echo   ============================================================
echo    正在建立公网 HTTPS 隧道, 请稍候 (首次约 5-15 秒)...
echo    建立成功后会输出 https://xxxx.trycloudflare.com 地址
echo    用手机浏览器打开该地址即可 (任意网络, 无需同一 WiFi)
echo.
echo    注意: 保持本窗口开启, 关闭窗口会立即断开公网访问
echo          公网地址仅本机运行期间有效, 每次重启会变化
echo   ============================================================
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:8690

echo.
echo   隧道已关闭
pause
