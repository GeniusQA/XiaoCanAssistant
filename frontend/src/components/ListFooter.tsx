import { useEffect, useRef } from 'react';
import { Button, Spin } from '@douyinfe/semi-ui';
import { useMobileLayout } from '../utils/useListPagination';

interface ListFooterProps {
  count: number;
  total?: number;
  hasMore?: boolean;
  loading?: boolean;
  error?: string;
  active?: boolean;
  onLoadMore?: () => void;
}

function findScrollRoot(footer: HTMLElement, tableRoot: HTMLElement | null): HTMLElement | null {
  if (tableRoot && tableRoot.scrollHeight > tableRoot.clientHeight + 1) return tableRoot;
  let node: HTMLElement | null = footer.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    const canScroll = /(auto|scroll)/.test(`${style.overflowY} ${style.overflow}`);
    if (canScroll && node.scrollHeight > node.clientHeight + 1) return node;
    node = node.parentElement;
  }
  return null;
}

/** 监听真正的纵向滚动容器；首屏不足高、空过滤页和尺寸变化也会重新检查。 */
export function ListFooter({ count, total, hasMore = false, loading = false, error = '', active = true, onLoadMore }: ListFooterProps) {
  const footerRef = useRef<HTMLDivElement>(null);
  const isMobile = useMobileLayout();
  useEffect(() => {
    const footer = footerRef.current;
    if (!footer || !active || !hasMore || loading || error || !onLoadMore) return;
    const container = footer.closest('[class*="-table-container"]');
    const tableRoot = container?.querySelector('.semi-table-body');
    const root = findScrollRoot(
      footer,
      tableRoot instanceof HTMLElement ? tableRoot : null,
    );
    if (!(root instanceof HTMLElement)) return;
    let frame: number | undefined;
    let requested = false;
    const check = () => {
      frame = undefined;
      if (requested || !footer.getClientRects().length || getComputedStyle(footer).visibility !== 'visible') return;
      if (root.scrollHeight - root.scrollTop - root.clientHeight <= 240) {
        requested = true;
        onLoadMore();
      }
    };
    const schedule = () => { if (frame === undefined) frame = requestAnimationFrame(check); };
    root.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    const observer = new ResizeObserver(schedule);
    observer.observe(root);
    observer.observe(footer);
    schedule();
    return () => {
      root.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      observer.disconnect();
      if (frame !== undefined) cancelAnimationFrame(frame);
    };
  }, [active, count, hasMore, loading, error, onLoadMore, isMobile]);

  if (!loading && !error && !hasMore && count === 0) return null;
  return (
    <div ref={footerRef} className="list-footer" role="status" aria-live="polite">
      {loading ? (
        <><Spin size="small" /><span>正在加载更多数据...</span></>
      ) : error ? (
        <><span className="text-semi-color-danger">{error}</span><Button size="small" theme="borderless" onClick={onLoadMore}>点击重试</Button></>
      ) : hasMore ? (
        <><span>已展示 {count}{total === undefined ? '' : ` / ${total}`} 条</span><Button size="small" theme="borderless" onClick={onLoadMore}>加载更多</Button></>
      ) : (
        <span>已展示全部 {count} 条，已到底部</span>
      )}
    </div>
  );
}
