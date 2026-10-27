import React, { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Empty, Input, Modal, Popconfirm, Tag, Toast, Tooltip, Typography } from '@douyinfe/semi-ui';
import { IconRefresh, IconSmartphoneStroked } from '@douyinfe/semi-icons';
import { api } from '../api';
import { copyText } from '../utils/clipboard';

const { Text } = Typography;

/** 判断设备凭证是否已过期 (后端 expires_at: 'YYYY-MM-DD HH:MM:SS') */
const isExpired = (expiresAt?: string): boolean => {
  if (!expiresAt) return false;
  const ts = new Date(String(expiresAt).replace(' ', 'T')).getTime();
  if (!Number.isFinite(ts)) return false;
  return Date.now() > ts;
};

/**
 * 设备协同面板 (添加小蚕账号弹窗 → 设备协同 Tab):
 * PC 生成一次性配对码 → 手机浏览器访问助手地址输入配对码 → 设备获得 30 天访问凭证,
 * 之后移动端即为瘦客户端, 同步使用 PC 端已绑定的全部账号、任务与配置 (token 不下发)。
 */
export const DevicePairingPanel: React.FC = () => {
  const [pairing, setPairing] = useState<{ code: string; expires_in: number; lan_address: string } | null>(null);
  const [remainSec, setRemainSec] = useState(0);
  // 配对码是否已被使用 (配对成功后遮罩失效, 避免继续对外展示有效数字)
  const [pairingUsed, setPairingUsed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [devices, setDevices] = useState<{ id: number; device_name: string; created_at: string; last_seen: string; ip?: string; expires_at?: string; revoked: number }[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  // 重命名弹窗 (配对时未填名称 → 未命名设备可在此修改)
  const [renameTarget, setRenameTarget] = useState<{ id: number; name: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameSubmitting, setRenameSubmitting] = useState(false);

  const loadDevices = useCallback(async () => {
    setDevicesLoading(true);
    try {
      const res = await api.getPairingDevices();
      setDevices(res.devices || []);
      // 顺带核对当前配对码是否已被使用 (手机配对成功后立即遮罩失效)
      setPairing((cur) => {
        if (cur?.code) {
          api.getPairingCodeStatus(cur.code).then((st) => {
            if (st?.used) setPairingUsed(true);
          }).catch(() => {});
        }
        return cur;
      });
    } catch { /* ignore */ } finally {
      setDevicesLoading(false);
    }
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const res = await api.createPairing();
      setPairing(res);
      setPairingUsed(false);
      setRemainSec(res.expires_in);
    } catch (e: any) {
      Toast.error(e.response?.data?.detail || '生成配对码失败');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: number) => {
    try {
      await api.revokePairingDevice(id);
      Toast.success('设备已吊销');
      loadDevices();
    } catch {
      Toast.error('吊销失败');
    }
  };

  const handlePurge = async (id: number) => {
    try {
      await api.purgePairingDevice(id);
      Toast.success('设备记录已删除');
      loadDevices();
    } catch (e: any) {
      Toast.error(e.response?.data?.detail || '删除失败');
    }
  };

  const openRename = (id: number, currentName: string) => {
    setRenameTarget({ id, name: currentName });
    setRenameValue(currentName === '未命名设备' ? '' : currentName);
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    const name = renameValue.trim();
    if (!name) {
      Toast.warning('请输入设备名称');
      return;
    }
    setRenameSubmitting(true);
    try {
      await api.renamePairingDevice(renameTarget.id, name);
      Toast.success(`设备名称已更新为「${name}」`);
      setRenameTarget(null);
      loadDevices();
    } catch (e: any) {
      Toast.error(e.response?.data?.detail || '重命名失败');
    } finally {
      setRenameSubmitting(false);
    }
  };

  // 配对码倒计时
  useEffect(() => {
    if (!pairing || remainSec <= 0) return;
    const timer = setInterval(() => setRemainSec((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [pairing, remainSec]);

  useEffect(() => {
    loadDevices();
    // 轮询刷新: 手机端配对成功后无需手动点刷新, 设备会自动出现在列表中
    const timer = setInterval(loadDevices, 4000);
    return () => clearInterval(timer);
  }, [loadDevices]);

  const mm = String(Math.floor(remainSec / 60)).padStart(2, '0');
  const ss = String(remainSec % 60).padStart(2, '0');
  const activeDevices = devices.filter((d) => !d.revoked);
  const revokedDevices = devices.filter((d) => !!d.revoked);

  return (
    <div className="flex flex-col gap-3 py-1">
      <Banner
        type="info"
        closeIcon={null}
        description="将手机浏览器访问下方局域网地址（需与 PC 同一 WiFi），在「设备配对」中输入本页生成的配对码，即可让手机同步使用 PC 端已绑定的全部小蚕账号、任务与配置。小蚕凭据仅保存在 PC 端，不会下发到手机。"
      />

      {/* 生成配对码 */}
      <div className="border border-semi-color-border rounded-xl p-4 bg-semi-color-bg-0">
        <div className="flex items-center justify-between mb-2">
          <Text strong className="text-[14px]">生成配对码</Text>
          {pairing && remainSec > 0 && !pairingUsed && (
            <div className="flex items-center gap-2">
              <Tag color="amber" size="small" shape="square" className="font-mono">
                有效期 {mm}:{ss}
              </Tag>
              <Button
                size="small"
                theme="borderless"
                type="primary"
                icon={<IconRefresh spin={creating} />}
                loading={creating}
                onClick={handleCreate}
              >
                刷新配对码
              </Button>
            </div>
          )}
        </div>

        {!pairing || remainSec <= 0 || pairingUsed ? (
          <div className="flex flex-col items-center gap-2 py-3">
            {pairingUsed ? (
              <div className="flex flex-col items-center gap-2 py-2">
                <div className="relative">
                  {/* 码被遮罩, 不对外展示 */}
                  <div
                    className="font-mono font-bold text-semi-color-text-2 tracking-[0.3em] select-none blur-[6px]"
                    style={{ fontSize: 42, lineHeight: 1.2 }}
                  >
                    {pairing?.code}
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Tag color="grey" size="large" shape="square" className="font-semibold">
                      该配对码已被使用，已失效
                    </Tag>
                  </div>
                </div>
                <Text type="tertiary" size="small">一台设备使用后配对码即失效，如需继续配对请重新生成</Text>
                <Button theme="solid" type="primary" size="large" loading={creating} onClick={handleCreate}>
                  重新生成配对码
                </Button>
              </div>
            ) : (
              <>
                <Button theme="solid" type="primary" size="large" loading={creating} onClick={handleCreate}>
                  生成 6 位配对码 (3 分钟有效)
                </Button>
                <Text type="tertiary" size="small">配对码为一次性使用，3 分钟内有效，过期后可重新生成</Text>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-2">
            <Tooltip content="点击复制配对码" position="top">
              <div
                className="font-mono font-bold text-semi-color-primary tracking-[0.3em] cursor-pointer hover:opacity-80 transition-opacity select-all"
                style={{ fontSize: 42, lineHeight: 1.2 }}
                onClick={async () => {
                  const ok = await copyText(pairing.code);
                  if (ok) Toast.success(`配对码 ${pairing.code} 已复制到剪贴板`);
                  else Toast.error('复制失败，请手动选择复制');
                }}
              >
                {pairing.code}
              </div>
            </Tooltip>
            <Text type="tertiary" size="small">点击配对码可复制 · 手机访问下方地址 → 输入此配对码 → 完成配对</Text>
            <div className="bg-semi-color-fill-0 rounded-lg px-3 py-1.5 font-mono text-xs text-semi-color-text-1 select-all">
              {pairing.lan_address}
            </div>
          </div>
        )}
      </div>

      {/* 手机端步骤 */}
      <div className="border border-dashed border-semi-color-border rounded-xl p-3.5 bg-semi-color-fill-0">
        <div className="flex items-center gap-2 mb-1.5">
          <IconSmartphoneStroked size="small" className="text-semi-color-primary" />
          <Text strong className="text-xs">手机端操作步骤</Text>
        </div>
        <div className="text-xs text-semi-color-text-2 space-y-1">
          <div>1. 手机与 PC 连接同一 WiFi，浏览器访问上方局域网地址；</div>
          <div>2. 打开页面后输入第一步生成的 6 位配对码并填写设备名称；</div>
          <div>3. 配对成功后建议「添加到主屏幕」，即可像 App 一样使用，账号、任务与配置与 PC 端实时同步。</div>
        </div>
      </div>

      {/* 已配对设备 */}
      <div className="border border-semi-color-border rounded-xl p-4 bg-semi-color-bg-0">
        <div className="flex items-center justify-between mb-2">
          <Text strong className="text-[14px]">已配对设备</Text>
          <Button size="small" theme="borderless" loading={devicesLoading} onClick={loadDevices}>
            刷新
          </Button>
        </div>
        {activeDevices.length === 0 && revokedDevices.length === 0 ? (
          <Empty title="暂无配对设备" description="按上方步骤完成配对后，设备将显示在这里" />
        ) : (
          <div className="flex flex-col gap-1.5">
            {[...activeDevices, ...revokedDevices].map((d) => (
              <div key={d.id} className="flex items-center justify-between gap-2 py-1.5 px-2 rounded-lg bg-semi-color-fill-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <Text strong size="small">{d.device_name}</Text>
                    {d.revoked ? (
                      <Tag color="grey" size="small">已吊销</Tag>
                    ) : isExpired(d.expires_at) ? (
                      <Tag color="red" size="small">已过期</Tag>
                    ) : (
                      <Tag color="green" size="small">在线凭证</Tag>
                    )}
                  </div>
                  <Text type="tertiary" size="small">
                    配对于 {d.created_at || '-'} · 最后活跃 {d.last_seen || '-'}
                    {d.ip ? ` · IP ${d.ip}` : ''}
                    {d.expires_at ? ` · 有效期至 ${d.expires_at}` : ''}
                  </Text>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button size="small" theme="borderless" type="primary" onClick={() => openRename(d.id, d.device_name)}>
                    编辑
                  </Button>
                  {!d.revoked && !isExpired(d.expires_at) ? (
                    <Popconfirm title="吊销后该设备将立即失去访问权限，确定吊销？" onConfirm={() => handleRevoke(d.id)}>
                      <Button size="small" type="danger" theme="light">吊销</Button>
                    </Popconfirm>
                  ) : (
                    <Popconfirm title="删除后该设备记录将从配对列表移除，确定删除？" onConfirm={() => handlePurge(d.id)}>
                      <Button size="small" theme="borderless" type="tertiary">删除</Button>
                    </Popconfirm>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 设备重命名弹窗 */}
      <Modal
        title="编辑设备名称"
        visible={!!renameTarget}
        onCancel={() => setRenameTarget(null)}
        onOk={handleRename}
        okText="保存"
        cancelText="取消"
        confirmLoading={renameSubmitting}
        width={420}
        centered
        style={{ maxWidth: '92vw' }}
      >
        <div className="py-1">
          <div className="text-xs text-semi-color-text-2 mb-1.5">设备名称（便于在配对列表识别，最多 24 个字符）</div>
          <Input
            value={renameValue}
            onChange={(v) => setRenameValue(v || '')}
            placeholder="例如 我的手机"
            maxLength={24}
            autoFocus
            onEnterPress={handleRename}
          />
        </div>
      </Modal>
    </div>
  );
};
