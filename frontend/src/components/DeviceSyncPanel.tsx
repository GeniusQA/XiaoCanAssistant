import React, { useCallback, useEffect, useRef, useState } from 'react';
import jsQR from 'jsqr';
import { Button, Card, Empty, Input, Popconfirm, Space, Tag, Toast, Typography } from '@douyinfe/semi-ui';
import {
  IconDelete,
  IconDownload,
  IconExternalOpen,
  IconQrCode,
  IconRefresh,
  IconSmartphoneStroked,
  IconUnlink,
} from '@douyinfe/semi-icons';
import { api } from '../api';
import type { DevicePairStartResult, PairedDevice } from '../types';

const { Text } = Typography;

const inferDeviceName = (): string => {
  if (typeof navigator === 'undefined') return '协同设备';
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/i.test(ua)) return 'iPhone 设备';
  if (/Android/i.test(ua)) return 'Android 设备';
  return '桌面设备';
};

const isMobileClient = typeof navigator !== 'undefined' && (
  /iPhone|iPad|iPod|Android|Windows Phone|Mobile|mobile/i.test(navigator.userAgent)
  || (navigator.maxTouchPoints > 1 && /Macintosh/i.test(navigator.userAgent))
);

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

const toGrayArray = (source: ImageData): Uint8ClampedArray => {
  const { data } = source;
  const total = source.width * source.height;
  const gray = new Uint8ClampedArray(total);
  for (let i = 0, p = 0; p < total; i += 4, p += 1) {
    gray[p] = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) | 0;
  }
  return gray;
};

const grayscaleContrast = (source: ImageData): ImageData => {
  const { width, height } = source;
  const gray = toGrayArray(source);
  let min = 255;
  let max = 0;
  for (let p = 0; p < gray.length; p += 1) {
    if (gray[p] < min) min = gray[p];
    if (gray[p] > max) max = gray[p];
  }
  const range = Math.max(1, max - min);
  const out = new Uint8ClampedArray(gray.length * 4);
  for (let p = 0, i = 0; p < gray.length; p += 1, i += 4) {
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

const boxBlurGray = (gray: Uint8ClampedArray, width: number, height: number): Uint8ClampedArray => {
  const out = new Uint8ClampedArray(gray.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let sum = 0;
      let count = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        const yy = y + dy;
        if (yy < 0 || yy >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          const xx = x + dx;
          if (xx < 0 || xx >= width) continue;
          sum += gray[yy * width + xx];
          count += 1;
        }
      }
      out[y * width + x] = sum / count;
    }
  }
  return out;
};

const otsuThreshold = (gray: Uint8ClampedArray): number => {
  const histogram = new Array(256).fill(0);
  for (let p = 0; p < gray.length; p += 1) histogram[gray[p]] += 1;
  const total = gray.length;
  let sum = 0;
  for (let i = 0; i < 256; i += 1) sum += i * histogram[i];
  let sumBackground = 0;
  let weightBackground = 0;
  let best = 0;
  let threshold = 127;
  for (let t = 0; t < 256; t += 1) {
    weightBackground += histogram[t];
    if (weightBackground === 0) continue;
    const weightForeground = total - weightBackground;
    if (weightForeground === 0) break;
    sumBackground += t * histogram[t];
    const meanBackground = sumBackground / weightBackground;
    const meanForeground = (sum - sumBackground) / weightForeground;
    const between = weightBackground * weightForeground * (meanBackground - meanForeground) ** 2;
    if (between > best) {
      best = between;
      threshold = t;
    }
  }
  return threshold;
};

const binarizeGray = (
  gray: Uint8ClampedArray,
  width: number,
  height: number,
  threshold: number,
): ImageData => {
  const out = new Uint8ClampedArray(gray.length * 4);
  for (let p = 0, i = 0; p < gray.length; p += 1, i += 4) {
    const value = gray[p] > threshold ? 255 : 0;
    out[i] = value;
    out[i + 1] = value;
    out[i + 2] = value;
    out[i + 3] = 255;
  }
  return new ImageData(out, width, height);
};

const rotateImageData = (source: ImageData, degrees: number): ImageData | null => {
  const swap = degrees === 90 || degrees === 270;
  const canvas = document.createElement('canvas');
  canvas.width = swap ? source.height : source.width;
  canvas.height = swap ? source.width : source.height;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const sourceCanvas = document.createElement('canvas');
  sourceCanvas.width = source.width;
  sourceCanvas.height = source.height;
  const sourceContext = sourceCanvas.getContext('2d');
  if (!sourceContext) return null;
  sourceContext.putImageData(source, 0, 0);
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((degrees * Math.PI) / 180);
  context.drawImage(sourceCanvas, -source.width / 2, -source.height / 2);
  return context.getImageData(0, 0, canvas.width, canvas.height);
};

const decodeWithJsQr = (source: ImageData): string => {
  try {
    return jsQR(source.data, source.width, source.height, { inversionAttempts: 'attemptBoth' })?.data || '';
  } catch {
    return '';
  }
};

const decodeWithZxing = (
  zxing: typeof import('@zxing/library') | null,
  source: ImageData,
): string => {
  if (!zxing) return '';
  try {
    const {
      BinaryBitmap,
      DecodeHintType,
      HybridBinarizer,
      QRCodeReader,
      RGBLuminanceSource,
    } = zxing;
    const hints = new Map();
    hints.set(DecodeHintType.TRY_HARDER, true);
    const luminance = new RGBLuminanceSource(toGrayArray(source), source.width, source.height);
    const bitmap = new BinaryBitmap(new HybridBinarizer(luminance));
    return new QRCodeReader().decode(bitmap, hints).getText() || '';
  } catch {
    return '';
  }
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
    } catch { /* 回退到本地解码 */ }
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

  const gray = toGrayArray(original);
  const blurred = boxBlurGray(gray, canvas.width, canvas.height);
  const enhanced = grayscaleContrast(original);
  const binarized = binarizeGray(gray, canvas.width, canvas.height, otsuThreshold(gray));
  const blurredBinarized = binarizeGray(blurred, canvas.width, canvas.height, otsuThreshold(blurred));

  const primaryAttempts: ImageData[] = [original, enhanced, binarized, blurredBinarized];
  const allAttempts: ImageData[] = [
    ...primaryAttempts,
    invertImage(binarized),
    invertImage(blurredBinarized),
  ];

  const zxing = await import('@zxing/library').catch(() => null);

  for (const data of primaryAttempts) {
    const value = decodeWithZxing(zxing, data);
    if (value) return value;
  }
  for (const data of allAttempts) {
    const value = decodeWithJsQr(data);
    if (value) return value;
  }
  for (const data of [binarized, blurredBinarized]) {
    for (const degrees of [90, 180, 270]) {
      const rotated = rotateImageData(data, degrees);
      if (!rotated) continue;
      const value = decodeWithZxing(zxing, rotated) || decodeWithJsQr(rotated);
      if (value) return value;
    }
  }
  return '';
};

const collectLocalStateSnapshot = (): Record<string, any> => {
  const snapshot: Record<string, any> = {};
  const localOnlyKeys = new Set([
    'xiaocan_device_token',
    'xiaocan_device_id',
    'xiaocan_device_name',
    'xiaocan_phone_base_url',
  ]);
  Object.keys(localStorage).forEach((key) => {
    if (!key.startsWith('xiaocan_') || localOnlyKeys.has(key)) return;
    const raw = localStorage.getItem(key);
    if (raw === null) return;
    try { snapshot[key] = JSON.parse(raw); } catch { snapshot[key] = raw; }
  });
  return snapshot;
};

export const DeviceSyncPanel: React.FC = () => {
  const [pairing, setPairing] = useState(false);
  const [phoneBaseUrl, setPhoneBaseUrl] = useState(() => {
    try {
      return localStorage.getItem('xiaocan_phone_base_url') || 'http://127.0.0.1:39691';
    } catch {
      return 'http://127.0.0.1:39691';
    }
  });
  const [localDeviceName, setLocalDeviceName] = useState(() => {
    try {
      return localStorage.getItem('xiaocan_device_name') || inferDeviceName();
    } catch {
      return inferDeviceName();
    }
  });
  const [pairInfo, setPairInfo] = useState<DevicePairStartResult | null>(null);
  const [pairStatus, setPairStatus] = useState('');
  const [pairExpiresAt, setPairExpiresAt] = useState<number>(0);
  const [pairExpired, setPairExpired] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState('');
  const [decodingFile, setDecodingFile] = useState(false);
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
    setPairInfo(null);
    setPairExpiresAt(0);
    setPairExpired(false);
    setPairStatus('正在生成配对二维码...');
    try {
      const normalizedPhoneBase = (phoneBaseUrl || '').trim().replace(/\/+$/, '');
      if (!/^https?:\/\//i.test(normalizedPhoneBase)) {
        throw new Error('手机端服务地址需以 http:// 或 https:// 开头');
      }
      const normalizedDeviceName = (localDeviceName || '').trim().slice(0, 40) || inferDeviceName();
      try {
        localStorage.setItem('xiaocan_phone_base_url', normalizedPhoneBase);
        localStorage.setItem('xiaocan_device_name', normalizedDeviceName);
      } catch {
        // ignore
      }
      const res = await api.startDevicePair(collectLocalStateSnapshot(), normalizedPhoneBase, normalizedDeviceName);
      if (!res.ok) throw new Error('生成配对二维码失败');
      setPairInfo(res);
      setPairExpiresAt(Date.now() + Number(res.expires_in || 300) * 1000);
      setPairExpired(false);
      setNowTick(Date.now());
      setPairStatus('状态: 等待中');
      Toast.success(`二维码已生成，${res.expires_in} 秒内有效`);
    } catch (e: any) {
      setPairStatus('');
      Toast.error(`生成失败: ${e?.response?.data?.detail || e.message || '未知错误'}`);
    } finally {
      setPairing(false);
    }
  };

  const pollPairStatus = async () => {
    if (!pairInfo || pairExpired) return;
    try {
      const res = await api.getDevicePairStatus(pairInfo.ticket);
      if (res.status === 'used') {
        setPairStatus('状态: 已授权并同步');
        setPairInfo(null);
        void loadPairedDevices(true);
        return;
      }
      if (res.status === 'expired' || res.status === 'not_found') {
        setPairStatus('状态: 已过期');
        setPairExpired(true);
        return;
      }
      setPairStatus(res.status === 'claimed' ? '状态: 等待扫码端导入' : '状态: 等待中');
    } catch { /* 轮询失败不打扰用户 */ }
  };

  useEffect(() => {
    void loadPairedDevices(true);
  }, []);

  useEffect(() => {
    if (!pairInfo) return;
    const statusTimer = window.setInterval(pollPairStatus, 2000);
    const tickTimer = window.setInterval(() => {
      const now = Date.now();
      setNowTick(now);
      if (pairExpiresAt > 0 && now >= pairExpiresAt) {
        setPairExpired(true);
        setPairStatus('状态: 已过期');
      }
    }, 1000);
    return () => {
      window.clearInterval(statusTimer);
      window.clearInterval(tickTimer);
    };
  }, [pairInfo, pairExpiresAt, pairExpired]);

  const handleRevokeDevice = async (deviceId: string, deviceName: string) => {
    try {
      const res = await api.revokePairedDevice(deviceId);
      Toast.error(res.message || `${deviceName}已取消设备协同授权`);
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
      setScanError('当前浏览器不允许调用相机（移动端需 HTTPS 或 localhost），请改用下方“相册选图”。');
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
      setScanError(`无法打开相机: ${e?.message || '请检查相机权限'}。可改用下方“相册选图”。`);
    }
  };

  const handleScanFile = async (file?: File) => {
    if (!file) return;
    setScanError('');
    setDecodingFile(true);
    try {
      const decoded = await decodeQrFromFile(file);
      if (!decoded) throw new Error('未在图片中识别到二维码，请靠近二维码重拍或改用截图');
      handleScannedUrl(decoded);
    } catch (e: any) {
      setScanError(`扫码失败: ${e?.message || '未知错误'}`);
    } finally {
      setDecodingFile(false);
      if (scanFileRef.current) scanFileRef.current.value = '';
    }
  };

  const handleSaveQr = () => {
    if (!pairInfo || pairExpired) return;
    const link = document.createElement('a');
    link.href = pairInfo.qr_image;
    link.download = `设备协同二维码-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    Toast.success('二维码已保存');
  };

  useEffect(() => stopScan, [stopScan]);

  const remainingSeconds = pairInfo && pairExpiresAt > 0
    ? Math.max(0, Math.ceil((pairExpiresAt - nowTick) / 1000))
    : 0;
  const remainingText = `${String(Math.floor(remainingSeconds / 60)).padStart(2, '0')}:${String(remainingSeconds % 60).padStart(2, '0')}`;

  return (
    <div className="space-y-4">
      <div className="text-xs text-semi-color-text-2 leading-relaxed space-y-1">
        <div>任一部署端生成短时二维码，另一端在同一局域网扫码即可一次性同步账号与配置；完成后两端独立运行，不再持续互相同步。</div>
        <div>二维码仅包含随机票据，不含账号 Token；默认 5 分钟有效且只能使用一次。</div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 items-center sm:items-center">
        <div className="shrink-0 flex flex-col items-center gap-2">
          <div className="relative w-[220px] h-[220px] rounded-xl border border-semi-color-border bg-white flex items-center justify-center overflow-hidden">
            {pairInfo ? (
              <>
                <img
                  src={pairInfo.qr_image}
                  alt="设备协同二维码"
                  className={`w-full h-full object-contain ${pairExpired ? 'blur-[6px] opacity-25' : ''}`}
                />
                {pairExpired && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/80 text-center px-4">
                    <IconQrCode size="extra-large" className="text-semi-color-text-3 mb-2" />
                    <div className="text-sm font-semibold text-semi-color-text-1">二维码已过期</div>
                    <div className="text-[11px] text-semi-color-text-2 mt-1">请点击「生成配对二维码」重新生成</div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-semi-color-text-2 text-xs px-4">
                <IconQrCode size="extra-large" className="mb-2" />
                <div>尚未生成二维码</div>
              </div>
            )}
          </div>
          {pairInfo && (
            <div className="flex items-center gap-2">
              <Tag color={pairExpired ? 'red' : 'blue'} size="small">
                {pairExpired ? '已过期' : `剩余 ${remainingText}`}
              </Tag>
              <Button
                size="small"
                theme="light"
                icon={<IconDownload />}
                disabled={pairExpired}
                onClick={handleSaveQr}
              >
                保存二维码
              </Button>
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0 space-y-2">
          <div>
            <div className="text-xs text-semi-color-text-2 mb-1">本机设备名称</div>
            <Input value={localDeviceName} onChange={(v) => setLocalDeviceName(v)} placeholder="当前设备" />
          </div>
          <div>
            <div className="text-xs text-semi-color-text-2 mb-1">扫码端服务地址（同步目标）</div>
            <Input
              value={phoneBaseUrl}
              onChange={(v) => setPhoneBaseUrl(v)}
              placeholder="http://127.0.0.1:39691"
            />
          </div>
          <Button theme="solid" type="primary" icon={<IconQrCode />} loading={pairing} onClick={handleStartPair}>
            生成配对二维码
          </Button>
          <div className={`text-xs break-all ${pairExpired ? 'text-semi-color-danger' : 'text-semi-color-text-2'}`}>
            {pairStatus || '二维码生成后请在 5 分钟内由另一端扫码确认。'}
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

      {isMobileClient && (
        <div className="p-4 rounded-xl bg-semi-color-fill-0 border border-semi-color-border text-center space-y-3">
          <IconSmartphoneStroked className="text-semi-color-primary" size="extra-large" />
          <div>
            <Text strong>扫描对端二维码</Text>
            <p className="text-xs text-semi-color-text-2 mt-1">移动端扫码加入；识别后进入一次性确认与同步页面。</p>
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
              loading={decodingFile}
              onClick={() => scanFileRef.current?.click()}
            >
              {decodingFile ? '正在识别二维码...' : '相册选图'}
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
            浏览器仅在 HTTPS 或 localhost 下允许网页直接调用相机；局域网 HTTP 可使用相册选图。
          </p>
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
                      content="注销后将取消该设备协同授权；一次性同步完成的本地数据不会被删除。"
                      onConfirm={() => void handleRevokeDevice(device.id, device.name)}
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
