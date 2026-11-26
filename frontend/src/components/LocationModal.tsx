import React, { useState, useEffect, useRef } from 'react';
import {
  Modal,
  Input,
  Tag,
  Button,
  Dropdown,
  Toast,
  Card,
  Typography,
  Space,
  Divider,
  Banner
} from '@douyinfe/semi-ui';
import {
  IconDesktop,
  IconSearch,
  IconRefresh,
  IconUser
} from '@douyinfe/semi-icons';
import { useAppStore, deriveAccountLocation } from '../store/useAppStore';
import { api } from '../api';
import type { LocationCandidate, LocationHistoryItem } from '../types';

interface LocationModalProps {
  visible: boolean;
  onClose: () => void;
  targetAccountKey?: string | null;
}

const formatCityTag = (rawCity?: string, district?: string) => {
  if (rawCity && rawCity !== '未知') {
    return rawCity
      .replace(/(特别行政区|自治区|自治州|地区|盟|市|省)$/, '')
      .trim() || rawCity;
  }
  if (district) {
    return district
      .replace(/(特别行政区|自治区|自治州|地区|盟|市|省|区|县|街道|镇)$/, '')
      .trim() || district;
  }
  return '地点';
};

type SourceTagColor = 'amber' | 'blue' | 'cyan' | 'green' | 'grey' | 'indigo' | 'light-blue' | 'light-green' | 'lime' | 'orange' | 'pink' | 'purple' | 'red' | 'teal' | 'violet' | 'yellow' | 'white';

const MAP_SOURCE_META: Record<string, { label: string; color: SourceTagColor }> = {
  amap: { label: '高德地图', color: 'blue' },
  baidu: { label: '百度地图', color: 'red' },
  tianditu: { label: '天地图', color: 'green' },
  preset: { label: '预设城市', color: 'grey' },
  fallback: { label: '备用服务', color: 'orange' },
  ip: { label: 'IP 定位', color: 'purple' },
};

const formatSourceTag = (source?: string, sourceName?: string) => {
  const key = String(source || '').toLowerCase();
  if (sourceName) return sourceName;
  return MAP_SOURCE_META[key]?.label || '未知来源';
};

const sourceTagColor = (source?: string): SourceTagColor => {
  const key = String(source || '').toLowerCase();
  return MAP_SOURCE_META[key]?.color || 'grey';
};

// 弹窗内统一格式：短名称 · 完整地址（缺字段时退化为已有地址）
const formatAddressDetail = (shortName?: string, fullAddress?: string, fallback?: string) => {
  const short = String(shortName || '').trim();
  const full = String(fullAddress || '').trim();
  if (short && full) return short === full ? short : `${short}·${full}`;
  return short || full || String(fallback || '');
};

export const LocationModal: React.FC<LocationModalProps> = ({ visible, onClose, targetAccountKey }) => {
  const accounts = useAppStore((s) => s.accounts);
  const currentAccountKey = useAppStore((s) => s.currentAccountKey);
  const locationModalAccountKey = useAppStore((s) => s.locationModalAccountKey);
  const bindAccountLocation = useAppStore((s) => s.bindAccountLocation);
  const locationHistory = useAppStore((s) => s.locationHistory);
  const addLocationHistory = useAppStore((s) => s.addLocationHistory);
  const removeLocationHistory = useAppStore((s) => s.removeLocationHistory);
  const updateLocationHistoryRemark = useAppStore((s) => s.updateLocationHistoryRemark);
  const clearLocationHistory = useAppStore((s) => s.clearLocationHistory);
  const openMapSourceSettings = useAppStore((s) => s.openMapSourceSettings);

  const showMapSourceRequired = (message?: string) => {
    Toast.warning({
      duration: 6,
      content: (
        <span>
          {message || '请前往系统与通知—位置与地理服务配置地图源参数'}
          <a
            className="ml-2 text-semi-color-primary cursor-pointer underline"
            onClick={() => openMapSourceSettings()}
          >
            前往配置
          </a>
        </span>
      ),
    });
  };

  const effectiveAccountKey = targetAccountKey || locationModalAccountKey || currentAccountKey;
  const targetAccount = accounts.find((a) => a.key === effectiveAccountKey) || null;
  const targetAccountLoc = deriveAccountLocation(targetAccount);

  const [editLng, setEditLng] = useState<string>(targetAccountLoc?.longitude || '');
  const [editLat, setEditLat] = useState<string>(targetAccountLoc?.latitude || '');
  const [resolvedCityCode, setResolvedCityCode] = useState<number>(targetAccountLoc?.cityCode || 0);
  const [resolvedCityName, setResolvedCityName] = useState<string>(targetAccountLoc?.cityName || '');
  const [resolvedAddress, setResolvedAddress] = useState<string>(targetAccountLoc?.addressName || '');
  const [resolvedShortName, setResolvedShortName] = useState<string>(targetAccountLoc?.shortName || '');
  const [resolvedFullAddress, setResolvedFullAddress] = useState<string>(targetAccountLoc?.fullAddress || '');
  const [resolvedSource, setResolvedSource] = useState<string>('');
  const [resolvedSourceName, setResolvedSourceName] = useState<string>('');
  const [resolvedRemark, setResolvedRemark] = useState<string>('');
  const [editingRemarkKey, setEditingRemarkKey] = useState<string | null>(null);
  const [remarkDraft, setRemarkDraft] = useState<string>('');

  const [resolving, setResolving] = useState<boolean>(false);
  const [locating, setLocating] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // 搜索关键词与浮层下拉状态
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [searching, setSearching] = useState<boolean>(false);
  const [candidates, setCandidates] = useState<LocationCandidate[]>([]);
  const [dropdownVisible, setDropdownVisible] = useState<boolean>(false);

  // 动态测量搜索栏宽度，确保下拉浮层与搜索栏 1:1 像素级精准对齐
  const searchRowRef = useRef<HTMLDivElement>(null);
  const [menuWidth, setMenuWidth] = useState<number>(532);

  // 定位/反查失败时清空整组结果，避免残留上一次的坐标与地址脏数据
  const clearResolved = () => {
    setEditLng('');
    setEditLat('');
    setResolvedCityCode(0);
    setResolvedCityName('');
    setResolvedAddress('');
    setResolvedShortName('');
    setResolvedFullAddress('');
    setResolvedSource('');
    setResolvedSourceName('');
    setResolvedRemark('');
    setCandidates([]);
    setDropdownVisible(false);
  };

  const updateMenuWidth = () => {
    if (searchRowRef.current) {
      const w = searchRowRef.current.offsetWidth;
      if (w > 0) {
        setMenuWidth(w);
      }
    }
  };

  useEffect(() => {
    if (visible) {
      setEditLng(targetAccountLoc?.longitude || '');
      setEditLat(targetAccountLoc?.latitude || '');
      setResolvedCityCode(targetAccountLoc?.cityCode || 0);
      setResolvedCityName(targetAccountLoc?.cityName || '');
      setResolvedAddress(targetAccountLoc?.addressName || '');
      setResolvedShortName(targetAccountLoc?.shortName || '');
      setResolvedFullAddress(targetAccountLoc?.fullAddress || '');
      setResolvedSource(targetAccountLoc?.source || '');
      setResolvedSourceName(targetAccountLoc?.sourceName || '');
      setResolvedRemark(targetAccountLoc?.remark || '');
      setSearchKeyword('');
      setCandidates([]);
      setDropdownVisible(false);

      // 弹窗渲染挂载后测量实际宽度
      updateMenuWidth();
      const t1 = setTimeout(updateMenuWidth, 50);
      const t2 = setTimeout(updateMenuWidth, 180);
      window.addEventListener('resize', updateMenuWidth);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
        window.removeEventListener('resize', updateMenuWidth);
      };
    } else {
      setDropdownVisible(false);
    }
  }, [visible, effectiveAccountKey]);

  // 反查经纬度对应地址
  const handleResolveCoords = async (latStr?: string, lngStr?: string, showToast = true) => {
    const targetLat = String(latStr ?? editLat ?? '').trim();
    const targetLng = String(lngStr ?? editLng ?? '').trim();
    const latVal = parseFloat(targetLat);
    const lngVal = parseFloat(targetLng);

    if (isNaN(latVal) || isNaN(lngVal)) {
      if (showToast) Toast.error('请输入有效的经纬度数值');
      return false;
    }

    setResolving(true);
    try {
      const res = await api.resolveLocation(latVal, lngVal);
      if (res && (res as any).no_map_source) {
        clearResolved();
        if (showToast) showMapSourceRequired((res as any).message);
        return false;
      }
      if (res && res.ok && res.city_name && Number(res.city_code || 0) > 0) {
        const full = res.address_name || `${res.city_name}市`;
        setResolvedCityCode(Number(res.city_code));
        setResolvedCityName(res.city_name);
        setResolvedAddress(full);
        setResolvedShortName(res.locality || res.address_name || '');
        setResolvedFullAddress(full);
        setResolvedSource(res.source || '');
        setResolvedSourceName(res.source_name || '');
        if (showToast) {
          Toast.success(`解析成功：${res.city_name} · ${res.address_name}（${formatSourceTag(res.source, res.source_name)}）`);
        }
        return true;
      } else {
        clearResolved();
        if (showToast) Toast.warning('未解析到该坐标的有效城市信息，请通过上方搜索框选取地址');
        return false;
      }
    } catch {
      clearResolved();
      if (showToast) Toast.error('反查地址失败，请检查网络');
      return false;
    } finally {
      setResolving(false);
    }
  };

  // 选中某一个候选地址项
  const handleSelectCandidate = (cand: LocationCandidate) => {
    setEditLng(cand.longitude);
    setEditLat(cand.latitude);
    setResolvedCityCode(Number(cand.city_code || 0));
    setResolvedCityName(cand.city_name);
    setResolvedAddress(cand.full_address || `${cand.city_name} · ${cand.short_name}`);
    setResolvedShortName(cand.short_name || cand.poi || '');
    setResolvedFullAddress(cand.full_address || '');
    setResolvedSource(cand.source || '');
    setResolvedSourceName(cand.source_name || '');
    setDropdownVisible(false);
    Toast.success(`已选择：${cand.city_name} · ${cand.short_name}（${formatSourceTag(cand.source, cand.source_name)}）`);
  };

  // 选中历史位置
  const handleSelectHistory = (item: LocationHistoryItem) => {
    setEditLng(item.longitude);
    setEditLat(item.latitude);
    setResolvedCityCode(Number(item.cityCode || 0));
    setResolvedCityName(item.cityName);
    setResolvedAddress(item.addressName);
    setResolvedShortName(item.shortName || item.remark || item.addressName);
    setResolvedFullAddress(item.fullAddress || item.addressName);
    setResolvedSource(item.source || '');
    setResolvedSourceName(item.sourceName || '');
    setResolvedRemark(item.remark || '');
    setEditingRemarkKey(null);
    Toast.success(`已填入历史位置：${item.cityName} · ${item.addressName}${item.sourceName ? `（${item.sourceName}）` : ''}`);
  };

  // 保存历史备注：写回历史并同步为当前位置，保证「绑定并保存」的坐标与备注一致
  const saveHistoryRemark = (item: LocationHistoryItem, value: string) => {
    const remark = (value || '').trim().slice(0, 40);
    updateLocationHistoryRemark(item, remark);
    handleSelectHistory({ ...item, remark });
  };

  // 仅在用户主动按 Enter 或点击【搜索】时单次触发检索 (严禁打字实时触发)
  const handleExecuteSearch = async () => {
    const cleanKw = (searchKeyword || '').trim();
    if (!cleanKw) {
      Toast.warning('请输入搜索关键词');
      return;
    }
    setSearching(true);
    try {
      const res = await api.searchLocation(cleanKw, resolvedCityName || undefined);
      if (res && (res as any).no_map_source) {
        showMapSourceRequired((res as any).message);
        setCandidates([]);
        setDropdownVisible(false);
        return;
      }
      if (res && res.ok && res.candidates && res.candidates.length > 0) {
        if (res.candidates.length === 1) {
          // 单条候选直接应用，无需下拉点选
          handleSelectCandidate(res.candidates[0]);
          setDropdownVisible(false);
        } else {
          // 多条候选展开浮层下拉菜单供用户点选，提前同步宽度
          updateMenuWidth();
          setCandidates(res.candidates);
          setDropdownVisible(true);
        }
      } else {
        setCandidates([]);
        setDropdownVisible(false);
        Toast.info('未找到匹配地点，请尝试输入更详细的地址或城市名');
      }
    } catch {
      setCandidates([]);
      setDropdownVisible(false);
      Toast.error('检索失败，请重试');
    } finally {
      setSearching(false);
    }
  };

  // 读取本机定位 (核心重点功能)
  const handleGetDeviceLocation = () => {
    setLocating(true);

    if (!navigator.geolocation) {
      clearResolved();
      setLocating(false);
      Toast.warning('当前浏览器不支持定位接口，请使用搜索框选择地址');
      return;
    }

    // 浏览器要求定位接口运行在安全上下文（HTTPS 或 localhost）中；
    // 局域网 HTTP 访问时即使站点权限设为“允许”，定位仍会被拒绝。
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      clearResolved();
      setLocating(false);
      Toast.warning('当前通过局域网 HTTP 访问，浏览器会禁止网页定位。请改用 HTTPS 访问，或直接使用搜索框选择地址。');
      return;
    }

    // 与改动前一致：拿到浏览器首个定位回调后立刻请求接口，不再设置坐标收敛窗口。
    // 仅保留「权限拒绝/超时分类提示、失败清空脏数据、定位成功后写短/全地址」等修复。
    let settled = false;

    const resolveFix = async (pos: GeolocationPosition) => {
      if (settled) return;
      settled = true;
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      try {
        const res = await api.resolveLocation(lat, lng);
        if (res && (res as any).no_map_source) {
          clearResolved();
          showMapSourceRequired((res as any).message);
        } else if (res && res.ok && res.city_name && Number(res.city_code || 0) > 0) {
          // 仅在逆地理编码成功确认后才写入坐标，失败不留下半截数据
          setEditLng(lng.toFixed(6));
          setEditLat(lat.toFixed(6));
          setResolvedCityCode(Number(res.city_code));
          setResolvedCityName(res.city_name);
          setResolvedAddress(res.address_name || `${res.city_name}市`);
          setResolvedShortName(res.locality || res.address_name || '');
          setResolvedFullAddress(res.address_name || `${res.city_name}市`);
          setResolvedSource(res.source || '');
          setResolvedSourceName(res.source_name || '');
          Toast.success(`已成功获取定位：${res.city_name} · ${res.address_name}（${formatSourceTag(res.source, res.source_name)}）`);
        } else {
          clearResolved();
          Toast.error('浏览器已返回坐标，但无法解析出有效城市，请尝试搜索地址');
        }
      } catch {
        clearResolved();
        Toast.error('解析定位坐标失败，请检查网络或地图源配置');
      } finally {
        setLocating(false);
      }
    };

    // 浏览器定位失败时直接暴露真实原因，不再静默降级 IP，避免掩盖定位故障。
    try {
      navigator.geolocation.getCurrentPosition(
        (pos) => void resolveFix(pos),
        (err: GeolocationPositionError) => {
          if (settled) return;
          settled = true;
          clearResolved();
          setLocating(false);
          const code = err?.code;
          const insecure = typeof window !== 'undefined' && !window.isSecureContext;
          const msg = code === 1
            ? (insecure
              ? '当前为局域网 HTTP 访问，浏览器禁止网页定位；请改用 HTTPS，或使用搜索框选择地址'
              : '位置权限被拒绝，请在浏览器地址栏允许位置访问，或使用搜索框选择地址')
            : code === 3
            ? '等待定位超时，请确认已点击浏览器弹窗「允许」后重试，或使用搜索框'
            : code === 2
            ? '系统暂时无法提供位置，请检查 Windows 定位服务后重试，或使用搜索框'
            : '浏览器定位失败，请使用搜索框选择地址';
          console.warn('[抢单定位] 浏览器定位失败', { code, message: err?.message });
          Toast.warning(msg);
        },
        { timeout: 20000, maximumAge: 3000, enableHighAccuracy: true }
      );
    } catch (e) {
      if (!settled) {
        settled = true;
        clearResolved();
        setLocating(false);
        console.warn('[抢单定位] 浏览器定位调用异常', e);
        Toast.warning('浏览器定位调用异常，请使用搜索框选择地址');
      }
    }
    // 兜底：权限弹窗长时间未响应时直接提示，不再降级 IP
    window.setTimeout(() => {
      if (!settled) {
        settled = true;
        clearResolved();
        setLocating(false);
        Toast.warning('浏览器定位无响应，请确认已允许位置访问后重试，或使用搜索框');
      }
    }, 21000);
  };

  // 确认绑定保存到账号数据库
  const handleConfirmLocation = async () => {
    if (!targetAccount) {
      Toast.error('请添加小蚕账号之后再设置抢单定位');
      return;
    }

    const latVal = parseFloat(editLat);
    const lngVal = parseFloat(editLng);

    if (isNaN(latVal) || isNaN(lngVal) || latVal === 0 || lngVal === 0) {
      Toast.error('请输入有效的非零经纬度坐标，或使用搜索/定位获取');
      return;
    }

    let cName = resolvedCityName;
    let cCode = Number(resolvedCityCode || 0);
    let addr = resolvedAddress;

    if (!addr || !cName || cName === '未知' || cName === '未知城市' || cCode <= 0) {
      try {
        const res = await api.resolveLocation(latVal, lngVal);
        if (res && (res as any).no_map_source) {
          showMapSourceRequired((res as any).message);
          return;
        }
        if (res && res.ok && res.city_name && Number(res.city_code || 0) > 0) {
          cName = res.city_name;
          cCode = Number(res.city_code);
          addr = res.address_name || `${res.city_name}市`;
          setResolvedShortName(res.locality || addr);
          setResolvedFullAddress(addr);
          setResolvedSource(res.source || '');
          setResolvedSourceName(res.source_name || '');
        }
      } catch {
        // ignore
      }
    }

    if (!cCode || cCode <= 0 || !cName || cName === '未知' || cName === '未知城市') {
      Toast.error('未能识别该坐标所属城市，请通过关键词搜索选择具体地点后保存');
      return;
    }

    const newLoc = {
      cityCode: cCode,
      cityName: cName.trim(),
      addressName: (addr || `${cName.trim()}定位点`).trim(),
      shortName: (resolvedShortName || addr || cName.trim()).trim(),
      fullAddress: (resolvedFullAddress || addr || `${cName.trim()}定位点`).trim(),
      source: resolvedSource,
      sourceName: resolvedSourceName,
      remark: (resolvedRemark || '').trim(),
      longitude: (editLng || '').trim(),
      latitude: (editLat || '').trim()
    };

    setSaving(true);
    try {
      await bindAccountLocation(targetAccount.key, newLoc);
      addLocationHistory(newLoc);
      Toast.success(`账号【${targetAccount.nick_name}】已绑定定位：${newLoc.cityName} · ${newLoc.addressName}`);
      onClose();
    } catch (err: any) {
      Toast.error(err?.response?.data?.detail || err?.message || '保存账号定位失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="抢单定位"
      visible={visible}
      onOk={handleConfirmLocation}
      onCancel={onClose}
      okText="绑定并保存"
      cancelText="取消"
      confirmLoading={saving}
      okButtonProps={{ disabled: !targetAccount }}
      width={580}
      centered
    >
      <div className="space-y-3.5 py-1">
        {targetAccount ? (
          <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-semi-color-fill-0 border border-semi-color-border">
            <Space spacing="tight">
              <IconUser className="text-semi-color-primary" />
              <Typography.Text size="small">当前绑定账号：</Typography.Text>
              <Typography.Text strong size="small">{targetAccount.nick_name}</Typography.Text>
            </Space>
            <Tag size="small" color={targetAccountLoc ? 'green' : 'amber'}>
              {targetAccountLoc ? `已绑: ${targetAccountLoc.cityName}` : '尚未绑定地址'}
            </Tag>
          </div>
        ) : (
          <Banner
            type="warning"
            closeIcon={null}
            description="系统尚未接入任何小蚕账号。地址必须跟随账号保存，请先添加小蚕账号后再绑定地址。"
          />
        )}
        {/* 1. 当前位置展示与一键获取本机定位 (重点核心卡片) */}
        <Card
          bordered
          header={
            <div className="flex items-center justify-between w-full">
              <Space align="center" spacing="tight">
                <Typography.Text strong size="small">当前位置</Typography.Text>
                <Tag size="small" color={resolvedCityName ? "blue" : "grey"}>
                  {resolvedCityName ? formatCityTag(resolvedCityName) : '未设置'}
                </Tag>
                {resolvedAddress && (
                  <Tag size="small" color={sourceTagColor(resolvedSource)} className="font-normal">
                    {formatSourceTag(resolvedSource, resolvedSourceName)}
                  </Tag>
                )}
              </Space>
              <Button
                theme="solid"
                type="primary"
                icon={<IconDesktop />}
                loading={locating}
                onClick={handleGetDeviceLocation}
                onMouseDown={(e) => e.preventDefault()}
                size="small"
              >
                获取本机定位
              </Button>
            </div>
          }
          headerStyle={{ padding: '10px 14px 6px', borderBottom: 'none' }}
          bodyStyle={{ padding: '0 14px 10px' }}
          style={{ backgroundColor: 'var(--semi-color-fill-0)', borderRadius: 'var(--semi-border-radius-medium)' }}
        >
          <Typography.Title heading={6} ellipsis={{ showTooltip: true }} style={{ margin: '0 0 4px' }}>
            {resolvedAddress
              ? formatAddressDetail(resolvedShortName, resolvedFullAddress, resolvedAddress)
              : '未获取位置，请点击右上角「获取本机定位」或在下方搜索地址'}
          </Typography.Title>
          <Typography.Text code size="small" type="secondary">
            {editLng && editLat ? `坐标: ${editLng}, ${editLat}` : '经纬度未配置'}
          </Typography.Text>
        </Card>

        {/* 2. 搜索其他地址 (采用 Dropdown 浮层下拉，与搜索栏 100% 等宽对齐，弹窗高度全程不改变) */}
        <Dropdown
          trigger="custom"
          visible={dropdownVisible}
          onClickOutSide={() => setDropdownVisible(false)}
          position="bottomLeft"
          zIndex={1060}
          spacing={6}
          style={{ width: `${menuWidth}px` }}
          render={
            <Dropdown.Menu
              style={{
                width: `${menuWidth}px`,
                minWidth: `${menuWidth}px`,
                maxWidth: `${menuWidth}px`,
                maxHeight: 320,
                overflowY: 'auto'
              }}
            >
              <Dropdown.Title className="text-xs text-semi-color-text-2 font-normal pb-1">
                候选地点（共 {candidates.length} 条结果）
              </Dropdown.Title>
              {candidates.map((cand, idx) => (
                <Dropdown.Item
                  key={`${cand.city_name}-${cand.latitude}-${cand.longitude}-${idx}`}
                  onClick={() => handleSelectCandidate(cand)}
                  style={{ maxWidth: 'none', width: '100%', padding: '10px 16px', boxSizing: 'border-box' }}
                  className="!max-w-none !w-full"
                >
                  <div className="flex items-center gap-3 py-0.5 w-full min-w-0">
                    <Tag size="small" color="blue" className="shrink-0 font-normal">
                      {formatCityTag(cand.city_name, cand.district_name)}
                    </Tag>
                    <Tag size="small" color={sourceTagColor(cand.source)} className="shrink-0 font-normal">
                      {formatSourceTag(cand.source, cand.source_name)}
                    </Tag>
                    <div className="flex flex-col flex-1 min-w-0">
                      <div className="text-xs text-semi-color-text-0 font-medium truncate">
                        {cand.short_name || cand.full_address}
                      </div>
                      <div
                        className="text-[11px] text-semi-color-text-2 truncate"
                        title={cand.full_address}
                      >
                        {cand.full_address}
                      </div>
                    </div>
                  </div>
                </Dropdown.Item>
              ))}
            </Dropdown.Menu>
          }
        >
          <div ref={searchRowRef} className="flex gap-2 w-full">
            <Input
              value={searchKeyword}
              placeholder="搜索地址或地标"
              prefix={<IconSearch />}
              showClear
              onChange={(val) => {
                setSearchKeyword(val);
                if (dropdownVisible) setDropdownVisible(false);
              }}
              onEnterPress={handleExecuteSearch}
              className="flex-1"
            />
            <Button
              type="primary"
              theme="light"
              loading={searching}
              icon={<IconSearch />}
              onClick={handleExecuteSearch}
              onMouseDown={(e) => e.preventDefault()}
              className="shrink-0"
            >
              搜索
            </Button>
          </div>
        </Dropdown>

        {/* 3. 历史位置：点击标签快速切回此前使用过的抢单位置 */}
        <Divider margin="8px" />
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-semi-color-text-2">历史位置</span>
            {locationHistory.length > 0 && (
              <Button
                size="small"
                theme="borderless"
                type="tertiary"
                className="text-[11px]"
                onClick={clearLocationHistory}
                onMouseDown={(e) => e.preventDefault()}
              >
                清空
              </Button>
            )}
          </div>
          {locationHistory.length === 0 ? (
            <div className="text-[11px] text-semi-color-text-3">
              暂无历史位置，确认设置后自动记录
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[132px] overflow-y-auto pr-1">
              {locationHistory.map((item) => {
                const itemKey = `${item.longitude}-${item.latitude}-${item.usedAt}`;
                const isCurrent =
                  Math.abs(parseFloat(item.longitude) - parseFloat(editLng || '0')) < 1e-5 &&
                  Math.abs(parseFloat(item.latitude) - parseFloat(editLat || '0')) < 1e-5;
                const detail = formatAddressDetail(item.shortName, item.fullAddress, item.addressName);
                // 有备注时只展示备注，否则展示 short_name·full_address
                const label = item.remark ? item.remark : detail;
                const sourceLabel = formatSourceTag(item.source, item.sourceName);
                const hasSource = Boolean(item.source || item.sourceName);
                return (
                  <div key={itemKey} className="flex items-center justify-between gap-2 py-0.5">
                    <div className="flex items-center gap-1 min-w-0 flex-1">
                      <Tag
                        size="small"
                        color={isCurrent ? 'blue' : 'grey'}
                        closable
                        className="cursor-pointer font-normal"
                        onClick={() => handleSelectHistory(item)}
                        onClose={() => removeLocationHistory(item)}
                      >
                        <span className="block truncate" title={label}>{label}</span>
                      </Tag>
                      {hasSource && (
                        <Tag size="small" color={sourceTagColor(item.source)} className="font-normal shrink-0">
                          {sourceLabel}
                        </Tag>
                      )}
                    </div>
                    {editingRemarkKey === itemKey ? (
                      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <Input
                          size="small"
                          value={remarkDraft}
                          placeholder="位置备注，最多 40 字"
                          maxLength={40}
                          onChange={(val) => setRemarkDraft(val)}
                          onEnterPress={() => saveHistoryRemark(item, remarkDraft)}
                          style={{ width: 150 }}
                        />
                        <Button
                          size="small"
                          theme="solid"
                          type="primary"
                          onClick={() => saveHistoryRemark(item, remarkDraft)}
                        >
                          保存
                        </Button>
                        <Button size="small" theme="light" onClick={() => setEditingRemarkKey(null)}>
                          取消
                        </Button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="shrink-0 text-[11px] text-semi-color-primary hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingRemarkKey(itemKey);
                          setRemarkDraft(item.remark || '');
                        }}
                      >
                        {item.remark ? '编辑备注' : '添加备注'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 4. 辅助微调区：经纬度弱化微调 (单行紧凑，视觉弱化) */}
        <Divider margin="8px" />
        <div className="flex items-center justify-between gap-2 text-xs text-semi-color-text-2">
          <Space align="center" spacing="tight" style={{ flex: 1 }}>
            <Typography.Text type="secondary" size="small" style={{ whiteSpace: 'nowrap' }}>坐标微调:</Typography.Text>
            <Input
              value={editLng}
              placeholder="经度"
              size="small"
              style={{ width: 110, fontFamily: 'monospace' }}
              onChange={(val) => setEditLng(val)}
            />
            <Input
              value={editLat}
              placeholder="纬度"
              size="small"
              style={{ width: 110, fontFamily: 'monospace' }}
              onChange={(val) => setEditLat(val)}
            />
          </Space>
          <Button
            size="small"
            theme="borderless"
            type="tertiary"
            icon={<IconRefresh />}
            loading={resolving}
            onClick={() => handleResolveCoords(editLat, editLng, true)}
            onMouseDown={(e) => e.preventDefault()}
          >
            逆地理编码
          </Button>
        </div>
      </div>
    </Modal>
  );
};
