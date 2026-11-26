/** Append pages without rendering duplicate records, retaining the original order. */
export function mergeUniquePage<T>(previous: readonly T[], incoming: readonly T[], key: (item: T) => string | number): T[] {
  const records = new Map<string | number, T>();
  for (const item of previous) records.set(key(item), item);
  for (const item of incoming) records.set(key(item), item);
  return [...records.values()];
}

/** A missing or non-advancing cursor is an API error, never an empty collection. */
export function getMessageNextPage(metadata: { has_more?: boolean; next_page?: number | null }, page: number): number | null {
  if (typeof metadata.has_more !== 'boolean') {
    throw new Error('消息分页信息缺失，请重试');
  }
  if (!metadata.has_more) {
    if (metadata.next_page !== null) throw new Error('消息末页信息异常，请重试');
    return null;
  }
  if (!Number.isSafeInteger(metadata.next_page) || (metadata.next_page ?? 0) <= page) {
    throw new Error('消息分页游标异常，请重试');
  }
  return metadata.next_page as number;
}

/** WxPusher uses numbered fixed-size pages; deduplicated item counts are not offsets. */
export function getWxUserPage(metadata: { total?: number }, page: number, pageSize: number, receivedCount: number): { total: number; nextPage: number | null } {
  const total = metadata.total;
  if (!Number.isSafeInteger(total) || (total ?? -1) < 0) {
    throw new Error('关注用户总数缺失，请重试');
  }
  if (total === 0 && receivedCount > 0) {
    throw new Error('关注用户总数与列表不一致，请重试');
  }
  if (receivedCount === 0 && (total as number) > (page - 1) * pageSize) {
    throw new Error('关注用户分页返回不完整，请重试');
  }
  return {
    total: total as number,
    nextPage: page * pageSize < (total as number) ? page + 1 : null,
  };
}
