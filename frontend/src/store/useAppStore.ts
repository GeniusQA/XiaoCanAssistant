import { create } from 'zustand';
import type { Account, UserInfo, LocationHistoryItem } from '../types';
import { api } from '../api';

export interface ActiveLocation {
  cityCode: number;
  cityName: string;
  addressName: string;
  longitude: string;
  latitude: string;
}

const LOCATION_HISTORY_KEY = 'xiaocan_location_history';
const LOCATION_HISTORY_LIMIT = 10;

const getStoredLocation = (): ActiveLocation | null => {
  try {
    const raw = localStorage.getItem('xiaocan_active_location');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.longitude && parsed.latitude && parsed.cityName) {
        return parsed;
      }
    }
  } catch (e) {}
  return null;
};

const getStoredLocationHistory = (): LocationHistoryItem[] => {
  try {
    const raw = localStorage.getItem(LOCATION_HISTORY_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter(
          (item) => item && item.longitude && item.latitude && item.cityName
        );
      }
    }
  } catch (e) {}
  return [];
};

const persistLocationHistory = (items: LocationHistoryItem[]) => {
  try {
    localStorage.setItem(LOCATION_HISTORY_KEY, JSON.stringify(items));
  } catch (e) {}
};

const locationHistoryKey = (loc: { longitude: string; latitude: string }) =>
  `${Number(loc.longitude).toFixed(5)},${Number(loc.latitude).toFixed(5)}`;

const getStoredCurrentAccountKey = (): string => {
  try {
    return localStorage.getItem('xiaocan_current_account_key') || '';
  } catch (e) {
    return '';
  }
};

const getStoredAccounts = (): Account[] => {
  try {
    const raw = localStorage.getItem('xiaocan_cached_accounts');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch (e) {}
  return [];
};

const getStoredSidebarCollapsed = (): boolean => {
  try {
    return localStorage.getItem('xiaocan_sidebar_collapsed') === 'true';
  } catch (e) {
    return false;
  }
};

interface AppState {
  activeTab: string;
  tabActivationTick: number;
  accounts: Account[];
  currentAccountKey: string;
  isDarkMode: boolean;
  userInfo: UserInfo | null;
  loading: boolean;
  activeLocation: ActiveLocation | null;
  locationHistory: LocationHistoryItem[];
  isSidebarCollapsed: boolean;
  /** 跨页面跳转信号: 请求我的订单页定位到指定状态标签 (auditing/completed 等), 消费后自动清空 */
  pendingOrderStatus: string | null;

  setActiveTab: (tab: string) => void;
  setDarkMode: (dark: boolean) => void;
  setCurrentAccountKey: (key: string) => void;
  setActiveLocation: (loc: Partial<ActiveLocation> | null) => void;
  addLocationHistory: (loc: ActiveLocation) => void;
  removeLocationHistory: (loc: { longitude: string; latitude: string }) => void;
  clearLocationHistory: () => void;
  /** 从服务端同步抢单位置 (多设备协同: 移动端与 PC 共享同一份定位配置) */
  hydrateLocation: () => Promise<void>;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapse: () => void;
  setPendingOrderStatus: (status: string | null) => void;
  loadAccounts: () => Promise<void>;
  loadUserInfo: () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => {
  const initialAccounts = getStoredAccounts();
  const storedKey = getStoredCurrentAccountKey();
  const initialKey =
    storedKey && initialAccounts.some((a) => a.key === storedKey)
      ? storedKey
      : initialAccounts[0]?.key || storedKey;

  return {
    activeTab: 'dashboard',
    tabActivationTick: 0,
    accounts: initialAccounts,
    currentAccountKey: initialKey,
    isDarkMode: false,
    userInfo: null,
    loading: false,
    activeLocation: getStoredLocation(),
    locationHistory: getStoredLocationHistory(),
    isSidebarCollapsed: getStoredSidebarCollapsed(),
    pendingOrderStatus: null,

  setPendingOrderStatus: (status: string | null) => set({ pendingOrderStatus: status }),

  setActiveTab: (tab: string) =>
    set((state) => ({
      activeTab: tab,
      tabActivationTick: state.tabActivationTick + 1,
    })),

  setSidebarCollapsed: (collapsed: boolean) => {
    try {
      localStorage.setItem('xiaocan_sidebar_collapsed', String(collapsed));
    } catch (e) {}
    set({ isSidebarCollapsed: collapsed });
  },

  toggleSidebarCollapse: () => {
    const next = !get().isSidebarCollapsed;
    try {
      localStorage.setItem('xiaocan_sidebar_collapsed', String(next));
    } catch (e) {}
    set({ isSidebarCollapsed: next });
  },

  setActiveLocation: (loc: Partial<ActiveLocation> | null) => {
    if (!loc) {
      try {
        localStorage.removeItem('xiaocan_active_location');
      } catch (e) {}
      set({ activeLocation: null });
      api.saveAppLocation({ active_location: null }).catch(() => {});
      return;
    }
    const prev = get().activeLocation || {
      cityCode: 0,
      cityName: '',
      addressName: '',
      longitude: '',
      latitude: '',
    };
    const updated = { ...prev, ...loc } as ActiveLocation;
    try {
      localStorage.setItem('xiaocan_active_location', JSON.stringify(updated));
    } catch (e) {}
    set({ activeLocation: updated });
    // 同步至服务端, 供已配对的移动设备读取同一份定位
    api.saveAppLocation({ active_location: updated }).catch(() => {});
  },

  addLocationHistory: (loc: ActiveLocation) => {
    const key = locationHistoryKey(loc);
    const rest = get().locationHistory.filter((item) => locationHistoryKey(item) !== key);
    const next: LocationHistoryItem[] = [
      { ...loc, usedAt: Date.now() },
      ...rest,
    ].slice(0, LOCATION_HISTORY_LIMIT);
    persistLocationHistory(next);
    set({ locationHistory: next });
    api.saveAppLocation({ location_history: next }).catch(() => {});
  },

  removeLocationHistory: (loc: { longitude: string; latitude: string }) => {
    const key = locationHistoryKey(loc);
    const next = get().locationHistory.filter((item) => locationHistoryKey(item) !== key);
    persistLocationHistory(next);
    set({ locationHistory: next });
    api.saveAppLocation({ location_history: next }).catch(() => {});
  },

  clearLocationHistory: () => {
    persistLocationHistory([]);
    set({ locationHistory: [] });
    api.saveAppLocation({ location_history: [] }).catch(() => {});
  },

  hydrateLocation: async () => {
    try {
      const res = await api.getAppLocation();
      if (!res?.ok) return;
      const remoteActive = res.active_location;
      const remoteHistory = Array.isArray(res.location_history) ? res.location_history : [];
      const localActive = get().activeLocation;
      const localHistory = get().locationHistory;

      // 服务端有定位数据 → 以服务端为准 (移动端首次打开即可拿到 PC 的抢单位置)
      if (remoteActive && remoteActive.longitude && remoteActive.latitude) {
        if (!localActive || JSON.stringify(localActive) !== JSON.stringify(remoteActive)) {
          try {
            localStorage.setItem('xiaocan_active_location', JSON.stringify(remoteActive));
          } catch (e) {}
          set({ activeLocation: remoteActive });
        }
      } else if (localActive) {
        // 服务端为空但本地有 → 上推一次, 完成初始化同步
        api.saveAppLocation({ active_location: localActive }).catch(() => {});
      }

      if (remoteHistory.length > 0) {
        const remoteKey = remoteHistory.map((i: any) => locationHistoryKey(i)).join('|');
        const localKey = localHistory.map((i) => locationHistoryKey(i)).join('|');
        if (remoteKey !== localKey) {
          persistLocationHistory(remoteHistory);
          set({ locationHistory: remoteHistory });
        }
      } else if (localHistory.length > 0) {
        api.saveAppLocation({ location_history: localHistory }).catch(() => {});
      }
    } catch (e) {}
  },

  setDarkMode: (dark: boolean) => {
    set({ isDarkMode: dark });
    const body = document.body;
    if (dark) {
      body.setAttribute('theme-mode', 'dark');
    } else {
      body.removeAttribute('theme-mode');
    }
  },

  setCurrentAccountKey: (key: string) => {
    try {
      localStorage.setItem('xiaocan_current_account_key', key);
    } catch (e) {}
    set({ currentAccountKey: key });
  },

  loadAccounts: async () => {
    if (loadAccountsInFlight) {
      return loadAccountsInFlight;
    }
    loadAccountsInFlight = (async () => {
      try {
        set({ loading: true });
        const res = await api.getAccounts();
        const accounts = res.accounts || [];
        try {
          localStorage.setItem('xiaocan_cached_accounts', JSON.stringify(accounts));
        } catch (e) {}
        const current = get().currentAccountKey;
        let newCurrent = current;
        const exists = accounts.some((a) => a.key === current);
        if ((!newCurrent || !exists) && accounts.length > 0) {
          newCurrent = accounts[0].key;
          try {
            localStorage.setItem('xiaocan_current_account_key', newCurrent);
          } catch (e) {}
        }
        set({ accounts, currentAccountKey: newCurrent, loading: false });
      } catch (e) {
        set({ loading: false });
      } finally {
        loadAccountsInFlight = null;
      }
    })();
    return loadAccountsInFlight;
  },

  loadUserInfo: async () => {
    if (loadUserInfoInFlight) {
      return loadUserInfoInFlight;
    }
    loadUserInfoInFlight = (async () => {
      try {
        const res = await api.getMe();
        if (res.ok) {
          set({ userInfo: res.user });
        }
      } catch (e) {
      } finally {
        loadUserInfoInFlight = null;
      }
    })();
    return loadUserInfoInFlight;
  },
  };
});

let loadAccountsInFlight: Promise<void> | null = null;
let loadUserInfoInFlight: Promise<void> | null = null;

