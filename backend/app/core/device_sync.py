"""设备协同辅助工具：局域网地址、二维码与终端类型识别。"""
import base64
import hashlib
import io
import re
import socket
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Dict, Optional

import qrcode


MOBILE_UA_RE = re.compile(
    r"(iphone|ipad|ipod|android|windows phone|blackberry|mobile|silk|kindle)",
    re.IGNORECASE,
)


def get_lan_ip() -> str:
    """获取本机局域网 IP：优先 UDP 探测，失败后回退主机名解析。"""
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        try:
            s.connect(("223.5.5.5", 80))
            ip = s.getsockname()[0] or ip
        finally:
            s.close()
    except Exception:
        pass
    if ip == "127.0.0.1":
        try:
            resolved = socket.gethostbyname_ex(socket.gethostname())[2]
            candidates = [x for x in resolved if not x.startswith("127.") and "%" not in x]
            if candidates:
                ip = candidates[0]
        except Exception:
            pass
    return ip


def build_lan_url(host_header: str = "", path: str = "/m/bind") -> str:
    """优先使用访问时的 Host；本地访问保留端口，仅把地址替换成局域网 IP。"""
    host = (host_header or "").strip()
    scheme = "http"
    if host.lower().startswith("https://"):
        scheme = "https"
        host = host[8:]
    elif host.lower().startswith("http://"):
        host = host[7:]
    host = host.split("/", 1)[0].strip()
    if not host:
        return f"http://{get_lan_ip()}:8690{path}"

    hostname, port = host, ""
    if ":" in host:
        hostname, port = host.rsplit(":", 1)
    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        hostname = get_lan_ip()
    clean_host = hostname if not port else f"{hostname}:{port}"
    return f"{scheme}://{clean_host}{path}"


def qr_data_url(text: str) -> str:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def is_mobile_user_agent(user_agent: str = "") -> bool:
    return bool(MOBILE_UA_RE.search(user_agent or ""))


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def client_ip_from_headers(forwarded_for: Optional[str] = None, real_ip: Optional[str] = None) -> str:
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return (real_ip or "").strip()
