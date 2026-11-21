import React, { useEffect, useState } from 'react';
import { Button, Card, Empty, Popconfirm, Space, Tag, Toast, Typography } from '@douyinfe/semi-ui';
import {
  IconDelete,
  IconExternalOpen,
  IconQrCode,
  IconRefresh,
  IconSmartphoneStroked,
  IconUnlink,
} from '@douyinfe/semi-icons';
import { api } from '../api';
import type { DevicePairStartResult, PairedDevice } from '../types';

const { Text } = Typography;

const isMobileClient = typeof navigator !== 'undefined' &&
  /iPhone|iPad|iPod|Android|Windows Phone|Mobile|mobile/i.test(navigator.userAgent);

const collectLocalStateSnapshot = (): Record<string, any> => {
  const snapshot: Record<string, any> = {};
  Object.keys(localStorage).forEach((key) => {
    if (!key.startsWith('xiaocan_') || key === 'xiaocan_device_token') return;
    const raw = localStorage.getItem(key);
    if (raw === null) return;
    try { snapshot[key] = JSON.parse(raw); } catch { snapshot[key] = raw; }
  });
  return snapshot;
};

export const DeviceSyncPanel: React.FC = () => {
  const [pairing, setPairing] = useState(false);
  const [pairInfo, setPairInfo] = useState<DevicePairStartResult | null>(null);
  const [pairStatus, setPairStatus] = useState('');
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);

  const loadPairedDevices = async (silent = false) => {
    if (!silent) setLoadingDevices(true);
    try {
      const res = await api.getPairedDevices();
      if (res.ok) setPairedDevices(res.devices || []);
    } catch (e: any) {
      if (!silent) Toast.error(`获取设备列表失败: ${e?.response?.data?.detail || e.message || '未知错误'}`);
    } finally {
      if (!silent) setLoadingDevices(false);
    }
  };

  const handleStartPair = async () => {
    setPairing(true);
    setPairStatus('正在生成配对二维码...');
    try {
      const res = await api.startDevicePair(collectLocalStateSnapshot());
      if (!res.ok) throw new Error('生成配对二维码失败');
      setPairInfo(res);
      setPairStatus('等待移动端扫码确认');
      Toast.success(`二维码已生成，${res.expires_in} 秒内有效`);
    } catch (e: any) {
      setPairStatus('');
      Toast.error(`生成失败: ${e?.response?.data?.detail || e.message || '未知错误'}`);
    } finally {
      setPairing(false);
    }
  };

  const pollPairStatus = async () => {
    if (!pairInfo) return;
    try {
      const res = await api.getDevicePairStatus(pairInfo.ticket);
      setPairStatus(res.status === 'used' ? '已授权并同步' : (res.message || `状态: ${res.status}`));
      if (res.status === 'used' || res.status === 'expired' || res.status === 'not_found') {
        setPairInfo(null);
        void loadPairedDevices(true);
      }
    } catch { /* 轮询失败不打扰用户 */ }
  };

  useEffect(() => {
    void loadPairedDevices(true);
  }, []);

  useEffect(() => {
    if (!pairInfo) return;
    const timer = window.setInterval(pollPairStatus, 2000);
    return () => window.clearInterval(timer);
  }, [pairInfo]);

  const handleRevokeDevice = async (deviceId: string) => {
    try {
      const res = await api.revokePairedDevice(deviceId);
      Toast.success(res.message || '已注销设备');
      void loadPairedDevices(true);
    } catch (e: any) {
      Toast.error(`注销失败: ${e?.response?.data?.detail || e.message || '未知错误'}`);
    }
  };

  const handleDeleteDevice = async (deviceId: string) => {
    try {
      const res = await api.deletePairedDevice(deviceId);
      Toast.success(res.message || '已删除设备记录');
      void loadPairedDevices(true);
    } catch (e: any) {
      Toast.error(`删除失败: ${e?.response?.data?.detail || e.message || '未知错误'}`);
    }
  };

  return (
    <div className="space-y-4">
      <div className="text-xs text-semi-color-text-2 leading-relaxed space-y-1">
        <div>PC 端配置完成后生成短时二维码，移动端在同一局域网扫码即可同步账号与配置，无需重新手动录入。</div>
        <div>二维码仅包含随机票据，不含账号 Token；默认 5 分钟有效且只能使用一次。</div>
      </div>

      {isMobileClient ? (
        <div className="p-4 rounded-xl bg-semi-color-fill-0 border border-semi-color-border text-center space-y-3">
          <IconSmartphoneStroked className="text-semi-color-primary" size="extra-large" />
          <div>
            <Text strong>移动端扫码入口</Text>
            <p className="text-xs text-semi-color-text-2 mt-1">请使用手机相机或微信扫一扫 PC 端展示的二维码；扫码后自动进入确认与同步页面。</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4 items-center sm:items-center">
          <div className="shrink-0 w-[220px] h-[220px] rounded-xl border border-semi-color-border bg-white flex items-center justify-center overflow-hidden">
            {pairInfo ? (
              <img src={pairInfo.qr_image} alt="设备协同二维码" className="w-full h-full object-contain" />
            ) : (
              <div className="text-center text-semi-color-text-2 text-xs px-4">
                <IconQrCode size="extra-large" className="mb-2" />
                <div>尚未生成二维码</div>
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0 space-y-2">
            <Button theme="solid" type="primary" icon={<IconQrCode />} loading={pairing} onClick={handleStartPair}>
              生成配对二维码
            </Button>
            <div className="text-xs text-semi-color-text-2 break-all">
              {pairStatus || '二维码生成后请在 5 分钟内用手机扫码确认。'}
            </div>
            {pairInfo && (
              <>
                <div className="text-xs text-semi-color-text-2 break-all">协同地址：{pairInfo.url}</div>
                <Button
                  size="small"
                  theme="light"
                  icon={<IconExternalOpen />}
                  onClick={() => navigator.clipboard?.writeText(pairInfo.url).then(() => Toast.success('协同地址已复制')).catch(() => Toast.warning('复制失败，请手动复制'))}
                >
                  复制地址
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      <Card
        className="rounded-xl border border-semi-color-border shadow-xs"
        title={
          <div className="flex justify-between items-center w-full gap-2">
            <span className="font-semibold text-base">已授权设备</span>
            <Button size="small" theme="light" icon={<IconRefresh spin={loadingDevices} />} onClick={() => void loadPairedDevices()}>刷新</Button>
          </div>
        }
      >
        {pairedDevices.length === 0 ? (
          <Empty description="暂无已授权设备" />
        ) : (
          <div className="space-y-2">
            {pairedDevices.map((device) => (
              <div key={device.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg border border-semi-color-border bg-semi-color-fill-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Text strong size="small">{device.name}</Text>
                    <Tag color={device.status === 'active' ? 'green' : 'grey'} size="small">
                      {device.status === 'active' ? '在线凭证' : '已注销'}
                    </Tag>
                  </div>
                  <div className="text-xs text-semi-color-text-2 mt-1 break-all">
                    ID: {device.id} · IP: {device.client_ip || '未知'} · 最后活跃: {device.last_seen_at ? new Date(device.last_seen_at * 1000).toLocaleString('zh-CN') : '尚未同步'}
                  </div>
                </div>
                <Space>
                  {device.status === 'active' ? (
                    <Popconfirm
                      title="注销此设备？"
                      content="注销后该设备下次校验会被踢下线并清除本地缓存；设备记录仍保留。"
                      onConfirm={() => void handleRevokeDevice(device.id)}
                    >
                      <Button size="small" theme="light" type="warning" icon={<IconUnlink />}>注销</Button>
                    </Popconfirm>
                  ) : (
                    <Popconfirm title="删除设备记录？" onConfirm={() => void handleDeleteDevice(device.id)}>
                      <Button size="small" theme="light" type="danger" icon={<IconDelete />}>删除</Button>
                    </Popconfirm>
                  )}
                </Space>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
