export type LogAccountType = 'user' | 'system' | 'unknown';

export interface LogAccountDisplay {
  name: string;
  key: string;
  type: LogAccountType;
  detail: string;
}

export const getLogAccountDisplay = (
  log: { account_key?: string; account_name?: string; account_type?: string },
  matchedAccount?: { nick_name?: string; key?: string }
): LogAccountDisplay => {
  const rawKey = String(log.account_key || '').trim();
  const isSystemKey = !rawKey || ['system', 'all', '__system__', '__global__'].includes(rawKey);

  if (isSystemKey || log.account_type === 'system') {
    return { name: '系统任务', key: '', type: 'system', detail: '系统任务' };
  }

  if (log.account_type === 'unknown' && !matchedAccount) {
    return { name: '历史任务', key: rawKey, type: 'unknown', detail: `历史任务 (Key: ${rawKey})` };
  }

  const name = String(matchedAccount?.nick_name || '').trim();
  return { name, key: rawKey, type: 'user', detail: `账号: ${name} (Key: ${rawKey})` };
};
