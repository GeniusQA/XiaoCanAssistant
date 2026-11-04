# -*- coding: utf-8 -*-
"""高德 / 百度 Web 服务地图源: POI 关键词检索 + 国标坐标转换 (GCJ-02 / BD-09 -> WGS84)

候选结构与 tianditu.search_poi_photon 完全对齐 (source='amap' / 'baidu'),
坐标统一转 WGS84 后返回, 与项目底图/存储坐标系一致。
"""
import math
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"
BAIDU_SEARCH_URL = "https://api.map.baidu.com/place/v2/search"
AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
BAIDU_REGEO_URL = "https://api.map.baidu.com/reverse_geocoding/v3/"

_DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) XiaoCanAssistant/1.0"

# ---------------- 坐标转换 (国标算法, GCJ02->WGS84 反向近似, 误差 <1m) ----------------

_PI = math.pi
_X_PI = math.pi * 3000.0 / 180.0
_A = 6378245.0  # 长半轴
_EE = 0.00669342162296594323  # 偏心率平方


def _out_of_china(lng: float, lat: float) -> bool:
    return not (73.0 < lng < 136.0 and 3.0 < lat < 54.0)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320.0 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng: float, lat: float) -> tuple:
    """GCJ-02 (火星坐标系, 高德) -> WGS-84"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * _PI)
    return lng - dlng, lat - dlat


def wgs84_to_gcj02(lng: float, lat: float) -> tuple:
    """WGS-84 -> GCJ-02 (正向纠偏, 供高德逆地理请求参数使用)"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * _PI)
    return lng + dlng, lat + dlat


def bd09_to_gcj02(lng: float, lat: float) -> tuple:
    """BD-09 (百度坐标系) -> GCJ-02"""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def bd09_to_wgs84(lng: float, lat: float) -> tuple:
    gLng, gLat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(gLng, gLat)


def _s(v: Any) -> str:
    """百度部分字段在直辖市场景返回数组, 统一取首个字符串"""
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "").strip()


def _build_candidate(name: str, district: str, city: str, province: str,
                     address: str, wlng: float, wlat: float, source: str) -> Dict[str, Any]:
    city_name = city.replace("市", "").strip() or "未知"
    return {
        "city_code": 0,  # 由端点层用 CITY_CODE_MAP 统一兜底
        "city_name": city_name,
        "province": province,
        "district_name": district,
        "town_name": "",
        "poi": name,
        # 地址名称 = POI 原始名称 (不拼区名前缀, 区县信息由具体地址承载)
        "short_name": name,
        "full_address": ", ".join(x for x in (name, address, district, city + "市" if city and not city.endswith("市") else city, province, "中国") if x),
        "latitude": f"{wlat:.6f}",
        "longitude": f"{wlng:.6f}",
        "source": source,
    }


# ---------------- 高德 Web 服务 ----------------

async def search_poi_amap(keyword: str, key: str, count: int = 8) -> List[Dict[str, Any]]:
    """高德 place/text 关键词检索 (GCJ-02 结果自动转 WGS84), source='amap'"""
    clean_kw = (keyword or "").strip()
    key = (key or "").strip()
    if not clean_kw or not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            resp = await client.get(
                AMAP_SEARCH_URL,
                params={"key": key, "keywords": clean_kw, "offset": count, "page": 1, "extensions": "base"},
                headers={"User-Agent": _DESKTOP_UA},
            )
            data = resp.json()
    except Exception as e:
        logger.info(f"高德 POI 检索失败(静默降级, 尝试下一地图源): {e}")
        return []
    if str(data.get("status")) != "1":
        logger.info(f"高德 POI 检索未成功: status={data.get('status')} infocode={data.get('infocode')} info={data.get('info')}")
        return []
    out: List[Dict[str, Any]] = []
    for p in (data.get("pois") or []):
        try:
            glng_s, glat_s = str(p.get("location") or "").split(",")[:2]
            glng, glat = float(glng_s), float(glat_s)
        except Exception:
            continue
        wlng, wlat = gcj02_to_wgs84(glng, glat)
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        city = str(p.get("cityname") or "").strip() or str(p.get("pname") or "").strip()
        out.append(_build_candidate(
            name=name,
            district=str(p.get("adname") or "").strip(),
            city=city,
            province=str(p.get("pname") or "").strip(),
            address=str(p.get("address") or "").strip(),
            wlng=wlng, wlat=wlat, source="amap",
        ))
    logger.info(f"高德 POI 检索 '{clean_kw}': {len(out)} 条候选")
    return out


# ---------------- 百度 Web 服务 ----------------

async def search_poi_baidu(keyword: str, key: str, count: int = 8) -> List[Dict[str, Any]]:
    """百度 place/v2/search 关键词检索 (BD-09 结果自动转 WGS84), source='baidu'"""
    clean_kw = (keyword or "").strip()
    key = (key or "").strip()
    if not clean_kw or not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            resp = await client.get(
                BAIDU_SEARCH_URL,
                params={"query": clean_kw, "region": "全国", "output": "json", "ak": key,
                        "page_size": count, "page_num": 0, "scope": "1"},
                headers={"User-Agent": _DESKTOP_UA},
            )
            data = resp.json()
    except Exception as e:
        logger.info(f"百度 POI 检索失败(静默降级, 尝试下一地图源): {e}")
        return []
    if int(data.get("status", -1)) != 0:
        logger.info(f"百度 POI 检索未成功: status={data.get('status')} message={data.get('message')}")
        return []
    out: List[Dict[str, Any]] = []
    for p in (data.get("results") or []):
        loc = p.get("location") or {}
        try:
            blng, blat = float(loc.get("lng")), float(loc.get("lat"))
        except Exception:
            continue
        wlng, wlat = bd09_to_wgs84(blng, blat)
        name = _s(p.get("name"))
        if not name:
            continue
        city = _s(p.get("city")) or _s(p.get("province"))
        out.append(_build_candidate(
            name=name,
            district=_s(p.get("area")),
            city=city,
            province=_s(p.get("province")),
            address=_s(p.get("address")),
            wlng=wlng, wlat=wlat, source="baidu",
        ))
    logger.info(f"百度 POI 检索 '{clean_kw}': {len(out)} 条候选")
    return out


# ---------------- 逆地理编码 (坐标 -> 地址, 供「获取本机定位」链路) ----------------

async def reverse_amap(lng: float, lat: float, key: str) -> Optional[Dict[str, Any]]:
    """高德逆地理 (regeo): WGS84 自动纠偏为 GCJ02 请求, 行政区与 formatted_address 输出"""
    key = (key or "").strip()
    if not key:
        return None
    try:
        gLng, gLat = wgs84_to_gcj02(lng, lat)
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            resp = await client.get(
                AMAP_REGEO_URL,
                params={"location": f"{gLng:.6f},{gLat:.6f}", "key": key,
                        "extensions": "base", "output": "json"},
                headers={"User-Agent": _DESKTOP_UA},
            )
            data = resp.json()
    except Exception as e:
        logger.info(f"高德逆地理失败(尝试下一地图源): {e}")
        return None
    if str(data.get("status")) != "1":
        logger.info(f"高德逆地理未成功: info={data.get('info')}")
        return None
    regeocode = data.get("regeocode") or {}
    comp = regeocode.get("addressComponent") or {}
    prov = _s(comp.get("province"))
    city = _s(comp.get("city")) or prov  # 直辖市 city 为空数组 -> 回退省
    district = _s(comp.get("district"))
    formatted = _s(regeocode.get("formatted_address"))
    if not formatted and not city:
        return None
    return {
        "city_name": city.replace("市", "").strip() or "未知",
        "province": prov,
        "district": district,
        "address_name": formatted or f"{city} · {district}",
        "source": "amap",
    }


async def reverse_baidu(lng: float, lat: float, key: str) -> Optional[Dict[str, Any]]:
    """百度逆地理 (v3): coordtype=wgs84ll 直接接收 WGS84, 无需纠偏"""
    key = (key or "").strip()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            resp = await client.get(
                BAIDU_REGEO_URL,
                params={"ak": key, "output": "json", "coordtype": "wgs84ll",
                        "location": f"{lat:.6f},{lng:.6f}"},
                headers={"User-Agent": _DESKTOP_UA},
            )
            data = resp.json()
    except Exception as e:
        logger.info(f"百度逆地理失败(尝试下一地图源): {e}")
        return None
    if int(data.get("status", -1)) != 0:
        logger.info(f"百度逆地理未成功: status={data.get('status')} message={data.get('message')}")
        return None
    res = data.get("result") or {}
    comp = res.get("addressComponent") or {}
    prov = _s(comp.get("province"))
    city = _s(comp.get("city")) or prov
    district = _s(comp.get("district"))
    formatted = _s(res.get("formatted_address"))
    if not formatted and not city:
        return None
    return {
        "city_name": city.replace("市", "").strip() or "未知",
        "province": prov,
        "district": district,
        "address_name": formatted or f"{city} · {district}",
        "source": "baidu",
    }


# ---------------- 连通性测试 ----------------

async def test_amap(key: str) -> Dict[str, Any]:
    import time as _time
    t0 = _time.time()
    try:
        res = await search_poi_amap("成都", key)
        ms = int((_time.time() - t0) * 1000)
        if res:
            return {"ok": True, "count": len(res), "latency_ms": ms,
                    "message": f"高德 Web 服务连通正常，耗时 {ms}ms，返回 {len(res)} 条候选"}
        return {"ok": False, "message": "高德 API 可达但未返回候选: 请确认 Key 为「Web 服务」类型且已绑定 (infocode 10009=Key无效, 10044=无权限)"}
    except Exception as e:
        return {"ok": False, "message": f"高德连接失败: {e}"}


async def test_baidu(key: str) -> Dict[str, Any]:
    """测试百度 Web 服务 AK 连通性: 直接请求并透出官方真实 status/message, 给出对症修复指引"""
    import time as _time
    t0 = _time.time()
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            resp = await client.get(
                BAIDU_SEARCH_URL,
                params={"query": "成都", "region": "全国", "output": "json", "ak": key,
                        "page_size": 8, "page_num": 0, "scope": "1"},
                headers={"User-Agent": _DESKTOP_UA},
            )
            data = resp.json()
        ms = int((_time.time() - t0) * 1000)
        status = int(data.get("status", -1))
        msg = str(data.get("message") or "")
        if status == 0 and data.get("results"):
            return {"ok": True, "count": len(data["results"]), "latency_ms": ms,
                    "message": f"百度 Web 服务连通正常，耗时 {ms}ms，返回 {len(data['results'])} 条候选"}
        hint = {
            2: "参数无效 — 常见: 创建应用时「启用服务」未勾选「检索服务」(地点检索), 或请求被校验方式拦截",
            200: "AK 不存在 — 检查是否复制完整 32 位 / 应用被删除或审核未通过",
            210: "IP 校验失败 — 当前 IP 白名单不含本机的公网出口 IP (127.0.0.1 是本机回环地址, 百度看不到它; 调试期可临时填 0.0.0.0/0)",
            240: "AK 被禁用或审核中 — 前往百度控制台确认应用状态",
            1: "服务响应无效 — 稍后重试",
        }.get(status, "请确认 AK 为「服务端」类型、已启用且勾选「检索服务」")
        return {"ok": False, "message": f"百度接口返回 status={status} ({msg}) — {hint}"}
    except Exception as e:
        return {"ok": False, "message": f"百度连接失败: {e}"}
