export type LogAccountType = 'user' | 'system' | 'unknown';

export interface LogAccountDisplay {
  name: string;
  key: string;
  type: LogAccountType;
  detail: string;
}

const INVALID_NAMES = new Set([
  'system', 'all', 'unknown', '默认账号', '系统', '系统任务', '全局任务',
  '腾讯验证码', '验证码', '验证', 'waf', 'stgw', '风控拦截',
]);

const isInvalidName = (value: string): boolean => {
  const name = value.trim();
  const lower = name.toLowerCase();
  return !name || INVALID_NAMES.has(lower) || ['验证码', 'waf', 'stgw', '风控', '拦截'].some((token) => lower.includes(token));
};

export const getLogAccountDisplay = (
  log: { account_key?: string; account_name?: string; account_type?: string },
  matchedAccount?: { nickname?: string; key?: string }
): LogAccountDisplay => {
  const rawKey = String(log.account_key || '').trim();
  const isSystemKey = !rawKey || ['system', 'all', '__system__', '__global__'].includes(rawKey);

  if (isSystemKey || log.account_type === 'system') {
    return { name: '系统任务', key: '', type: 'system', detail: '系统任务' };
  }

  if (log.account_type === 'unknown' && !matchedAccount) {
    return { name: '历史任务', key: rawKey, type: 'unknown', detail: `历史任务 (Key: ${rawKey})` };
  }

  const candidates = [log.account_name, matchedAccount?.nickname, rawKey];
  const name = candidates.find((value) => value && !isInvalidName(value))?.trim();
  if (name) {
    return { name, key: rawKey, type: 'user', detail: `账号: ${name} (Key: ${rawKey})` };
  }

  const suffix = rawKey.includes('_') ? rawKey.split('_').pop() || rawKey : rawKey;
  const fallbackName = `账号 ${suffix.slice(0, 8)}`;
  return { name: fallbackName, key: rawKey, type: 'user', detail: `账号: ${fallbackName} (Key: ${rawKey})` };
};
