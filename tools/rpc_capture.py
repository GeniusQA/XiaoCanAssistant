"""
小蚕 RPC 协议分析抓包工具 (独立于主程序运行)

用途: 电脑微信打开小蚕小程序期间, 透明解密 gw.xiaocantech.com 等
小蚕域名的 HTTPS 流量, 将全部 RPC 请求/响应报文记录到 JSONL,
用于分析凭据签发与续期链路 (如 issue 中提到的 ybb 接口)。

用法:
    python tools/rpc_capture.py [持续秒数, 默认600]

输出: backend/data/rpc_capture.jsonl (每行一个报文事件)
停止: 到时自动停止并还原系统代理; 或手动创建 _stop_capture 文件提前结束;
      或直接结束本进程 (finally 也会还原代理)。
"""
import asyncio
import json
import os
import ssl
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.core.win_proxy import win_proxy  # noqa: E402
from app.core.cert_manager import cert_mgr  # noqa: E402

LISTEN_PORT = 8699
OUT_PATH = os.path.join(ROOT, "backend", "data", "rpc_capture.jsonl")
STOP_FLAG = os.path.join(ROOT, "_stop_capture")
MAX_BODY_LOG = 4000

_lock = asyncio.Lock()
_event_seq = 0


def is_xiaocan_host(host: str) -> bool:
    h = (host or "").lower()
    return "xiaocan" in h or "silk" in h


def log_event(kind: str, host: str, data: dict):
    global _event_seq
    entry = {
        "seq": -1,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind,
        "host": host,
    }
    entry.update(data or {})
    text = json.dumps(entry, ensure_ascii=False)
    print(text[:400], flush=True)


async def append_event(entry: dict):
    global _event_seq
    async with _lock:
        _event_seq += 1
        entry["seq"] = _event_seq
        line = json.dumps(entry, ensure_ascii=False)
        with open(OUT_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(f"[capture] #{entry['seq']} {entry.get('kind')} {entry.get('servername','')}.{entry.get('methodname','')}", flush=True)


async def read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


async def read_http_message(reader: asyncio.StreamReader):
    """读取一条 HTTP 报文: 返回 (headers_bytes, headers_dict_lower, body_bytes) 或 None"""
    raw = bytearray()
    while True:
        line = await reader.readline()
        if not line:
            return None
        raw.extend(line)
        if line in (b"\r\n", b"\n"):
            break
        if len(raw) > 262144:
            break
    head = bytes(raw)
    try:
        head_text = head.decode("utf-8", errors="ignore")
    except Exception:
        head_text = ""
    lines = head_text.splitlines()
    headers = {}
    for ln in lines[1:]:
        if ":" in ln:
            k, _, v = ln.partition(":")
            headers[k.strip().lower()] = v.strip()
    body = b""
    if "content-length" in headers:
        try:
            n = int(headers["content-length"])
            body = await read_exact(reader, n) if n > 0 else b""
        except Exception:
            pass
    elif headers.get("transfer-encoding", "").lower() == "chunked":
        while True:
            size_line = await reader.readline()
            if not size_line:
                break
            try:
                size = int(size_line.strip().split(b";")[0], 16)
            except Exception:
                break
            if size == 0:
                await reader.readline()
                break
            chunk = await read_exact(reader, size)
            body += chunk
            await reader.readexactly(2)
    return head, headers, body


async def pipe_and_log_client(src: asyncio.StreamReader, dst: asyncio.StreamWriter, host: str):
    """客户端 -> 上游: 逐条解析 RPC 请求并记录"""
    while True:
        msg = await read_http_message(src)
        if msg is None:
            break
        head, headers, body = msg
        try:
            dst.write(head)
            if body:
                dst.write(body)
            await dst.drain()
        except Exception:
            return
        if is_xiaocan_host(host):
            first_line = head.decode("utf-8", errors="ignore").splitlines()[0] if head else ""
            entry = {
                "kind": "request",
                "http": first_line,
                "servername": headers.get("servername", ""),
                "methodname": headers.get("methodname", ""),
                "platform": headers.get("x-platform", headers.get("X-Platform", "")),
                "app_sr": headers.get("x-app-sr", ""),
                "has_sivir": bool(headers.get("x-sivir")),
                "sivir_prefix": (headers.get("x-sivir", "") or "")[:20],
                "req_body": body.decode("utf-8", errors="ignore")[:MAX_BODY_LOG],
            }
            await append_event(entry)


async def pipe_and_log_server(src: asyncio.StreamReader, dst: asyncio.StreamWriter, host: str):
    """上游 -> 客户端: 逐条解析响应并记录 (按 HTTP/1.1 顺序与请求配对)"""
    while True:
        msg = await read_http_message(src)
        if msg is None:
            break
        head, headers, body = msg
        try:
            dst.write(head)
            if body:
                dst.write(body)
            await dst.drain()
        except Exception:
            return
        if is_xiaocan_host(host):
            first_line = head.decode("utf-8", errors="ignore").splitlines()[0] if head else ""
            body_text = body.decode("utf-8", errors="ignore")
            code_hint = ""
            try:
                j = json.loads(body_text)
                st = j.get("status") if isinstance(j, dict) else None
                if isinstance(st, dict):
                    code_hint = f"code={st.get('code')} msg={st.get('msg')}"
            except Exception:
                pass
            await append_event({
                "kind": "response",
                "http": first_line,
                "code_hint": code_hint,
                "resp_body": body_text[:MAX_BODY_LOG],
            })


async def mitm(client_reader, client_writer, host, port):
    """小蚕域名: 动态证书解密 + 全量报文记录"""
    remote_reader, remote_writer = await asyncio.open_connection(host, port, ssl=True)
    client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await client_writer.drain()

    cert_pem, key_pem = cert_mgr.get_or_create_host_cert(host)
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as fc:
        fc.write(cert_pem)
        cert_file = fc.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as fk:
        fk.write(key_pem)
        key_file = fk.name
    try:
        ssl_ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    finally:
        os.remove(cert_file)
        os.remove(key_file)

    loop = asyncio.get_running_loop()
    transport = await loop.start_tls(
        client_writer.transport, client_writer._protocol, ssl_ctx, server_side=True
    )
    tls_reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(tls_reader)
    transport.set_protocol(protocol)
    tls_writer = asyncio.StreamWriter(transport, protocol, tls_reader, loop)

    await asyncio.gather(
        pipe_and_log_client(tls_reader, remote_writer, host),
        pipe_and_log_server(remote_reader, tls_writer, host),
        return_exceptions=True,
    )


async def blind_tunnel(client_reader, client_writer, host, port, send_ok=True):
    remote_reader, remote_writer = await asyncio.open_connection(host, port)
    if send_ok:
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()

    async def fwd(r, w):
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                w.write(data)
                await w.drain()
        except Exception:
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass

    await asyncio.gather(
        fwd(client_reader, remote_writer),
        fwd(remote_reader, client_writer),
        return_exceptions=True,
    )


async def handle_client(reader, writer):
    try:
        head = bytearray()
        while True:
            line = await reader.readline()
            if not line:
                return
            head.extend(line)
            if line in (b"\r\n", b"\n"):
                break
            if len(head) > 65536:
                break
        text = head.decode("utf-8", errors="ignore")
        first_line = text.splitlines()[0] if text else ""
        if first_line.startswith("CONNECT "):
            target = first_line.split()[1]
            host, _, port_s = target.partition(":")
            port = int(port_s) if port_s else 443
            use_mitm = is_xiaocan_host(host)
            await append_event({"kind": "tunnel", "host": host, "port": port, "mitm": use_mitm})
            if use_mitm:
                await mitm(reader, writer, host, port)
            else:
                await blind_tunnel(reader, writer, host, port, send_ok=True)
        else:
            # 明文 HTTP: 仅记录小蚕域请求头 (少见)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
    except Exception as e:
        print(f"[warn] connection error: {e}", flush=True)
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main(duration: int):
    if not cert_mgr.is_ca_installed():
        print("[FATAL] 根证书尚未安装到系统信任存储, 小程序会拒绝解密连接。")
        print(f"请先在主程序【账号接入】里完成一次电脑微信无感直连 (会引导安装CA), 或手动安装: {cert_mgr.get_ca_cert_path()}")
        return 2

    server = await asyncio.start_server(handle_client, "127.0.0.1", LISTEN_PORT)
    print(f"[capture] listening on 127.0.0.1:{LISTEN_PORT}, duration={duration}s", flush=True)
    print(f"[capture] output -> {OUT_PATH}", flush=True)

    ok = win_proxy.enable_proxy(host="127.0.0.1", port=LISTEN_PORT)
    print(f"[capture] system proxy takeover: {'OK' if ok else 'FAILED (请手动设置系统代理 127.0.0.1:8699)'}", flush=True)

    try:
        deadline = time.time() + duration
        while time.time() < deadline:
            if os.path.exists(STOP_FLAG):
                print("[capture] stop flag detected", flush=True)
                break
            await asyncio.sleep(1)
    finally:
        try:
            win_proxy.restore_proxy()
            print("[capture] system proxy restored", flush=True)
        except Exception as e:
            print(f"[warn] restore proxy failed: {e}", flush=True)
        server.close()
    print(f"[capture] done, total events: {_event_seq}", flush=True)
    return 0


if __name__ == "__main__":
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    try:
        rc = asyncio.run(main(dur))
    finally:
        try:
            win_proxy.restore_proxy()
        except Exception:
            pass
    sys.exit(rc or 0)
