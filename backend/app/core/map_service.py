"""
多地图源地理服务路由 (高德 > 百度 > 天地图)
统一对外提供逆地理编码、关键词 POI 检索与连通性测试，所有返回结果携带 source/source_name 供前端标注来源。
严禁使用 Emoji 字符。
"""
import asyncio
import json
import logging
import math
from typing import Dict, Any, List, Optional, Tuple

import httpx

try:
    from ..models import database as db
    from .tianditu import (
        tianditu_client,
        CITY_CODE_MAP,
        infer_city_from_coords,
        extract_city_code_from_admin,
        DESKTOP_UA,
    )
except ImportError:
    from app.models import database as db
    from app.core.tianditu import (
        tianditu_client,
        CITY_CODE_MAP,
        infer_city_from_coords,
        extract_city_code_from_admin,
        DESKTOP_UA,
    )

logger = logging.getLogger("map_service")

SOURCE_NAMES = {
    "amap": "高德地图",
    "baidu": "百度地图",
    "tianditu": "天地图",
    "preset": "预设城市",
    "fallback": "备用服务",
    "ip": "IP 定位",
}

MAP_SOURCE_REQUIRED_MESSAGE = "请前往系统与通知—位置与地理服务配置地图源参数"

AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
AMAP_PLACE_URL = "https://restapi.amap.com/v3/place/text"
BAIDU_REVERSE_URL = "https://api.map.baidu.com/reverse_geocoding/v3/"
BAIDU_PLACE_URL = "https://api.map.baidu.com/place/v2/search"


# ---------------- WGS84 / GCJ-02 / BD-09 坐标转换 ---------------- #

def _out_of_china(lon: float, lat: float) -> bool:
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(lon: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(lon: float, lat: float) -> float:
    ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    """浏览器定位 WGS84 -> 高德/腾讯使用的 GCJ-02"""
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6335552.717000426 / (magic * sqrtmagic)) * math.pi)
    dlon = (dlon * 180.0) / ((6378245.0 / sqrtmagic) * math.cos(radlat) * math.pi)
    return round(lon + dlon, 6), round(lat + dlat, 6)


def gcj02_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """GCJ-02 -> 百度 BD-09"""
    x, y = lon, lat
    z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) + 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return round(z * math.cos(theta) + 0.0065, 6), round(z * math.sin(theta) + 0.006, 6)


def wgs84_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """浏览器定位 WGS84 -> 百度 BD-09"""
    return gcj02_to_bd09(*wgs84_to_gcj02(lon, lat))


def bd09_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    """百度 BD-09 坐标还原为 WGS84，保证展示与存储的经纬度统一"""
    x, y = lon - 0.0065, lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    g_lon, g_lat = z * math.cos(theta), z * math.sin(theta)
    return _gcj02_to_wgs84(g_lon, g_lat)


def _gcj02_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6335552.717000426 / (magic * sqrtmagic)) * math.pi)
    dlon = (dlon * 180.0) / ((6378245.0 / sqrtmagic) * math.cos(radlat) * math.pi)
    return round(lon - dlon, 6), round(lat - dlat, 6)


def _city_code(adcode: Any, city_name: str = "") -> int:
    """从 adcode 或城市名推导 6 位市级编码"""
    raw = str(adcode or "").strip()
    if raw.isdigit() and len(raw) >= 6:
        code = int(raw[:6])
        if code > 0:
            return (code // 100) * 100
    return extract_city_code_from_admin(raw, city_name) or CITY_CODE_MAP.get(city_name, 0) or CITY_CODE_MAP.get(f"{city_name}市", 0)


def _clean_city(raw: str) -> str:
    return str(raw or "").replace("市", "").strip()


def infer_city_from_keyword(keyword: str, current_city: str = "") -> str:
    """
    从搜索词或当前定位城市推断用于 POI 检索的城市。
    高德 place/text 与百度 place/search 对「天府」这类泛词在无 city 时会返回空结果或城市建议列表，
    必须带 city 才能拿到具体 POI。优先取关键词里显式出现的城市，否则用当前定位城市。
    """
    text = str(keyword or "").strip()
    for name in CITY_CODE_MAP:
        base = name.replace("市", "")
        if base and (base in text or name in text):
            return base
    return _clean_city(current_city)


# ---------------- 配置读取 ---------------- #

def get_provider_settings() -> Dict[str, Any]:
    def as_bool(key: str, default: bool) -> bool:
        val = db.get_setting(key, default)
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    return {
        "amap_enabled": as_bool("amap_enabled", True),
        "amap_key": str(db.get_setting("amap_key", "") or "").strip(),
        "baidu_enabled": as_bool("baidu_enabled", False),
        "baidu_key": str(db.get_setting("baidu_key", "") or "").strip(),
        "tianditu_enabled": as_bool("tianditu_enabled", True),
        "tianditu_key": str(db.get_setting("tianditu_key", "") or "").strip(),
    }


def enabled_providers(settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """严格按 高德 > 百度 > 天地图 的顺序返回已开启且配置了密钥的地图源"""
    cfg = settings or get_provider_settings()
    order: List[str] = []
    if cfg.get("amap_enabled") and cfg.get("amap_key"):
        order.append("amap")
    if cfg.get("baidu_enabled") and cfg.get("baidu_key"):
        order.append("baidu")
    if cfg.get("tianditu_enabled") and (cfg.get("tianditu_key") or "109fd484f999e3c0472ab15fa38fe2ac"):
        order.append("tianditu")
    return order


def no_source_response() -> Dict[str, Any]:
    """所有地图源均未开启时的统一错误响应，供前端跳转配置页面"""
    return {
        "ok": False,
        "no_map_source": True,
        "message": MAP_SOURCE_REQUIRED_MESSAGE,
    }


def _tagged(result: Dict[str, Any], source: str) -> Dict[str, Any]:
    result["source"] = source
    result["source_name"] = SOURCE_NAMES.get(source, source)
    return result


# ---------------- 高德地图 ---------------- #

async def _amap_reverse(lat: float, lon: float, key: str) -> Optional[Dict[str, Any]]:
    g_lon, g_lat = wgs84_to_gcj02(lon, lat)
    try:
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            resp = await client.get(AMAP_REGEO_URL, params={
                "key": key,
                "location": f"{g_lon},{g_lat}",
                "extensions": "all",
            }, headers={"User-Agent": DESKTOP_UA})
            data = resp.json()
        if str(data.get("status", "")) != "1":
            logger.warning(f"高德逆地理编码返回失败: {data.get('info')}")
            return None
        regeo = data.get("regeocode") or {}
        comp = regeo.get("addressComponent") or {}
        province = _clean_city(comp.get("province"))
        city = _clean_city(comp.get("city")) or province
        district = str(comp.get("district") or "").strip()
        town = str(comp.get("township") or "").strip()
        formatted = str(regeo.get("formatted_address") or "").strip()
        code = _city_code(comp.get("adcode"), city)
        if not code:
            near = infer_city_from_coords(lat, lon)
            code = near[0] if near else 0
        addr = formatted or f"{city} · {district}" if (city or district) else "高德定位点"
        return {
            "city_code": code,
            "city_name": city or "未知",
            "locality": town or district,
            "province": province,
            "address_name": addr,
            "latitude": f"{lat:.6f}",
            "longitude": f"{lon:.6f}",
            "accuracy": "high",
        }
    except Exception as e:
        logger.warning(f"高德逆地理编码异常: {e}")
        return None


async def _amap_search(keyword: str, key: str, count: int, city: str = "") -> List[Dict[str, Any]]:
    city_hint = _clean_city(city)
    try:
        params: Dict[str, Any] = {
            "key": key,
            "keywords": keyword,
            "offset": min(max(count, 1), 25),
            "page": 1,
            "extensions": "base",
        }
        if city:
            params["city"] = city
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            resp = await client.get(AMAP_PLACE_URL, params=params, headers={"User-Agent": DESKTOP_UA})
            data = resp.json()
        if str(data.get("status", "")) != "1":
            logger.warning(f"高德 POI 检索返回失败: {data.get('info')}")
            return []
        pois = data.get("pois") or []
        result: List[Dict[str, Any]] = []
        for poi in pois[:count]:
            loc = str(poi.get("location") or "").split(",")
            if len(loc) != 2:
                continue
            try:
                g_lon, g_lat = float(loc[0]), float(loc[1])
            except ValueError:
                continue
            lon, lat = _gcj02_to_wgs84(g_lon, g_lat)
            city = _clean_city(poi.get("cityname")) or _clean_city(city_hint)
            district = str(poi.get("adname") or "").strip()
            province = _clean_city(poi.get("pname") or poi.get("provincename")) or city
            code = _city_code(poi.get("adcode"), city)
            if not code:
                near = infer_city_from_coords(lat, lon)
                code = near[0] if near else 0
            name = str(poi.get("name") or keyword).strip()
            raw_addr = str(poi.get("address") or "").strip()
            full = raw_addr or f"{province}{city}{district}{name}"
            result.append({
                "city_code": code,
                "city_name": city or "未知",
                "province": province,
                "district_name": district,
                "town_name": "",
                "poi": name,
                "short_name": name,
                "full_address": full,
                "latitude": f"{lat:.6f}",
                "longitude": f"{lon:.6f}",
            })
        return result
    except Exception as e:
        logger.warning(f"高德 POI 检索异常: {e}")
        return []


async def _amap_test(key: str) -> Dict[str, Any]:
    res = await _amap_reverse(30.593099, 114.305393, key)
    if res:
        return {"ok": True, "message": f"高德地图 API 鉴权连通成功：{res['city_name']} · {res['address_name']}"}
    return {"ok": False, "message": "高德地图 API 鉴权失败或配额不足，请检查 Key 与已启用服务"}


# ---------------- 百度地图 ---------------- #

async def _baidu_reverse(lat: float, lon: float, key: str) -> Optional[Dict[str, Any]]:
    b_lon, b_lat = wgs84_to_bd09(lon, lat)
    try:
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            resp = await client.get(BAIDU_REVERSE_URL, params={
                "ak": key,
                "location": f"{b_lat},{b_lon}",
                "output": "json",
            }, headers={"User-Agent": DESKTOP_UA})
            data = resp.json()
        if int(data.get("status", -1)) != 0:
            logger.warning(f"百度逆地理编码返回失败: {data.get('message')}")
            return None
        result = data.get("result") or {}
        comp = result.get("addressComponent") or {}
        province = _clean_city(comp.get("province"))
        city = _clean_city(comp.get("city")) or province
        district = str(comp.get("district") or "").strip()
        town = str(comp.get("town") or "").strip()
        formatted = str(result.get("formatted_address") or "").strip()
        code = _city_code(comp.get("adcode"), city)
        if not code:
            near = infer_city_from_coords(lat, lon)
            code = near[0] if near else 0
        addr = formatted or f"{city} · {district}" if (city or district) else "百度定位点"
        return {
            "city_code": code,
            "city_name": city or "未知",
            "locality": town or district,
            "province": province,
            "address_name": addr,
            "latitude": f"{lat:.6f}",
            "longitude": f"{lon:.6f}",
            "accuracy": "high",
        }
    except Exception as e:
        logger.warning(f"百度逆地理编码异常: {e}")
        return None


async def _baidu_search(keyword: str, key: str, count: int, city: str = "") -> List[Dict[str, Any]]:
    try:
        params: Dict[str, Any] = {
            "ak": key,
            "query": keyword,
            "output": "json",
            "page_size": min(max(count, 1), 20),
            "page_num": 0,
            "scope": 1,
        }
        # 百度 Place API v2 必须带 region，否则报 Parameter Invalid；无城市提示时用「全国」
        params["region"] = city or "全国"
        async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
            resp = await client.get(BAIDU_PLACE_URL, params=params, headers={"User-Agent": DESKTOP_UA})
            data = resp.json()
        if int(data.get("status", -1)) != 0:
            logger.warning(f"百度 POI 检索返回失败: {data.get('message')}")
            return []
        results = data.get("results") or []
        out: List[Dict[str, Any]] = []
        for poi in results[:count]:
            loc = poi.get("location") or {}
            try:
                b_lon, b_lat = float(loc.get("lng")), float(loc.get("lat"))
            except (TypeError, ValueError):
                continue
            lon, lat = bd09_to_wgs84(b_lon, b_lat)
            city = _clean_city(poi.get("city"))
            # 百度 Place API v2 的区县字段是 area（不是 district）
            district = str(poi.get("area") or poi.get("district") or "").strip()
            province = _clean_city(poi.get("province")) or city
            code = CITY_CODE_MAP.get(city) or CITY_CODE_MAP.get(f"{city}市") or 0
            if not code:
                near = infer_city_from_coords(lat, lon)
                code = near[0] if near else 0
            name = str(poi.get("name") or keyword).strip()
            raw_addr = str(poi.get("address") or "").strip()
            full = raw_addr or f"{province}{city}{district}{name}"
            out.append({
                "city_code": code,
                "city_name": city or "未知",
                "province": province,
                "district_name": district,
                "town_name": "",
                "poi": name,
                "short_name": name,
                "full_address": full,
                "latitude": f"{lat:.6f}",
                "longitude": f"{lon:.6f}",
            })
        return out
    except Exception as e:
        logger.warning(f"百度 POI 检索异常: {e}")
        return []


async def _baidu_test(key: str) -> Dict[str, Any]:
    res = await _baidu_reverse(30.593099, 114.305393, key)
    if res:
        return {"ok": True, "message": f"百度地图 API 鉴权连通成功：{res['city_name']} · {res['address_name']}"}
    return {"ok": False, "message": "百度地图 API 鉴权失败或配额不足，请检查 AK 与已启用服务"}


# ---------------- 天地图 ---------------- #

async def _tianditu_reverse(lat: float, lon: float, key: str) -> Optional[Dict[str, Any]]:
    res = await tianditu_client.resolve_location(lat, lon, key or None)
    if not res or not res.get("city_name"):
        return None
    return {
        "city_code": res.get("city_code") or 0,
        "city_name": res.get("city_name"),
        "locality": res.get("town") or res.get("district") or "",
        "province": res.get("province") or "",
        "address_name": res.get("address_name") or f"{res.get('city_name')}定位点",
        "latitude": f"{lat:.6f}",
        "longitude": f"{lon:.6f}",
        "accuracy": "high",
    }


async def _tianditu_search(keyword: str, key: str, count: int) -> List[Dict[str, Any]]:
    return await tianditu_client.search_poi(keyword, key or None, count)


async def _tianditu_test(key: str) -> Dict[str, Any]:
    return await tianditu_client.test_connection(key or None)


# ---------------- 统一入口 ---------------- #

_REVERSE_FUNCS = {
    "amap": _amap_reverse,
    "baidu": _baidu_reverse,
    "tianditu": _tianditu_reverse,
}
_SEARCH_FUNCS = {
    "amap": _amap_search,
    "baidu": _baidu_search,
    "tianditu": _tianditu_search,
}
_TEST_FUNCS = {
    "amap": _amap_test,
    "baidu": _baidu_test,
    "tianditu": _tianditu_test,
}


async def reverse_geocode(latitude: float, longitude: float, settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """按 高德 > 百度 > 天地图 优先级逆地理编码，首个成功结果直接返回"""
    cfg = settings or get_provider_settings()
    for source in enabled_providers(cfg):
        key = cfg.get(f"{source}_key", "")
        try:
            res = await _REVERSE_FUNCS[source](latitude, longitude, key)
            if res and int(res.get("city_code") or 0) > 0 and res.get("city_name") not in ("", "未知"):
                return _tagged(res, source)
        except Exception as e:
            logger.warning(f"{SOURCE_NAMES.get(source, source)}逆地理编码路由异常: {e}")
    return None


async def search_poi(keyword: str, count: int = 10, settings: Optional[Dict[str, Any]] = None, current_city: str = "") -> List[Dict[str, Any]]:
    """按 高德 > 百度 > 天地图 优先级检索 POI，首个有结果的源直接返回"""
    cfg = settings or get_provider_settings()
    city = infer_city_from_keyword(keyword, current_city)
    for source in enabled_providers(cfg):
        key = cfg.get(f"{source}_key", "")
        try:
            # 天地图自带行政区解析，无需 city；高德/百度需要 city 才能解析泛词
            if source == "tianditu":
                items = await _SEARCH_FUNCS[source](keyword, key, count)
            else:
                items = await _SEARCH_FUNCS[source](keyword, key, count, city)
            valid = [i for i in items if int(i.get("city_code") or 0) > 0 and str(i.get("city_name") or "").strip()]
            if valid:
                return [_tagged(i, source) for i in valid]
        except Exception as e:
            logger.warning(f"{SOURCE_NAMES.get(source, source)}POI 检索路由异常: {e}")
    return []


async def test_connection(source: str, key: str = "") -> Dict[str, Any]:
    """测试指定地图源的连通性"""
    source = str(source or "").strip().lower()
    if source not in _TEST_FUNCS:
        return {"ok": False, "message": f"不支持的地图源: {source}"}
    cfg = get_provider_settings()
    test_key = str(key or cfg.get(f"{source}_key", "") or "").strip()
    if not test_key and source != "tianditu":
        return {"ok": False, "message": f"请先填写{SOURCE_NAMES.get(source, source)}服务密钥"}
    try:
        return await _TEST_FUNCS[source](test_key)
    except Exception as e:
        return {"ok": False, "message": f"{SOURCE_NAMES.get(source, source)}连通性测试异常: {e}"}
