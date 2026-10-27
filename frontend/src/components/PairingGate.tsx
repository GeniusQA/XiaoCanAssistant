import React, { useEffect, useState } from 'react';
import { Modal, Input, Button, Banner, Toast } from '@douyinfe/semi-ui';
import { api, setDeviceJwt } from '../api';

/**
 * 多端设备配对门:
 * 远程设备 (非 PC 本机) 访问助手时, 所有 /api 请求需携带配对换发的设备 JWT;
 * 收到 401 (xc-pairing-required 事件) 时显示本配对界面, 输入 PC 端生成的配对码完成登录。
 */
export const PairingGate: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [code, setCode] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const handler = () => setVisible(true);
    window.addEventListener('xc-pairing-required', handler);
    return () => window.removeEventListener('xc-pairing-required', handler);
  }, []);

  const handleRedeem = async () => {
    if (!/^\d{6}$/.test(code.trim())) {
      Toast.warning('请输入 PC 端生成的 6 位配对码');
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.redeemPairing(code.trim(), deviceName.trim());
      if (res.ok && res.token) {
        setDeviceJwt(res.token);
        Toast.success(`设备「${res.device_name}」配对成功，有效期 ${res.expires_days} 天`);
        setVisible(false);
        setCode('');
        // 配对成功后整页刷新, 重新拉取全部数据
        window.location.reload();
      } else {
        Toast.error('配对失败，请确认配对码是否有效');
      }
    } catch (e: any) {
      Toast.error(e.response?.data?.detail || '配对失败，请确认配对码是否有效');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="设备配对"
      visible={visible}
      footer={null}
      width={460}
      centered
      maskClosable={false}
      closeOnEsc={false}
    >
      <Banner
        type="info"
        closeIcon={null}
        className="rounded-lg mb-3"
        description="本设备尚未与助手 PC 端配对。请在 PC 端「添加小蚕账号 → 设备协同」生成 6 位配对码，输入后即可同步使用全部账号、任务与配置。"
      />
      <PairingForm
        code={code} setCode={setCode}
        deviceName={deviceName} setDeviceName={setDeviceName}
        submitting={submitting} onSubmit={handleRedeem}
      />
    </Modal>
  );
};

const PairingForm: React.FC<{
  code: string; setCode: (v: string) => void;
  deviceName: string; setDeviceName: (v: string) => void;
  submitting: boolean; onSubmit: () => void;
}> = ({ code, setCode, deviceName, setDeviceName, submitting, onSubmit }) => (
  <div className="flex flex-col gap-3 py-1">
    <div>
      <div className="text-xs text-semi-color-text-2 mb-1.5">配对码 (6 位数字)</div>
      <Input
        value={code}
        onChange={(v) => setCode((v || '').replace(/\D/g, '').slice(0, 6))}
        placeholder="例如 382914"
        size="large"
        maxLength={6}
        autoFocus
        onKeyDown={(e) => { if (e.keyCode === 13) onSubmit(); }}
      />
    </div>
    <div>
      <div className="text-xs text-semi-color-text-2 mb-1.5">设备名称 (便于 PC 端识别与管理)</div>
      <Input
        value={deviceName}
        onChange={(v) => setDeviceName(v || '')}
        placeholder="例如 我的手机"
        onEnterPress={onSubmit}
      />
    </div>
    <Button theme="solid" type="primary" block loading={submitting} onClick={onSubmit}>
      配对并登录
    </Button>
    <div className="text-[11px] text-semi-color-text-2 leading-relaxed">
      配对后本设备将同步使用 PC 端已绑定的全部小蚕账号、任务与配置；小蚕凭据仅保存在 PC 端，不会下发到本设备。配对有效期为 30 天，可在 PC 端「设备协同」中随时吊销。
    </div>
  </div>
);
