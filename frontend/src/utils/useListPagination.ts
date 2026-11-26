import { useCallback, useEffect, useMemo, useState } from 'react';

/** 移动端断点：页面内容自然展开，由外层 .tab-page 负责纵向滚动。 */
export function useMobileLayout(): boolean {
  const getMatches = () => typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(max-width: 768px)').matches;
  const [isMobile, setIsMobile] = useState<boolean>(getMatches);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia('(max-width: 768px)');
    const onChange = () => setIsMobile(query.matches);
    onChange();
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', onChange);
      return () => query.removeEventListener('change', onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  return isMobile;
}

export interface ListPagination<T> {
  dataSource: T[];
  pagination: {
    currentPage: number;
    pageSize: number;
    total: number;
    showTotal: boolean;
    showSizeChanger: boolean;
    pageSizeOpts: number[];
    onPageChange: (page: number) => void;
    onPageSizeChange: (size: number) => void;
  };
  visibleCount: number;
  hasMore: boolean;
  loadMore: () => void;
}

/**
 * 本地数组分页：
 * - 桌面端使用 Semi Table 受控分页；
 * - 移动端使用累加展示 + ListFooter 触底加载。
 */
export function useListPagination<T>(
  items: T[],
  resetKey: string,
  initialPageSize = 10,
): ListPagination<T> {
  const isMobile = useMobileLayout();
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [visibleCount, setVisibleCount] = useState(initialPageSize);

  useEffect(() => {
    setCurrentPage(1);
    setVisibleCount(initialPageSize);
  }, [resetKey, initialPageSize]);

  useEffect(() => {
    if (!isMobile) return;
    setVisibleCount((count) => Math.min(Math.max(count, initialPageSize), Math.max(items.length, initialPageSize)));
  }, [items.length, isMobile, initialPageSize]);

  const dataSource = useMemo(() => {
    if (isMobile) return items.slice(0, visibleCount);
    const start = (currentPage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [currentPage, isMobile, items, pageSize, visibleCount]);

  const handlePageChange = useCallback((page: number) => {
    setCurrentPage(Math.max(1, page));
  }, []);

  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(Math.max(1, size));
    setCurrentPage(1);
    setVisibleCount(Math.max(1, size));
  }, []);

  const loadMore = useCallback(() => {
    setVisibleCount((count) => Math.min(items.length, count + pageSize));
  }, [items.length, pageSize]);

  return {
    dataSource,
    pagination: {
      currentPage,
      pageSize,
      total: items.length,
      showTotal: true,
      showSizeChanger: true,
      pageSizeOpts: [10, 20, 50, 100],
      onPageChange: handlePageChange,
      onPageSizeChange: handlePageSizeChange,
    },
    visibleCount: Math.min(visibleCount, items.length),
    hasMore: isMobile && visibleCount < items.length,
    loadMore,
  };
}
