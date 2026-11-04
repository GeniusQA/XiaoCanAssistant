"""wxapkg v1 格式解包工具"""
import os
import struct
import sys


def unpack(wxapkg_path: str, out_dir: str):
    data = open(wxapkg_path, "rb").read()
    if data[0] != 0xBE:
        # PC 微信加密包头 V1MMWX 等, 需先解密
        raise SystemExit(f"非标准 wxapkg (首字节 0x{data[0]:02X}), 可能是加密包, 请从安卓 root 真机提取")

    index_len = struct.unpack(">I", data[5:9])[0]
    body_len = struct.unpack(">I", data[9:13])[0]
    last = data[13]
    if last != 0xED:
        raise SystemExit("尾部标记不匹配, 格式可能已变化")

    pos = 14
    file_count = struct.unpack(">I", data[pos:pos + 4])[0]
    pos += 4
    files = []
    for _ in range(file_count):
        name_len = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        name = data[pos:pos + name_len].decode("utf-8")
        pos += name_len
        offset = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        files.append((name, offset, size))

    os.makedirs(out_dir, exist_ok=True)
    for name, offset, size in files:
        content = data[offset:offset + size]
        rel = name.lstrip("/")
        out_path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(content)
    print(f"解包完成: {file_count} 个文件 -> {out_dir}")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "xc_mini.wxapkg")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "xc_unpacked")
    unpack(src, dst)
