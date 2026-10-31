import axios from 'axios';
import { Toast } from '@douyinfe/semi-ui';
import type { Account, AccountDetailData, UserCardItem, TaskItem, StoreItem, StoreAppointment, NameMonitorPayload, JobLog, UserInfo, Order, OrderStats, DashboardChartData, BatchDailyResult, SystemSettings, NotifyTestResult, LocationSearchResult, ClawBotStatus, ClawBotQrResponse, ClawBotPollResponse, ClawBotActivationResponse, AccountNotifyConfig, AccountNotifyResponse, XiaoCanMessagesResponse, MeituanAccount, MeituanAuthStartResponse, MeituanAuthPollResponse, MeituanSlot, MediaVipRecord } from '../types';

export const API_BASE = import.meta.env.VITE_API_BASE || '/api';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

// ---------------- 多端设备协同认证 ----------------
// 移动端等远程设备通过配对码换取设备 JWT, 之后所有请求自动携带
export const DEVICE_JWT_KEY = 'xc_device_jwt';

export const getDeviceJwt = (): string => {
  try {
    return localStorage.getItem(DEVICE_JWT_KEY) || '';
  } catch {
    return '';
  }
};

export const setDeviceJwt = (token: string) => {
  try {
    if (token) localStorage.setItem(DEVICE_JWT_KEY, token);
    else localStorage.removeItem(DEVICE_JWT_KEY);
  } catch { /* ignore */ }
};

client.interceptors.request.use((config) => {
  const jwt = getDeviceJwt();
  if (jwt) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${jwt}`;
  }
  return config;
});

/**
 * 设备凭证失效时清理本机残留数据:
 * 吊销/失效后, 本机浏览器缓存中的账号列表、抢单位置等副本不应继续留存, 统一清除。
 * (重配对后账号由服务端重新下发, 位置从服务端同步拉回, 无数据损失)
 */
const clearLocalDeviceData = () => {
  try {
    localStorage.removeItem(DEVICE_JWT_KEY);
    localStorage.removeItem('xiaocan_cached_accounts');
    localStorage.removeItem('xiaocan_current_account_key');
    localStorage.removeItem('xiaocan_active_location');
    localStorage.removeItem('xiaocan_location_history');
  } catch { /* ignore */ }
};

// 401 提示去重时间戳 (并发请求同时失效时只提示一次)
let pairingNotifiedAt = 0;

// 全局响应拦截器：统一网络异常与安全兜底
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) {
      return Promise.reject(error);
    }
    // 设备凭证失效 (被吊销/过期) → 清理本机缓存并触发全局配对门 (携带后端原因供弹窗展示)
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      clearLocalDeviceData();
      // 首页会并发多个接口, 全部 401 时不能重复弹窗/弹 Toast: 3 秒内只触发一次
      const now = Date.now();
      if (now - pairingNotifiedAt > 3000) {
        pairingNotifiedAt = now;
        window.dispatchEvent(new CustomEvent('xc-pairing-required', {
          detail: error.response?.data?.detail || '设备未配对或凭证已失效，请在 PC 端生成配对码重新登录'
        }));
      }
    }
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      Toast.error('请求超时，请检查后端服务是否正常响应');
    } else if (error.message === 'Network Error') {
      Toast.error('网络连接失败，请确认后端服务已在 8690 端口启动');
    }
    return Promise.reject(error);
  }
);

// 官方WAF熔断提示全局去重: 10 秒内相同文案只弹一次 (无论多少接口/页面同时触发, 只展示一条)
let lastWafToast = { text: '', at: 0 };
export const warnOnce = (content: string, duration = 8) => {
  const now = Date.now();
  if (content === lastWafToast.text && now - lastWafToast.at < 10000) return;
  lastWafToast = { text: content, at: now };
  Toast.warning({ content, duration });
};

// 在途 GET 请求复用池：避免同一时间点多个并发相同 GET 请求重复打到后端
const inFlightGetRequests = new Map<string, Promise<any>>();

const getQueryKey = (url: string, params?: any): string => {
  if (!params) return url;
  try {
    const searchParams = new URLSearchParams();
    const sortedKeys = Object.keys(params).sort();
    for (const key of sortedKeys) {
      const val = params[key];
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    }
    const qs = searchParams.toString();
    return qs ? `${url}?${qs}` : url;
  } catch {
    return `${url}?${JSON.stringify(params)}`;
  }
};

const originalGet = client.get.bind(client);

(client as any).get = function (url: string, config?: any): Promise<any> {
  // 如果调用方显式提供了 AbortSignal，不进行在途共享，保证 AbortSignal 精确控制
  if (config?.signal) {
    return originalGet(url, config);
  }
  const key = getQueryKey(url, config?.params);
  const existing = inFlightGetRequests.get(key);
  if (existing) {
    return existing;
  }
  const promise = originalGet(url, config)
    .finally(() => {
      inFlightGetRequests.delete(key);
    });
  inFlightGetRequests.set(key, promise);
  return promise;
};

export const api = {
  // 账号管理
  getAccounts: () => client.get<{ ok: boolean; accounts: Account[]; total: number }>('/accounts').then(r => r.data),
  createAccount: (data: Partial<Account>) => client.post<{ ok: boolean; account: Account }>('/accounts', data).then(r => r.data),
  updateAccount: (key: string, data: Partial<Account>) => client.post<{ ok: boolean; account: Account; message: string }>(`/accounts/${key}/profile`, data).then(r => r.data),
  syncAccount: (key: string) => client.post<{ ok: boolean; account: Account; message: string; sync_error?: string }>(`/accounts/${key}/sync`).then(r => r.data),
  getAccountDetail: (key: string) => client.get<AccountDetailData & { sync_errors?: string[] }>(`/accounts/${key}/detail`).then(r => r.data),
  getAccountCards: (key: string, status = 0) => client.get<{ ok: boolean; cards: UserCardItem[]; status: number; error?: string }>(`/accounts/${key}/cards`, { params: { status } }).then(r => r.data),
  deleteAccount: (key: string) => client.delete<{ ok: boolean; message: string }>(`/accounts/${key}`).then(r => r.data),
  getAccountNotifyConfig: (key: string) => client.get<AccountNotifyResponse>(`/accounts/${key}/notify-config`).then(r => r.data),
  saveAccountNotifyConfig: (key: string, notify_mode: string, notify_config: AccountNotifyConfig) => client.post<{ ok: boolean; message: string }>(`/accounts/${key}/notify-config`, { notify_mode, notify_config }).then(r => r.data),
  testAccountNotify: (key: string, notify_mode: string, notify_config: AccountNotifyConfig) => client.post<{ ok: boolean; message: string; channel?: string }>(`/accounts/${key}/test-notify`, { notify_mode, notify_config }).then(r => r.data),
  
  // 账号解析与嗅探接入
  parseToken: (rawText: string) => client.post<{ ok: boolean; token?: string; silk_id?: string; is_valid: boolean; message: string; exp_date?: string; city_code?: number; nickname?: string; client_mode?: string }>('/accounts/parse-token', { raw_text: rawText }).then(r => r.data),
  verifyToken: (token: string, cityCode?: number) => client.post<{ ok: boolean; valid: boolean; message: string }>('/accounts/verify-token', { token, city_code: cityCode }).then(r => r.data),
  startProxyCapture: (port?: number) => client.post<{ ok: boolean; message: string; status: any }>('/accounts/proxy-capture/start', { port }).then(r => r.data),
  stopProxyCapture: () => client.post<{ ok: boolean; message: string; status: any }>('/accounts/proxy-capture/stop').then(r => r.data),
  getProxyCaptureStatus: () => client.get<{ ok: boolean; status: any }>('/accounts/proxy-capture/status').then(r => r.data),

  // 电脑微信无感直连 (免配置·首选)
  scanWechatAccount: () => client.post<{ ok: boolean; account?: Account; message: string }>('/accounts/wechat-scan').then(r => r.data),
  startWechatListener: (timeout?: number) => client.post<{ ok: boolean; message: string; status: any }>('/accounts/wechat-listener/start', { timeout }).then(r => r.data),
  stopWechatListener: () => client.post<{ ok: boolean; message: string; status: any }>('/accounts/wechat-listener/stop').then(r => r.data),
  getWechatListenerStatus: () => client.get<{ ok: boolean; status: any }>('/accounts/wechat-listener/status').then(r => r.data),

  // 历史兼容
  startWinCapture: (port?: number, timeout?: number) => client.post<{ ok: boolean; message: string; status: any }>('/accounts/win_capture/start', { port, timeout }).then(r => r.data),
  stopWinCapture: () => client.post<{ ok: boolean; message: string; status: any }>('/accounts/win_capture/stop').then(r => r.data),
  getWinCaptureStatus: () => client.get<{ ok: boolean; status: any }>('/accounts/win_capture/status').then(r => r.data),
  installCaCert: () => client.post<{ ok: boolean; message: string; ca_installed?: boolean }>('/accounts/win_capture/install_ca').then(r => r.data),


  // 任务自动化
  getTasks: (accountKey: string) => client.get<{ ok: boolean; tasks: TaskItem[] }>(`/tasks?account_key=${accountKey}`).then(r => r.data),
  toggleTask: (data: { account_key: string; task_id: string; enabled: boolean; cron_time?: string; params?: Record<string, any> }) => client.post<{ ok: boolean; message: string }>('/tasks/toggle', data).then(r => r.data),
  runTaskNow: (accountKey: string, taskId: string) => client.post<{ ok: boolean; job_id?: string; output: string }>('/tasks/run', { account_key: accountKey, task_id: taskId }, { timeout: 60000 }).then(r => r.data),
  batchRunDaily: (accountKey?: string) => client.post<BatchDailyResult>('/tasks/batch-run-daily', { account_key: accountKey }, { timeout: 180000 }).then(r => r.data),
  updateNameMonitor: (id: number, data: Record<string, any>) =>
    client.put<{ ok: boolean; appointment: any; message: string }>(`/store/name-monitor/${id}`, data, { timeout: 30000 }).then(r => r.data),
  notifyHealthcheck: (force = false) =>
    client.post<{ ok: boolean; cached?: boolean; enabled_count: number; ok_count: number; failed_count: number; results: { channel: string; label: string; ok: boolean; message: string }[] }>('/settings/notify-healthcheck', { force }, { timeout: 60000 }).then(r => r.data),
  dailyInspectionNotify: (accountKey?: string) =>
    client.post<{ ok: boolean; title: string; content: string; sent_count: number; skipped_count: number; results: { channel: string; name: string; ok: boolean; skipped: boolean; message: string }[] }>('/tasks/daily-inspection-notify', { account_key: accountKey }, { timeout: 60000 }).then(r => r.data),
  getCurrentAccountKey: () =>
    client.get<{ ok: boolean; current_account_key: string }>('/settings/current-account', { timeout: 15000 }).then(r => r.data),
  saveCurrentAccountKey: (key: string) =>
    client.post<{ ok: boolean }>('/settings/current-account', { current_account_key: key }, { timeout: 15000 }).then(r => r.data),
  getAppLocation: () =>
    client.get<{ ok: boolean; active_location: any; location_history: any[] }>('/settings/app-location', { timeout: 15000 }).then(r => r.data),
  saveAppLocation: (data: { active_location?: any; location_history?: any[] }) =>
    client.post<{ ok: boolean }>('/settings/app-location', data, { timeout: 15000 }).then(r => r.data),
  createPairing: () =>
    client.post<{ ok: boolean; code: string; expires_in: number; lan_address: string }>('/pairing/create', {}, { timeout: 15000 }).then(r => r.data),
  redeemPairing: (code: string, deviceName: string) =>
    client.post<{ ok: boolean; token: string; device_id: number; device_name: string; expires_days: number }>('/pairing/redeem', { code, device_name: deviceName }, { timeout: 15000 }).then(r => r.data),
  getPairingDevices: () =>
    client.get<{ ok: boolean; devices: { id: number; device_name: string; created_at: string; last_seen: string; ip?: string; expires_at?: string; revoked: number }[] }>('/pairing/devices', { timeout: 15000 }).then(r => r.data),
  revokePairingDevice: (id: number) =>
    client.delete<{ ok: boolean; message: string }>(`/pairing/devices/${id}`, { timeout: 15000 }).then(r => r.data),
  getPairingCodeStatus: (code: string) =>
    client.get<{ ok: boolean; exists: boolean; used: boolean; expired: boolean }>('/pairing/code-status', { params: { code }, timeout: 15000 }).then(r => r.data),
  renamePairingDevice: (id: number, deviceName: string) =>
    client.put<{ ok: boolean; message: string }>(`/pairing/devices/${id}`, { device_name: deviceName }, { timeout: 15000 }).then(r => r.data),
  purgePairingDevice: (id: number) =>
    client.delete<{ ok: boolean; message: string }>(`/pairing/devices/${id}/purge`, { timeout: 15000 }).then(r => r.data),
  getFlashSaleGoods: (accountKey?: string) =>
    client.get<{ ok: boolean; items: { exchange_id: number; goods_name: string; community_silk: number; left: number; group: string; round_ts: number }[]; rounds?: string[]; round_ts_list?: number[]; error?: string }>(
      '/tasks/flash-sale-goods', { params: { account_key: accountKey }, timeout: 30000 }
    ).then(r => r.data),

  // 美团官方账号与神券领取
  getMeituanAccounts: () => client.get<{ ok: boolean; accounts: MeituanAccount[] }>('/meituan/accounts').then(r => r.data),
  saveMeituanAccount: (data: Partial<MeituanAccount>) => client.post<{ ok: boolean; account: MeituanAccount; message: string }>('/meituan/accounts', data).then(r => r.data),
  deleteMeituanAccount: (key: string) => client.delete<{ ok: boolean; message: string }>(`/meituan/accounts/${key}`).then(r => r.data),
  startMeituanAuth: (accountKey?: string, customNickname?: string) => client.post<MeituanAuthStartResponse>('/meituan/auth/start', { ...(accountKey ? { account_key: accountKey } : {}), ...(customNickname ? { custom_nickname: customNickname } : {}) }).then(r => r.data),
  updateMeituanNickname: (accountKey: string, nickname: string) => client.post<{ ok: boolean; message: string; nickname?: string }>(`/accounts/${accountKey}/meituan-nickname`, { nickname }).then(r => r.data),
  clearAllMeituan: () => client.post<{ ok: boolean; message: string }>('/meituan/clear-all').then(r => r.data),
  unbindMeituan: (accountKey: string) => client.post<{ ok: boolean; message: string }>(`/accounts/${accountKey}/unbind-meituan`).then(r => r.data),
  bindExistingMeituan: (accountKey: string, meituanKey: string) => client.post<{ ok: boolean; message: string }>(`/accounts/${accountKey}/bind-meituan`, { meituan_key: meituanKey }).then(r => r.data),
  getMeituanSlots: (accountKey: string) => client.get<{ ok: boolean; slots: MeituanSlot[]; cap: number }>(`/accounts/${accountKey}/meituan-slots`).then(r => r.data),
  switchMeituanSlot: (accountKey: string, slotId: number) => client.post<{ ok: boolean; message: string; meituan_nickname: string }>(`/accounts/${accountKey}/meituan-slots/${slotId}/switch`).then(r => r.data),
  deleteMeituanSlot: (accountKey: string, slotId: number) => client.delete<{ ok: boolean; message: string }>(`/accounts/${accountKey}/meituan-slots/${slotId}`).then(r => r.data),
  pollMeituanAuth: (sessionId: string) => client.get<MeituanAuthPollResponse>('/meituan/auth/poll', { params: { session_id: sessionId } }).then(r => r.data),
  cancelMeituanAuth: (sessionId: string) => client.post<{ ok: boolean; message: string }>('/meituan/auth/cancel', { session_id: sessionId }).then(r => r.data),
  runMeituanClaim: (data?: { account_key?: string; force?: boolean }) => client.post<{ ok: boolean; result?: any; results?: any[]; message?: string }>('/meituan/claim/run', data, { timeout: 150000 }).then(r => r.data),

  // 店铺与附近霸王餐 (支持经纬度、平台、搜索过滤、触底流式分页)
  getStores: (params?: { city_code?: number; longitude?: string; latitude?: string; account_key?: string; keyword?: string; platform?: string; condition?: string; rebate_type?: string; sort_by?: string; limit?: number; offset?: number; page_pv_id?: string }, signal?: AbortSignal) => 
    client.get<{ ok: boolean; stores: StoreItem[]; total: number; raw_total?: number; source?: string; has_more?: boolean; next_offset?: number; page_pv_id?: string; keyword?: string; error?: string }>('/store/list', { params, signal }).then(r => r.data),
  scanDualRebateStores: (params?: { city_code?: number; longitude?: string; latitude?: string; account_key?: string; platform?: string; keyword?: string; max_stores?: number }) =>
    client.get<{
      ok: boolean;
      total_scanned_promotions: number;
      total_scanned_stores: number;
      dual_rebate_count: number;
      returned_count?: number;
      max_stores?: number;
      stores: StoreItem[];
      message?: string;
      error?: string;
    }>('/store/dual-rebate-scan', { params, timeout: 120000 }).then(r => r.data),
  grabStoreNow: (data: { account_key: string; store_id?: string; store_name?: string; store_icon?: string; promotion_id: string; platform?: string; order_money?: number; rebate_price?: number; rebate_desc?: string; rebate_type?: string; advance?: boolean; redpack_id?: string; redpack_name?: string; redpack_mode?: number }) =>
    client.post<{ ok: boolean; order_id?: number; can_monitor?: boolean; message: string }>('/store/grab-now', data).then(r => r.data),
  createAppointment: (data: Partial<StoreAppointment>) => client.post<{ ok: boolean; appointment_id: number; message: string }>('/store/appoint', data).then(r => r.data),
  createNameMonitor: (data: NameMonitorPayload) =>
    client.post<{ ok: boolean; appointment_id: number; message: string }>('/store/name-monitor', data).then(r => r.data),
  getAppointments: (accountKey?: string) => client.get<{ ok: boolean; appointments: StoreAppointment[]; total: number }>('/store/appointments', { params: { account_key: accountKey } }).then(r => r.data),
  stopAppointment: (id: number) => client.post<{ ok: boolean; message: string }>(`/store/appointments/${id}/stop`).then(r => r.data),
  cancelAppointment: (id: number) => client.delete<{ ok: boolean; message: string }>(`/store/appointments/${id}`).then(r => r.data),

  // 设备定位与逆地理编码
  searchLocation: (keyword: string) =>
    client.get<LocationSearchResult>('/location/search', { params: { keyword } }).then(r => r.data),
  resolveLocation: (latitude: number, longitude: number) =>
    client.get<{ ok: boolean; city_code: number; city_name: string; locality?: string; province?: string; address_name: string; latitude: string; longitude: string; source?: string; accuracy?: string }>('/location/resolve', { params: { latitude, longitude } }).then(r => r.data),
  getIpLocation: () =>
    client.get<{ ok: boolean; city_code: number; city_name: string; address_name: string; latitude: string; longitude: string; is_ip?: boolean }>('/location/ip').then(r => r.data),

  // 阿里云 NTP 高精度授时校准
  getTime: (force?: boolean) =>
    client.get<{ ok: boolean; timestamp: number; beijing_time: string; server: string; synced: boolean; offset: number }>('/time', { params: { force } }).then(r => r.data),

  // 霸王餐订单管理
  getOrders: (params?: { account_key?: string; status?: string; platform?: string; keyword?: string; limit?: number; offset?: number }) =>
    client.get<{ ok: boolean; orders: Order[]; total: number; sync_error?: string; error?: string }>('/orders', { params }).then(r => r.data),
  getOrderStats: (accountKey?: string) => 
    client.get<{ ok: boolean; stats: OrderStats }>(`/orders/stats`, { params: { account_key: accountKey } }).then(r => r.data),
  getDashboardChartData: (accountKey?: string) =>
    client.get<{ ok: boolean; data: DashboardChartData }>('/dashboard/chart-data', { params: { account_key: accountKey } }).then(r => r.data),
  getMessages: (params?: { account_key?: string; channel_id?: number; page?: number; page_size?: number }) =>
    client.get<XiaoCanMessagesResponse>('/messages', { params }).then(r => r.data),
  markAllMessagesRead: (account_key: string) =>
    client.post<{ ok: boolean; message: string }>('/messages/read-all', { account_key }).then(r => r.data),
  createOrder: (data: Partial<Order>) => 
    client.post<{ ok: boolean; order: Order; message: string }>('/orders', data).then(r => r.data),
  updateOrder: (id: number, data: Partial<Order>) => 
    client.put<{ ok: boolean; order: Order; message: string }>(`/orders/${id}`, data).then(r => r.data),
  submitPlatformOrderId: (id: number, platformOrderId: string, receiptImg?: string, forceModify = false) =>
    client.post<{ ok: boolean; order: Order; message: string; error?: string }>(`/orders/${id}/submit-platform-id`, { platform_order_id: platformOrderId, receipt_img: receiptImg, force_modify: forceModify }).then(r => r.data),
  cancelOrderSignup: (id: number) =>
    client.post<{ ok: boolean; order: Order; message: string }>(`/orders/${id}/cancel-signup`, {}, { timeout: 30000 }).then(r => r.data),
  ocrOrderId: (id: number, imageBase64: string) =>
    client.post<{ ok: boolean; order_id_str: string; candidates?: string[]; message?: string }>(`/orders/${id}/ocr-order-id`, { image_base64: imageBase64 }, { timeout: 60000 }).then(r => r.data),
  hotkeyCaptureStatus: () =>
    client.get<{ ok: boolean; stage: 'idle' | 'capturing' | 'found' | 'not_found' | 'error'; message: string; order_id_str: string; target_order_id: number; target_store: string; frame: number; seq: number; ts: number }>(`/orders/hotkey-capture/status`, { timeout: 10000 }).then(r => r.data),
  hotkeyCaptureTrigger: () =>
    client.post<{ ok: boolean; stage: string; message: string }>(`/orders/hotkey-capture/trigger`, {}, { timeout: 10000 }).then(r => r.data),
  freeOrderPanel: () =>
    client.get<{ ok: boolean; cards: Array<{ account_key: string; nickname: string; card_id: number; amount_yuan: number; platforms: string[]; orders: Array<{ order_id: number; store_name: string; store_icon: string; platform: string; platform_order_id: string; order_sn: string; completed_time: string; order_money: number; rebate_money: number; redpack_reward_num: number; subsidy_amount: number }> }>; has_card: boolean }>(`/orders/free-order/panel`, { timeout: 60000 }).then(r => r.data),
  useFreeCard: (id: number, platformOrderId?: string) =>
    client.post<{ ok: boolean; message: string; raw?: Record<string, unknown> }>(`/orders/${id}/use-free-card`, platformOrderId ? { platform_order_id: platformOrderId } : {}, { timeout: 60000 }).then(r => r.data),
  delayOrderVoucher: (id: number, useDelayCard: boolean = false) =>
    client.post<{ ok: boolean; is_delayed: boolean; delay_time: number; message: string; use_delay_card?: boolean }>(`/orders/${id}/delay-voucher`, { use_delay_card: useDelayCard }).then(r => r.data),
  getMediaVipRecords: (key: string) =>
    client.get<{ ok: boolean; records: MediaVipRecord[]; error?: string }>(`/accounts/${key}/media-vip-records`, { timeout: 30000 }).then(r => r.data),
  deleteOrder: (id: number) => 
    client.delete<{ ok: boolean; message: string }>(`/orders/${id}`).then(r => r.data),
  batchDeleteOrders: (ids: number[]) =>
    client.post<{ ok: boolean; deleted: number[]; failed: { id: number; order_sn?: string; reason: string }[]; skipped: { id: number; reason: string }[]; message: string }>(
      '/orders/batch-delete', { ids }, { timeout: 120000 }
    ).then(r => r.data),

  // 日志与监控
  getJobs: (accountKey?: string, limit: number = 50) => client.get<{ ok: boolean; jobs: JobLog[] }>('/jobs', { params: { account_key: accountKey, limit } }).then(r => r.data),
  clearJobs: (accountKey?: string) => client.delete<{ ok: boolean; message: string }>('/jobs', { params: { account_key: accountKey } }).then(r => r.data),
  
  // 用户中心 (免付费状态)
  getMe: () => client.get<{ ok: boolean; user: UserInfo }>('/me').then(r => r.data),

  // 系统配置与通知管理
  getSettings: () => client.get<SystemSettings>('/settings').then(r => r.data),
  saveSettings: (data: Partial<SystemSettings>) => client.post<{ ok: boolean; message: string }>('/settings', data).then(r => r.data),
  testNotify: (channel: string, config: Record<string, any>) => 
    client.post<NotifyTestResult>('/settings/test-notify', { channel, config }).then(r => r.data),
  testTianditu: (data: { tianditu_key: string }) =>
    client.post<{ ok: boolean; message: string; data?: any }>('/settings/test-tianditu', data).then(r => r.data),
  testPhoton: () =>
    client.post<{ ok: boolean; message: string; count?: number; latency_ms?: number }>('/settings/test-photon').then(r => r.data),
  getClawBotStatus: (customPath?: string) => 
    client.get<ClawBotStatus & { ok: boolean; message: string }>('/settings/clawbot/status', { params: { custom_path: customPath } }).then(r => r.data),
  generateClawBotQr: (localToken?: string) =>
    client.post<ClawBotQrResponse>('/settings/clawbot/qr', { local_token: localToken }).then(r => r.data),
  pollClawBotStatus: (qrcode: string, verifyCode?: string) =>
    client.get<ClawBotPollResponse>('/settings/clawbot/poll', { params: { qrcode, verify_code: verifyCode } }).then(r => r.data),
  checkClawBotActivation: () =>
    client.post<ClawBotActivationResponse>('/settings/clawbot/check-activation').then(r => r.data),
  unbindClawBot: () =>
    client.post<{ ok: boolean; message: string }>('/settings/clawbot/unbind').then(r => r.data),

  // 阿里云 NTP 高精度授时服务
  getBeijingTime: () =>
    client
      .get<{
        ok: boolean;
        timestamp: number;
        beijing_time: string;
        server: string;
        synced: boolean;
        offset: number;
      }>('/time')
      .then(r => r.data),
};
