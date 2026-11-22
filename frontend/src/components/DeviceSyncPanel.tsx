import React, { useCallback, useEffect, useRef, useState } from 'react';
import jsQR from 'jsqr';
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

const MAX_DECODE_SIZE = 1600;

const loadImageElement = (file: File): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('图片读取失败，可能是 HEIC 等浏览器不支持的格式，请改用截图或 JPG/PNG'));
    };
    image.src = url;
  });

const drawSourceToCanvas = (
  source: CanvasImageSource,
  width: number,
  height: number,
): { canvas: HTMLCanvasElement; context: CanvasRenderingContext2D } | null => {
  if (!width || !height) return null;
  const scale = Math.min(1, MAX_DECODE_SIZE / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  return { canvas, context };
};

const grayscaleContrast = (source: ImageData): ImageData => {
  const { data, width, height } = source;
  const total = width * height;
  const gray = new Uint8ClampedArray(total);
  let min = 255;
  let max = 0;
  for (let i = 0, p = 0; p < total; i += 4, p += 1) {
    const value = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) | 0;
    gray[p] = value;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  const range = Math.max(1, max - min);
  const out = new Uint8ClampedArray(total * 4);
  for (let p = 0, i = 0; p < total; p += 1, i += 4) {
    const value = ((gray[p] - min) * 255 / range) | 0;
    out[i] = value;
    out[i + 1] = value;
    out[i + 2] = value;
    out[i + 3] = 255;
  }
  return new ImageData(out, width, height);
};

const invertImage = (source: ImageData): ImageData => {
  const { data, width, height } = source;
  const out = new Uint8ClampedArray(data.length);
  for (let i = 0; i < data.length; i += 4) {
    out[i] = 255 - data[i];
    out[i + 1] = 255 - data[i + 1];
    out[i + 2] = 255 - data[i + 2];
    out[i + 3] = data[i + 3];
  }
  return new ImageData(out, width, height);
};

const decodeQrFromFile = async (file: File): Promise<string> => {
  const BarcodeDetectorCtor = (window as any).BarcodeDetector;
  if (typeof BarcodeDetectorCtor !== 'undefined' && typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file);
      const detector = new BarcodeDetectorCtor({ formats: ['qr_code'] });
      const codes = await detector.detect(bitmap);
      bitmap.close?.();
      if (codes.length && codes[0].rawValue) return codes[0].rawValue;
    } catch { /* 回退到 jsQR */ }
  }

  const image = await loadImageElement(file);
  const built = drawSourceToCanvas(
    image,
    image.naturalWidth || image.width,
    image.naturalHeight || image.height,
  );
  if (!built) throw new Error('当前浏览器不支持图片解析');
  const { canvas, context } = built;
  const original = context.getImageData(0, 0, canvas.width, canvas.height);

  const enhanced = grayscaleContrast(original);
  const attempts: ImageData[] = [original, enhanced, invertImage(enhanced)];
  for (const data of attempts) {
    const code = jsQR(data.data, data.width, data.height, { inversionAttempts: 'attemptBoth' });
    if (code?.data) return code.data;
  }
  return '';
};

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
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState('');
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const scanFileRef = useRef<HTMLInputElement | null>(null);

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

  const stopScan = useCallback(() => {
    if (rafRef.current !== null) {
      window.cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setScanning(false);
  }, []);

  const handleScannedUrl = useCallback((value: string) => {
    const raw = String(value || '').trim();
    let target = raw;
    try {
      const url = new URL(raw, window.location.href);
      if (!url.searchParams.get('ticket')) {
        throw new Error('二维码中没有配对票据');
      }
      target = url.toString();
      window.location.assign(target);
    } catch {
      setScanError('识别到的二维码不是有效的设备协同二维码，请扫描 PC 端生成的二维码');
    }
  }, []);

  const decodeQrFromCanvas = (canvas: HTMLCanvasElement): string => {
    const width = canvas.width;
    const height = canvas.height;
    if (!width || !height) return '';
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) return '';
    const image = context.getImageData(0, 0, width, height);
    return jsQR(image.data, width, height, { inversionAttempts: 'attemptBoth' })?.data || '';
  };

  const scanFrame = () => {
    const video = videoRef.current;
    if (!video || !streamRef.current) return;
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (context) {
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const decoded = decodeQrFromCanvas(canvas);
        if (decoded) {
          stopScan();
          handleScannedUrl(decoded);
          return;
        }
      }
    }
    rafRef.current = window.requestAnimationFrame(scanFrame);
  };

  const startScan = async () => {
    setScanError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setScanError('当前浏览器不允许调用相机（移动端需 HTTPS 或 localhost），请改用下方“系统相机/相册选图”。');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      streamRef.current = stream;
      setScanning(true);
      window.setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play();
          scanFrame();
        }
      }, 0);
    } catch (e: any) {
      setScanError(`无法打开相机: ${e?.message || '请检查相机权限'}。可改用下方“系统相机/相册选图”。`);
    }
  };

  const handleScanFile = async (file?: File) => {
    if (!file) return;
    setScanError('');
    try {
      const decoded = await decodeQrFromFile(file);
      if (!decoded) throw new Error('未在图片中识别到二维码，请靠近二维码重拍或改用截图');
      handleScannedUrl(decoded);
    } catch (e: any) {
      setScanError(`扫码失败: ${e?.message || '未知错误'}`);
    } finally {
      if (scanFileRef.current) scanFileRef.current.value = '';
    }
  };

  useEffect(() => stopScan, [stopScan]);

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
            <p className="text-xs text-semi-color-text-2 mt-1">直接调用手机相机扫描 PC 端二维码，识别后自动进入确认与同步页面。</p>
          </div>

          {!scanning ? (
            <Button theme="solid" type="primary" icon={<IconQrCode />} onClick={() => void startScan()}>
              打开相机扫码
            </Button>
          ) : (
            <div className="space-y-2">
              <video
                ref={videoRef}
                playsInline
                muted
                autoPlay
                className="w-full max-h-[320px] rounded-lg bg-black object-cover"
              />
              <Button size="small" theme="light" onClick={stopScan}>关闭相机</Button>
            </div>
          )}

          <div>
            <Button
              size="small"
              theme="light"
              onClick={() => scanFileRef.current?.click()}
            >
              系统相机 / 相册选图
            </Button>
            <input
              ref={scanFileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => void handleScanFile(e.target.files?.[0])}
            />
          </div>

          {scanError && (
            <div className="text-xs text-semi-color-danger leading-relaxed bg-semi-color-danger-light-0 rounded-md p-2 text-left">
              {scanError}
            </div>
          )}
          <p className="text-[11px] text-semi-color-text-3 leading-relaxed">
            手机浏览器仅在 HTTPS 或 localhost 下允许网页直接调用相机；局域网 HTTP 可使用系统相机/相册选图。
          </p>
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
