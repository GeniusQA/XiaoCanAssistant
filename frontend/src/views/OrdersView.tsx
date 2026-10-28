import React, { useEffect, useState, useRef } from 'react';
import {
  Card,
  Table,
  Typography,
  Tag,
  Button,
  Space,
  Toast,
  Tabs,
  TabPane,
  Avatar,
  Input,
  RadioGroup,
  Radio,
  Empty,
  Modal,
  Banner,
  Tooltip
} from '@douyinfe/semi-ui';
import { gsap, useGSAP } from '../utils/animations';

import type { ColumnProps } from '@douyinfe/semi-ui/lib/es/table';
import {
  IconRefresh,
  IconCopy,
  IconSearch,
  IconHelpCircle
} from '@douyinfe/semi-icons';
import { useAppStore } from '../store/useAppStore';
import { api } from '../api';
import { useOnActivated } from '../utils/useOnActivated';
import type { Order } from '../types';

const { Title, Text } = Typography;

const normalizeConditionText = (condition?: string): string => {
  const c = (condition || '').trim();
  if (!c || c.includes('无需') || c.includes('免评')) {
    return '无需评价';
  }
  if (c.includes('用餐反馈') || c.includes('反馈') || c.includes('图文') || c.includes('好评')) {
    return '图文反馈';
  }
  return c;
};

/** 与小蚕官方一致的精确到秒倒计时: HH:MM:SS (超 24 小时按总小时数展示, 如 24:36:41) */
const formatRemainingHMS = (remainingSec: number | null | undefined): string => {
  if (remainingSec === null || remainingSec === undefined || remainingSec <= 0) return '';
  const h = Math.floor(remainingSec / 3600);
  const m = Math.floor((remainingSec % 3600) / 60);
  const s = remainingSec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

export const OrdersView: React.FC = () => {
  const currentAccountKey = useAppStore((s) => s.currentAccountKey);
  const accounts = useAppStore((s) => s.accounts);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const pendingOrderStatus = useAppStore((s) => s.pendingOrderStatus);
  const setPendingOrderStatus = useAppStore((s) => s.setPendingOrderStatus);
  const containerRef = useRef<HTMLDivElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const [tableScrollY, setTableScrollY] = useState<number>(460);

  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeStatusTab, setActiveStatusTab] = useState<string>('all');
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [uploadModalOrder, setUploadModalOrder] = useState<Order | null>(null);
  const [rebateRuleVisible, setRebateRuleVisible] = useState(false);
  // 会员专属订单免单 (对齐官方「会员专区-订单免单」: 券状态与补贴金额来自官方 UserFreeOrderInfo)
  type FreeOrderItem = {
    order_id: number; store_name: string; store_icon: string; platform: string;
    platform_order_id: string; order_sn: string; completed_time: string;
    order_money: number; rebate_money: number; redpack_reward_num: number; subsidy_amount: number;
  };
  type FreeOrderCard = {
    account_key: string; nickname: string; card_id: number; amount_yuan: number;
    platforms: string[]; orders: FreeOrderItem[];
  };
  const [freeOrderVisible, setFreeOrderVisible] = useState(false);
  const [freeCards, setFreeCards] = useState<FreeOrderCard[]>([]);
  const [freeLoading, setFreeLoading] = useState(false);
  const [freeConfirm, setFreeConfirm] = useState<{ card: FreeOrderCard; order: FreeOrderItem } | null>(null);
  const [freeDone, setFreeDone] = useState<{ amount: number; expire: string } | null>(null);
  const [freeSubmitting, setFreeSubmitting] = useState(false);
  const openFreeOrderModal = async () => {
    setFreeOrderVisible(true);
    setFreeConfirm(null);
    setFreeDone(null);
    setFreeLoading(true);
    try {
      const res = await api.freeOrderPanel();
      setFreeCards(res.cards || []);
      if (!res.cards?.some((c) => c.orders.length)) {
        const held = res.cards?.filter((c) => c.amount_yuan > 0);
        Toast.info(held?.length
          ? '免单券可用，但没有符合条件的订单（需最近48小时内完成且已绑定外卖单号）'
          : '当前所有账号均未持有可用免单券（每月 14:00 秒杀获取）');
      }
    } catch (e: unknown) {
      Toast.error(`获取免单信息失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setFreeLoading(false);
    }
  };
  const handleFreeOrderUse = async () => {
    if (!freeConfirm) return;
    setFreeSubmitting(true);
    try {
      await api.useFreeCard(freeConfirm.order.order_id, freeConfirm.order.platform_order_id);
      const expire = new Date(Date.now() + 24 * 3600 * 1000);
      const pad = (n: number) => String(n).padStart(2, '0');
      const subsidy = freeCalc(freeConfirm.order).subsidy;
      setFreeDone({
        amount: subsidy,
        expire: `${expire.getFullYear()}年${expire.getMonth() + 1}月${expire.getDate()}日 ${pad(expire.getHours())}:${pad(expire.getMinutes())}:${pad(expire.getSeconds())}`,
      });
      Toast.success(`免单成功！${subsidy.toFixed(2)}元无门槛小蚕红包已发放`);
      fetchOrders(undefined, true);
    } catch (e: unknown) {
      Toast.error(`免单失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setFreeSubmitting(false);
    }
  };
  /** 订单卡上的返利描述: 满23返11.92 (返利 = 官方返利 + 红包奖励) */
  const freeOrderRebateDesc = (o: FreeOrderItem): string => {
    const redpackRaw = Number(o.redpack_reward_num || 0);
    const redpackYuan = redpackRaw > 5 ? redpackRaw / 100 : redpackRaw;
    const total = Number(((o.rebate_money || 0) + redpackYuan).toFixed(2));
    return `满${(o.order_money || 0).toFixed(0)}返${total.toFixed(2)}`;
  };
  /** 免单补贴计算 (对齐官方规则): 到手金额 = 门槛金额 - 返利金额; 补贴 = min(到手, 15元上限) */
  const FREE_SUBSIDY_CAP = 15;
  const freeCalc = (o: FreeOrderItem) => {
    const redpackRaw = Number(o.redpack_reward_num || 0);
    const redpackYuan = redpackRaw > 5 ? redpackRaw / 100 : redpackRaw;
    const rebate = Number(((o.rebate_money || 0) + redpackYuan).toFixed(2));
    const threshold = Number(o.order_money || 0);
    const shoudao = Math.max(0, Number((threshold - rebate).toFixed(2)));
    const subsidy = Math.min(shoudao, FREE_SUBSIDY_CAP);
    // 比较符号: 到手未超上限 补到手(订单免单 > 补X); 到手等于上限(订单免单 = 补15); 到手超过上限 补15(订单免单 < 补15)
    const symbol = shoudao.toFixed(2) === FREE_SUBSIDY_CAP.toFixed(2) ? '=' : (shoudao > FREE_SUBSIDY_CAP ? '<' : '>');
    return { threshold, rebate, shoudao, subsidy, symbol };
  };
  const [platformOrderIdInput, setPlatformOrderIdInput] = useState<string>('');
  // 订单分页大小 (记忆用户选择, 默认20; 未受控时刷新数据会被默认值打回)
  const [ordersPageSize, setOrdersPageSize] = useState<number>(() => {
    try { const v = Number(localStorage.getItem('orders_page_size')); return [10, 20, 50, 100].includes(v) ? v : 20; } catch { return 20; }
  });
  const [currentOrderPage, setCurrentOrderPage] = useState<number>(1);
  // 订单删除 (仅已完成/已取消, 走官方接口)
  const [selectedOrderIds, setSelectedOrderIds] = useState<number[]>([]);
  const [deletingOrders, setDeletingOrders] = useState(false);
  const canDeleteOrders = activeStatusTab === 'completed' || activeStatusTab === 'cancelled';
  // 秒级倒计时: pending 状态的凭证/单号剩余时间每秒刷新 (与小蚕官方一致)
  const [nowTick, setNowTick] = useState<number>(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const timer = setInterval(() => setNowTick(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleBatchDelete = (singleId?: number) => {
    const ids = singleId ? [singleId] : selectedOrderIds;
    if (ids.length === 0) {
      Toast.warning('请先勾选要删除的订单');
      return;
    }
    Modal.confirm({
      title: `删除 ${ids.length} 笔订单`,
      content: '将同步调用小蚕官方删除接口并移除本地记录，删除后不可恢复。确定继续吗？',
      okText: '确认删除',
      okButtonProps: { type: 'danger' },
      cancelText: '取消',
      onOk: async () => {
        setDeletingOrders(true);
        try {
          const res = await api.batchDeleteOrders(ids);
          if (res.deleted.length > 0) {
            Toast.success(`已删除 ${res.deleted.length} 笔订单（官方已取消记录不再同步回列表）`);
          }
          if (res.failed.length > 0) {
            const reason = res.failed[0]?.reason || '官方删除失败';
            Toast.error({ content: `${res.failed.length} 笔删除失败: ${reason}`, duration: 8 });
          }
          if (res.skipped.length > 0 && res.deleted.length === 0 && res.failed.length === 0) {
            Toast.warning(res.skipped[0]?.reason || '部分订单不可删除');
          }
          setSelectedOrderIds((prev) => prev.filter((id) => !res.deleted.includes(id)));
          fetchOrders(undefined, true);
        } catch (e: any) {
          Toast.error(`删除失败: ${e.response?.data?.detail || e.message || e}`);
        } finally {
          setDeletingOrders(false);
        }
      },
    });
  };
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [delayingOrderId, setDelayingOrderId] = useState<number | null>(null);

  // 跨页面跳转定位: 仪表盘等入口请求定位到指定状态标签 (审核中/已完成等), 消费后清空信号
  useEffect(() => {
    if (pendingOrderStatus) {
      setActiveStatusTab(pendingOrderStatus);
      setPendingOrderStatus(null);
    }
  }, [pendingOrderStatus, setPendingOrderStatus]);

  // 纯净视口高度自适应：监听表格卡片容器，杜绝 DOM querySelector 与强制同步重排
  useEffect(() => {
    const updateHeight = () => {
      if (!tableContainerRef.current) return;
      const ch = tableContainerRef.current.clientHeight;
      if (ch > 100) {
        // 预留表头(44px)与分页条(48px)及边框空间(约96px)
        const targetH = Math.max(260, ch - 96);
        setTableScrollY((prev) => (Math.abs(prev - targetH) > 12 ? targetH : prev));
      }
    };

    updateHeight();
    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined' && tableContainerRef.current) {
      ro = new ResizeObserver(() => {
        updateHeight();
      });
      ro.observe(tableContainerRef.current);
    }

    window.addEventListener('resize', updateHeight);
    return () => {
      window.removeEventListener('resize', updateHeight);
      ro?.disconnect();
    };
  }, []);

  const lastOrdersSignatureRef = useRef<string>('');
  // 请求序号: 允许并发, 仅最新一次请求的结果生效 (避免切 Tab 时旧请求覆盖新数据)
  const fetchSeqRef = useRef<number>(0);

  const fetchOrders = async (kw?: string, force = false, silent = false) => {
    if (accounts.length === 0) {
      setOrders([]);
      return;
    }
    const keywordToSearch = typeof kw === 'string' ? kw.trim() : (searchKeyword || '').trim();
    const effectiveKey = currentAccountKey || accounts[0]?.key || '';
    const queryKey = `${effectiveKey}_${activeStatusTab}_${platformFilter}_${keywordToSearch}`;

    if (!force && lastOrdersSignatureRef.current === queryKey) {
      return;
    }
    const seq = ++fetchSeqRef.current;

    if (!silent) setLoading(true);
    try {
      const ordersRes = await api.getOrders({
        account_key: effectiveKey || undefined,
        status: activeStatusTab,
        platform: platformFilter,
        keyword: keywordToSearch
      });

      // 过期响应 (期间已发起更新的请求) 直接丢弃, 防止旧数据覆盖新 Tab 结果
      if (seq !== fetchSeqRef.current) return;

      if (ordersRes.ok) {
        lastOrdersSignatureRef.current = queryKey;
        setOrders(ordersRes.orders || []);
        if ((ordersRes.orders || []).length === 0 && ordersRes.sync_error) {
          Toast.warning({
            content: '官方订单同步失败，当前展示本地缓存。原因: ' + ordersRes.sync_error,
            duration: 6,
          });
        }
      } else if (ordersRes.error) {
        Toast.error('拉取订单列表失败: ' + ordersRes.error);
      }
    } catch (e) {
      lastOrdersSignatureRef.current = '';
      if (seq === fetchSeqRef.current) {
        Toast.error('拉取订单列表失败');
      }
    } finally {
      if (seq === fetchSeqRef.current) {
        if (!silent) setLoading(false);
      }
    }
  };

  useEffect(() => {
    // 存在跨页跳转定位信号时, 等信号消费 (Tab 已切换) 后再拉取, 避免先发一次无关请求
    if (pendingOrderStatus) return;
    // 切换 Tab/账号/平台时先清空旧列表, 避免上一个状态的订单残留在新 Tab 下形成"状态错乱"观感
    setOrders([]);
    fetchOrders();
  }, [currentAccountKey, activeStatusTab, platformFilter, pendingOrderStatus]);

  // 页面切入激活或顶级重复点击时立刻拉取最新订单数据
  useOnActivated('orders', () => {
    fetchOrders(undefined, true, false);
  }, { throttleMs: 300 });

  // 筛选与 Tab 切换时的平滑微过渡 (遵循 Semi Design 高性能 GPU 合成通道，杜绝整体表格下坠位移)
  useGSAP(
    () => {
      const tableEl = containerRef.current?.querySelector('.orders-table-container');
      if (tableEl) {
        gsap.killTweensOf(tableEl);
        gsap.fromTo(
          tableEl,
          { autoAlpha: 0.72 },
          {
            autoAlpha: 1,
            duration: 0.18,
            ease: 'power1.out',
            overwrite: 'auto',
            clearProps: 'opacity,visibility',
          }
        );
      }
    },
    { scope: containerRef, dependencies: [activeStatusTab, platformFilter] }
  );

  // 复制文本快捷方法
  const handleCopyText = (txt: string, label: string = '内容') => {
    navigator.clipboard.writeText(txt);
    Toast.success(`${label}已复制到剪贴板`);
  };

  // 打开回填单号弹窗: 未绑定为「提交单号」, 已绑定为「修改单号」(对应官方订单详情「修改」)
  const [modifyMode, setModifyMode] = useState(false);
  const lastHotkeySeqRef = useRef(-1);
  const handleOpenUploadModal = (order: Order) => {
    setModifyMode(Boolean(order.platform_order_id));
    setUploadModalOrder(order);
    setPlatformOrderIdInput(order.platform_order_id || '');
    // 基线取当前最新结果, 避免把历史识别结果当成新结果回填
    api.hotkeyCaptureStatus().then((s) => { lastHotkeySeqRef.current = s.seq ?? -1; }).catch(() => {});
  };

  // Alt+Q 全局热键截屏识别: 后端滚动多帧 OCR, 弹窗打开期间轮询结果自动回填
  useEffect(() => {
    if (!uploadModalOrder) return;
    const timer = setInterval(async () => {
      try {
        const s = await api.hotkeyCaptureStatus();
        if (!s || s.seq === lastHotkeySeqRef.current) return;
        lastHotkeySeqRef.current = s.seq;
        if (s.stage === 'found' && s.order_id_str) {
          if (s.target_order_id === uploadModalOrder.id) {
            setPlatformOrderIdInput(s.order_id_str);
            Toast.success(`已通过 Alt+Q 截屏识别外卖单号: ${s.order_id_str}，请核对后提交`);
          } else {
            Toast.info(`截屏识别到单号 ${s.order_id_str}，但它属于其他待反馈订单（${s.target_store || '订单' + s.target_order_id}），请打开对应订单核对`);
          }
        } else if (s.stage === 'not_found' || s.stage === 'error') {
          Toast.warning(`Alt+Q 截屏识别未成功: ${s.message || '请手动输入'}`);
        }
      } catch { /* 轮询失败忽略 */ }
    }, 1500);
    return () => clearInterval(timer);
  }, [uploadModalOrder]);

  // OCR 自动识别: 粘贴外卖订单截图 -> 官方 OCR 提取单号自动回填 (手动输入的兜底)
  const [ocrLoading, setOcrLoading] = useState(false);
  const handlePasteScreenshot = async (e: React.ClipboardEvent) => {
    if (!uploadModalOrder || ocrLoading) return;
    const items = Array.from(e.clipboardData?.items || []);
    const imgItem = items.find((it) => it.type.startsWith('image/'));
    if (!imgItem) return;
    const file = imgItem.getAsFile();
    if (!file) return;
    e.preventDefault();
    setOcrLoading(true);
    try {
      const dataUrl: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('读取剪贴板图片失败'));
        reader.readAsDataURL(file);
      });
      const imageBase64 = dataUrl.split(',')[1] || '';
      if (!imageBase64) {
        Toast.warning('剪贴板内容不是有效图片');
        return;
      }
      const res = await api.ocrOrderId(uploadModalOrder.id, imageBase64);
      if (res.ok && res.order_id_str) {
        setPlatformOrderIdInput(res.order_id_str);
        Toast.success(`已自动识别外卖单号: ${res.order_id_str}，请核对后提交`);
      } else {
        Toast.warning(res.message || '未能从截图中识别出单号，请手动输入');
      }
    } catch (e: any) {
      const detail = e.response?.data?.detail || e.message || e;
      Toast.error(`截图识别失败: ${detail}`);
    } finally {
      setOcrLoading(false);
    }
  };

  // 提交/更新外卖单号
  const handleConfirmSubmitId = async () => {
    if (!uploadModalOrder) return;
    const orderIdToSubmit = platformOrderIdInput.trim();
    if (!orderIdToSubmit) {
      Toast.warning('请输入外卖平台订单号');
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.submitPlatformOrderId(uploadModalOrder.id, orderIdToSubmit, undefined, modifyMode);
      if (res.ok) {
        Toast.success(res.message || (modifyMode ? '外卖单号已修改' : '外卖单号已成功绑定'));
        setUploadModalOrder(null);
        setPlatformOrderIdInput('');
        fetchOrders(undefined, true);
      } else {
        Toast.error({
          content: res.error || res.message || '单号提交失败，请重试',
          duration: 6,
        });
      }
    } catch (e: any) {
      Toast.error(`提交异常: ${e.message || e}`);
    } finally {
      setSubmitting(false);
    }
  };

  // 取消报名 (对应官方订单卡片底部「取消报名」)
  const [cancelingOrderId, setCancelingOrderId] = useState<number | null>(null);
  const handleCancelSignup = (order: Order) => {
    Modal.confirm({
      title: '取消报名',
      content: `将取消「${order.store_name || '该店铺'}」的报名并放弃本次霸王餐名额（对应官方「取消报名」），取消后不可恢复。确定继续吗？`,
      okText: '确认取消报名',
      okButtonProps: { type: 'danger' },
      cancelText: '再想想',
      onOk: async () => {
        setCancelingOrderId(order.id);
        try {
          const res = await api.cancelOrderSignup(order.id);
          if (res.ok) {
            Toast.success(res.message || '已成功取消报名');
            fetchOrders(undefined, true);
          } else {
            Toast.error(res.message || '取消报名失败');
          }
        } catch (e: any) {
          Toast.error(`取消失败: ${e.response?.data?.detail || e.message || e}`);
        } finally {
          setCancelingOrderId(null);
        }
      },
    });
  };

  const handleDelayVoucher = async (order: Order) => {
    Modal.confirm({
      title: '使用延时券延长提交时间',
      content: '将消耗 1 张延时券，把该订单的凭证提交时间延长 1 小时（可多次使用，最长至次日早 6 点）。官方延时券剩余数量以小蚕 App 为准。确定使用吗？',
      okText: '使用延时券',
      cancelText: '取消',
      onOk: async () => {
        setDelayingOrderId(order.id);
        try {
          const res = await api.delayOrderVoucher(order.id, true);
          if (res.ok) {
            Toast.success(res.message || '延时券使用成功，提交时间已延长');
            fetchOrders(undefined, true);
          } else {
            Toast.error(res.message || '延时申请失败');
          }
        } catch (e: any) {
          Toast.error(`延时操作失败: ${e.response?.data?.detail || e.message || e}`);
        } finally {
          setDelayingOrderId(null);
        }
      },
    });
  };

  const DEFAULT_PLATFORM_ICONS: Record<string, string> = {
    jingdong: 'https://img10.360buyimg.com/imagetools/jfs/t1/282159/28/8442/32950/67e10a0dFb8e53ae1/3a4d405ef2b69aff.jpg',
    jd: 'https://img10.360buyimg.com/imagetools/jfs/t1/282159/28/8442/32950/67e10a0dFb8e53ae1/3a4d405ef2b69aff.jpg',
    eleme: 'https://cube.elemecdn.com/8/FF/D6D23A46B485F85152E1F9A855510jpg.jpg',
    taobao: 'https://cube.elemecdn.com/8/FF/D6D23A46B485F85152E1F9A855510jpg.jpg',
    meituan: 'http://p0.meituan.net/business/cf047871536dfa726936dfdc834b23c7211376.jpg'
  };

  const getPlatformBadge = (plat?: string) => {
    if (plat === 'jingdong' || plat === 'jd') {
      return { label: '京东外卖', color: 'red' as const, avatarColor: 'red' as const };
    }
    if (plat === 'eleme' || plat === 'taobao') {
      return { label: '淘宝闪购', color: 'blue' as const, avatarColor: 'blue' as const };
    }
    return { label: '美团外卖', color: 'orange' as const, avatarColor: 'orange' as const };
  };

  const columns: ColumnProps<Order>[] = [
    {
      title: '店铺与订单号',
      dataIndex: 'store_name',
      width: 340,
      render: (name: string, row?: Order) => {
        const platInfo = getPlatformBadge(row?.platform);
        const avatarSrc = row?.store_icon || DEFAULT_PLATFORM_ICONS[row?.platform || 'meituan'];
        return (
          <div className="flex items-start gap-3 max-w-[340px]">
            <Avatar
              size="medium"
              shape="square"
              src={avatarSrc}
              color={platInfo.avatarColor}
              className="flex-shrink-0"
            >
              {name?.[0] || '外'}
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Tag color={platInfo.color} size="small" shape="square" className="flex-shrink-0">
                  {platInfo.label}
                </Tag>
                <Typography.Text
                  ellipsis={{ showTooltip: true }}
                  style={{ maxWidth: 220, cursor: 'pointer' }}
                  strong
                  className="text-[14px] hover:text-semi-color-primary transition-colors"
                  title="点击复制店铺名"
                  onClick={() => handleCopyText(name, '店铺名称')}
                >
                  {name}
                </Typography.Text>
                {Number(row?.original_user_rebate || 0) > 0 && Number(row?.order_money || 0) > 0 && (() => {
                  // 对齐小蚕APP: 返 = max(原始返豆, 实际返豆) + 红包奖励 (红包沿用进制定位换算)
                  const redpackRaw = Number(row?.redpack_reward_num || 0);
                  const redpackYuan = redpackRaw > 5 ? redpackRaw / 100 : redpackRaw;
                  const tagRebate = parseFloat(
                    (Math.max(Number(row?.original_user_rebate || 0), Number(row?.rebate_money || 0)) + redpackYuan).toFixed(2)
                  );
                  return (
                    <Tag color="red" size="small" shape="square" className="flex-shrink-0">
                      满{row?.order_money}返{tagRebate}
                    </Tag>
                  );
                })()}
              </div>
              <div className="flex items-center gap-1 mt-1 text-xs text-semi-color-text-2 font-mono">
                <span className="truncate max-w-[180px]">小蚕单号: {row?.order_sn}</span>
                <Button
                  theme="borderless"
                  icon={<IconCopy size="small" />}
                  size="small"
                  className="p-0.5 ml-1 h-5 flex-shrink-0"
                  onClick={() => row && handleCopyText(row.order_sn, '小蚕单号')}
                />
              </div>
            </div>
          </div>
        );
      },
    },
    {
      title: '实付与返利',
      dataIndex: 'order_money',
      width: 170,
      render: (_: any, row?: Order) => {
        const hasRedpack = Boolean(row?.redpack_reward_num && row.redpack_reward_num > 0);
        const isPercentOrder =
          row?.order_type === 12 ||
          Boolean(row?.rebate_ratio && row.rebate_ratio > 0) ||
          Number(row?.order_money || 0) <= 0;
        const hasRealOrderMoney = Number(row?.order_money || 0) > 0;
        const isDeducted =
          Number(row?.original_user_rebate || 0) > Number(row?.rebate_money || 0) &&
          Number(row?.rebate_money || 0) > 0;
        return (
          <div>
            <div className="text-xs text-semi-color-text-2">
              {isPercentOrder && !hasRealOrderMoney ? (
                <>
                  返利模式：<Text strong>{row?.rebate_ratio ? `按实付 ${row.rebate_ratio}% 返` : '按比例返现'}</Text>
                </>
              ) : (
                <>
                  门槛金额：<Text strong>¥{row?.order_money}</Text>
                </>
              )}
            </div>
            {Number(row?.platform_total_price || 0) > 0 && (
              <div className="text-xs text-semi-color-text-2 mt-0.5">
                实付金额：<Text strong>¥{row?.platform_total_price}</Text>
              </div>
            )}
            <div className="text-sm font-semibold text-semi-color-danger mt-0.5 flex items-center gap-1 flex-wrap">
              <span>
                {isPercentOrder && !hasRealOrderMoney && row?.status !== 'completed'
                  ? `最高返：¥${row?.rebate_money}`
                  : `返利：¥${row?.rebate_money}`}
              </span>
              {hasRedpack && (
                <Tag size="small" color="red">
                  +{((row!.redpack_reward_num!) > 5 ? (row!.redpack_reward_num!) / 100 : (row!.redpack_reward_num!)).toFixed(2)} 红包
                </Tag>
              )}
            </div>
            {row?.remark && (
              <div className="text-xs text-semi-color-text-2 mt-1 leading-snug">
                备注："{row.remark}"
              </div>
            )}
            {isDeducted && (
              <div
                className="text-xs mt-1 flex items-center gap-1 w-fit"
                style={{
                  color: 'var(--semi-color-warning-2)',
                  background: 'var(--semi-color-warning-light-default)',
                  padding: '2px 8px',
                  borderRadius: 4,
                }}
              >
                <span>平台扣除返利金额，返您{row?.rebate_money}蚕豆</span>
                <IconHelpCircle
                  size="small"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setRebateRuleVisible(true)}
                />
              </div>
            )}
          </div>
        );
      },
    },
    {
      title: '外卖单号 / 审核状态',
      dataIndex: 'status',
      width: 270,
      render: (status: string, row?: Order) => {
        const hasExtId = !!row?.platform_order_id;
        const isPercentOrder =
          row?.order_type === 12 ||
          Boolean(row?.rebate_ratio && row.rebate_ratio > 0) ||
          Number(row?.order_money || 0) <= 0;
        let badgeColor: 'green' | 'amber' | 'blue' | 'red' | 'grey' | 'cyan' = 'grey';
        let statusText = '未知状态';

        if (status === 'completed') {
          badgeColor = 'green';
          // 已返利总额 = 官方返利 + 红包奖励 (红包字段沿用下方标签的进制定位换算规则)
          const redpackRaw = Number(row?.redpack_reward_num || 0);
          const redpackYuan = redpackRaw > 5 ? redpackRaw / 100 : redpackRaw;
          const totalRebated = parseFloat((Number(row?.rebate_money || 0) + redpackYuan).toFixed(2));
          statusText = `已返利 ¥${totalRebated}`;
        } else if (status === 'auditing') {
          badgeColor = 'amber';
          statusText = '平台审核中';
        } else if (status === 'pending') {
          if (hasExtId) {
            badgeColor = 'cyan';
            statusText = '已下单，待反馈';
          } else {
            badgeColor = 'blue';
            statusText = '已报名，待下单';
          }
        } else if (status === 'rejected') {
          badgeColor = 'red';
          statusText = row?.reject_reason ? `已驳回: ${row.reject_reason}` : '已驳回';
        } else if (status === 'cancelled') {
          badgeColor = 'grey';
          statusText = '已取消';
        }

        const remainingSec = row?.timeout_time ? row.timeout_time - nowTick : null;
        const countdownHMS = formatRemainingHMS(remainingSec);
        const isTimeout = remainingSec !== null && remainingSec <= 0;
        // 与小蚕官方一致的子状态剩余时间提示 (精确到秒)
        // 官方接口只返回 rebate_condition(99=无需评价) / rebate_condition_str("无需反馈"), 提示文案由前端拼装:
        // 官方 APP 对 99 的展示为 "本单无需评价，如评价将无法拿到额外返利" (整段标红)
        const condText = (String(row?.condition || '无需评价')
          .replace(/[（(].*?需含字含图.*?[）)]/g, '')
          .replace(/[（(]需含字含图[）)]/g, '')
          .trim()) || '无需评价';
        const deadlineHint = remainingSec === null
          ? ''
          : isTimeout
            ? `(${hasExtId ? '上传凭证已超时' : '提交单号已超时'})`
            : `(${hasExtId ? '上传凭证剩余时间' : '提交单号剩余时间'}${countdownHMS})`;
        const isNoReviewCond = condText === '无需评价' || condText === '无需反馈';
        const condHint = isNoReviewCond
          ? '本单无需评价，如评价将无法拿到额外返利'
          : `本单${condText}，请在截止时间前完成反馈`;

        return (
          <div className="max-w-[270px]">
            {row?.free_order_at ? (
              <div
                className="mb-1.5 rounded-md border border-[#ffd591] bg-[#fff7e6] px-2 py-1 text-[11px] leading-4 text-[#d46b08] flex items-center gap-1"
                title={`免单时间: ${new Date(row.free_order_at * 1000).toLocaleString('zh-CN')}`}
              >
                <span>🎟️</span>
                <span>已享会员专属免单权益，{Number(row.free_subsidy || 0).toFixed(2)}元红包免单已到账</span>
              </div>
            ) : null}
            <Space spacing="tight">
              <Tag color={badgeColor} size="small">
                {statusText}
              </Tag>
              {status === 'pending' && isTimeout && (
                <Tag color="red" size="small">已超时</Tag>
              )}
            </Space>
            {status === 'pending' && deadlineHint && (
              <div className="mt-1 text-xs text-semi-color-danger leading-4">
                {deadlineHint} {condHint}
              </div>
            )}
            <div className="mt-1.5 text-xs font-mono">
              {hasExtId ? (
                <div>
                  <div className="flex items-center gap-1 text-semi-color-text-1">
                    <span className="truncate max-w-[170px]" title={row?.platform_order_id}>
                      外卖单号: {row?.platform_order_id}
                    </span>
                    <Button
                      theme="borderless"
                      icon={<IconCopy size="small" />}
                      size="small"
                      className="p-0.5 ml-0.5 h-5 flex-shrink-0"
                      onClick={() => row && handleCopyText(row.platform_order_id!, '外卖单号')}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-semi-color-text-3">未绑定外卖单号</span>
                  {status === 'pending' && (
                    <div className="flex items-center gap-1">
                      {!isPercentOrder && (
                        row?.delay_used ? (
                          <Tooltip content="官方接口反馈该订单已使用过领红包延时特权">
                            <Tag color="green" size="small">已延时</Tag>
                          </Tooltip>
                        ) : (
                          <Button
                            theme="light"
                            type="warning"
                            size="small"
                            loading={delayingOrderId === row?.id}
                            className="!py-0.5 !px-1.5 text-xs h-5"
                            onClick={() => row && handleDelayVoucher(row)}
                            title="使用延时券延长凭证提交时间"
                          >
                            使用延时券
                          </Button>
                        )
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      },
    },
    {
      title: '评价门槛',
      dataIndex: 'condition',
      width: 140,
      render: (cond: string) => {
        const cleanCond = String(cond || '无需评价')
          .replace(/[（(].*?需含字含图.*?[）)]/g, '')
          .replace(/[（(]需含字含图[）)]/g, '')
          .trim() || '无需评价';
        return (
          <Tag color="grey" size="small">
            {normalizeConditionText(cleanCond)}
          </Tag>
        );
      },
    },
    {
      title: '下单时间',
      dataIndex: 'created_at',
      width: 180,
      render: (timeStr: string) => (
        <Text size="small" type="secondary">{timeStr}</Text>
      ),
    },
    {
      title: '操作',
      dataIndex: 'actions',
      width: 190,
      render: (_: any, row?: Order) => {
        const st = (row?.status || '').toLowerCase();
        const hasExt = Boolean(row?.platform_order_id);
        // 单号操作按钮文案对齐官方: 已下单待反馈→「上传凭证」, 已报名待下单→「提交单号」
        if (st === 'pending') {
          return (
            <div className="flex items-center gap-1 flex-wrap">
              <Button
                size="small"
                theme="light"
                onClick={() => row && handleOpenUploadModal(row)}
              >
                {hasExt ? '上传凭证' : '提交单号'}
              </Button>
              <Button
                size="small"
                theme="light"
                type="danger"
                loading={cancelingOrderId === row?.id}
                onClick={() => row && handleCancelSignup(row)}
              >
                取消报名
              </Button>
            </div>
          );
        }
        if (st !== 'completed' && st !== 'cancelled') {
          return <Text type="tertiary" size="small">-</Text>;
        }
        return (
          <Button
            size="small"
            theme="light"
            type="danger"
            loading={deletingOrders}
            onClick={() => row && handleBatchDelete(row.id)}
          >
            删除
          </Button>
        );
      },
    }
  ];

  if (accounts.length === 0) {
    return (
      <div className="w-full flex flex-col h-full min-h-0 space-y-3">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 shrink-0">
          <div>
            <Title heading={3}>我的霸王餐订单与返利</Title>
            <Text type="secondary" size="small">实时跟踪已抢霸王餐状态与返利到账明细</Text>
          </div>
        </div>
        <Card className="flex-1 min-h-0 rounded-xl border border-semi-color-border py-16 flex flex-col items-center justify-center text-center bg-semi-color-bg-0">
          <Empty
            title="当前未登录或未托管小蚕账号"
            description="查看已抢霸王餐订单与返利明细需要真实小蚕账号凭证。当前已退出或无登录账号，系统已停止拉取任何订单数据。"
          >
            <Button
              theme="solid"
              type="primary"
              onClick={() => setActiveTab('accounts')}
              className="mt-4"
            >
              前往「小蚕账号」添加或绑定账号
            </Button>
          </Empty>
        </Card>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full flex flex-col h-full min-h-0 space-y-3">
      {/* 注入表格高度自适应与分页规范样式 */}
      <style>{`
        .orders-table-container .semi-table-body {
          height: var(--table-scroll-y) !important;
          min-height: var(--table-scroll-y) !important;
          max-height: var(--table-scroll-y) !important;
          overflow-y: auto !important;
          contain: content;
          will-change: transform;
          transform: translateZ(0);
          -webkit-overflow-scrolling: touch;
        }
        .orders-table-container .semi-table-placeholder {
          min-height: var(--table-scroll-y) !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
        }
        .orders-table-container .semi-spin-wrapper {
          display: flex !important;
          flex-direction: column !important;
          align-items: center !important;
          justify-content: center !important;
          position: absolute !important;
          top: 50% !important;
          left: 50% !important;
          transform: translate(-50%, -50%) !important;
          width: auto !important;
          height: auto !important;
          z-index: 10 !important;
        }
        .orders-table-container .semi-table-pagination-outer {
          padding: 10px 16px !important;
          margin: 0 !important;
          margin-top: auto !important;
          flex-shrink: 0 !important;
          border-top: 1px solid var(--semi-color-border) !important;
          display: flex !important;
          align-items: center !important;
          justify-content: space-between !important;
          background-color: var(--semi-color-bg-0) !important;
        }
      `}</style>

      {/* 头部标题与操作 */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 shrink-0">
        <div>
          <Title heading={3}>我的霸王餐订单与返利</Title>
          <Text type="secondary" size="small">实时跟踪已抢霸王餐状态与返利到账明细</Text>
        </div>

        <div className="flex items-center gap-2">
          {canDeleteOrders && (
            <Button
              type="danger"
              theme="light"
              disabled={selectedOrderIds.length === 0}
              loading={deletingOrders}
              onClick={() => handleBatchDelete()}
            >
              删除选中{selectedOrderIds.length > 0 ? ` (${selectedOrderIds.length})` : ''}
            </Button>
          )}
          <Button
            icon={<span className="text-base leading-none">🎟️</span>}
            onClick={openFreeOrderModal}
          >
            订单免单
          </Button>
          <Button
            icon={<IconRefresh spin={loading} />}
            loading={loading}
            onClick={() => fetchOrders(undefined, true)}
          >
            刷新订单
          </Button>
        </div>
      </div>

      {/* 状态分类与平台过滤控制栏 */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 shrink-0">
        <Tabs
          type="button"
          activeKey={activeStatusTab}
          onChange={(k) => setActiveStatusTab(String(k))}
          className="shrink-0"
        >
          <TabPane tab="全部" itemKey="all" />
          <TabPane tab="待上传" itemKey="pending" />
          <TabPane tab="审核中" itemKey="auditing" />
          <TabPane tab="已完成" itemKey="completed" />
          <TabPane tab="已驳回" itemKey="rejected" />
          <TabPane tab="已取消" itemKey="cancelled" />
        </Tabs>

        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          <RadioGroup
            type="button"
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
          >
            <Radio value="all">全部</Radio>
            <Radio value="meituan">美团</Radio>
            <Radio value="eleme">淘宝闪购</Radio>
            <Radio value="jingdong">京东</Radio>
          </RadioGroup>

          <Input
            prefix={<IconSearch />}
            placeholder="搜索店铺名、单号..."
            value={searchKeyword}
            onChange={(val) => setSearchKeyword(val || '')}
            onEnterPress={() => fetchOrders()}
            showClear
            onClear={() => {
              setSearchKeyword('');
              fetchOrders('');
            }}
            style={{ width: 220 }}
          />
        </div>
      </div>

      {/* 主体表格卡片：撑满视口垂直剩余高度，杜绝超出页面滚动 */}
      <Card
        className="flex-1 min-h-0 flex flex-col rounded-xl border border-semi-color-border shadow-xs overflow-hidden bg-semi-color-bg-0"
        bodyStyle={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, padding: 0 }}
      >
        <div
          ref={tableContainerRef}
          className="orders-table-container relative flex-1 min-h-0 flex flex-col overflow-hidden"
          style={{
            ['--table-scroll-y' as any]: `${tableScrollY}px`
          }}
        >
          <Table
            rowKey="id"
            columns={columns}
            dataSource={orders}
            rowSelection={
              canDeleteOrders
                ? {
                    selectedRowKeys: selectedOrderIds,
                    onChange: (keys: any) => setSelectedOrderIds((keys || []).map(Number)),
                  }
                : undefined
            }
            loading={loading}
            pagination={{
              pageSize: ordersPageSize,
              currentPage: currentOrderPage,
              showSizeChanger: true,
              pageSizeOpts: [10, 20, 50, 100],
              onPageChange: (page: number) => setCurrentOrderPage(page),
              onChange: (_page: number, pageSize: number) => {
                // 分页大小切换后回到第1页并记忆用户选择, 避免刷新数据后被默认值20打回
                setOrdersPageSize(pageSize);
                setCurrentOrderPage(1);
                try { localStorage.setItem('orders_page_size', String(pageSize)); } catch { /* ignore */ }
              },
            }}
            scroll={{ y: tableScrollY, x: 1000 }}
            size="middle"
            empty={
              loading ? (
                <div className="py-20 text-center flex flex-col items-center justify-center m-auto">
                  <div className="text-sm font-medium text-semi-color-text-0 mt-8">
                    正在同步霸王餐订单记录...
                  </div>
                </div>
              ) : (
                <div className="py-16 text-center flex flex-col items-center justify-center m-auto">
                  <Empty
                    title="暂无匹配的霸王餐订单记录"
                    description="已抢到的霸王餐订单将自动同步展示于此，支持返利明细与审核进度实时追踪"
                  />
                </div>
              )
            }
          />
        </div>
      </Card>

      {/* 会员专属订单免单弹窗 (对齐官方: 券列表 → 补贴计算确认 → 发放红包) */}
      <Modal
        title={
          <div className="flex items-center justify-between w-full pr-2">
            <span>会员专属订单免单</span>
            <Button theme="borderless" icon={<IconRefresh spin={freeLoading} />} size="small" onClick={openFreeOrderModal} />
          </div>
        }
        visible={freeOrderVisible}
        onCancel={() => { setFreeOrderVisible(false); setFreeConfirm(null); setFreeDone(null); }}
        footer={null}
        width={440}
        bodyStyle={{ maxHeight: '65vh', overflowY: 'auto' }}
      >
        {/* 步骤一: 券与资格订单列表 (官方图二) */}
        {!freeConfirm && !freeDone && (
          <div className="space-y-3">
            <div className="rounded-lg bg-[#fff7e6] border border-[#ffd591] px-3 py-2 text-xs text-[#8c5a00] leading-5">
              <div>· 最近48小时内的完成的订单可参与免单活动</div>
              <div>· 额外补贴至免单，上限补贴15元无门槛小蚕红包</div>
            </div>
            {freeLoading && <div className="text-center text-semi-color-text-2 text-sm py-6">正在获取免单券与订单数据...</div>}
            {!freeLoading && freeCards.filter((c) => c.orders.length > 0).length === 0 && (
              <Empty description="没有可参与免单的订单" style={{ padding: 24 }} />
            )}
            {freeCards.filter((c) => c.orders.length > 0).map((card) => (
              <div key={card.account_key} className="space-y-2">
                <div className="flex items-center gap-2 text-xs">
                  <Text strong>{card.nickname}</Text>
                  <Tag color="red" size="small">免单券 ¥{card.amount_yuan.toFixed(2)}</Tag>
                </div>
                {card.orders.map((o) => (
                  <div key={o.order_id} className="rounded-xl border border-semi-color-border p-3 flex items-start gap-2.5">
                    {o.store_icon ? (
                      <img src={o.store_icon} alt="" className="w-12 h-12 rounded-lg object-cover flex-shrink-0" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                    ) : null}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <Text strong ellipsis={{ showTooltip: true }} style={{ maxWidth: 180 }}>{o.store_name}</Text>
                        <Tag color="orange" size="small">{o.platform === 'eleme' ? '饿了么' : o.platform === 'jingdong' ? '京东' : '外卖'}</Tag>
                      </div>
                      <div className="mt-1 text-xs">
                        <span className="rounded bg-[#fde3e3] text-[#e03e3e] px-1.5 py-0.5 text-[11px]">
                          活动返利 {freeOrderRebateDesc(o)}·可得补贴 {freeCalc(o).subsidy.toFixed(2)}元
                        </span>
                      </div>
                      <div className="mt-1.5 text-[11px] text-semi-color-text-2 leading-4">
                        <div>订单号: <span className="font-mono">{o.order_sn}</span></div>
                        <div>完单时间: {o.completed_time}</div>
                      </div>
                    </div>
                    <Button theme="solid" type="danger" size="small" className="flex-shrink-0" onClick={() => setFreeConfirm({ card, order: o })}>
                      选择免单
                    </Button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* 步骤二: 补贴计算确认 (对齐官方图: 三步时间线 + 到手徽标 + 补贴符号规则) */}
        {freeConfirm && !freeDone && (() => {
          const calc = freeCalc(freeConfirm.order);
          const shoudaoTxt = calc.shoudao.toFixed(2);
          const subsidyTxt = calc.subsidy.toFixed(2);
          return (
          <div className="relative">
            <div className="absolute right-0 top-8 w-20 h-20 rounded-full border-[3px] border-[#43a047] text-[#43a047] flex items-center justify-center text-2xl font-bold -rotate-12 opacity-80 free-stamp">
              免单
            </div>
            <div className="rounded-xl bg-[#fdf6ec] border border-[#f5d9a8] px-3 py-2 text-xs text-semi-color-text-1 mb-3 flex items-center gap-1.5">
              <span>📦</span>
              <Text strong ellipsis={{ showTooltip: true }} style={{ maxWidth: 300 }}>{freeConfirm.order.store_name}</Text>
            </div>
            <div className="space-y-0">
              <div className="flex gap-3 free-step">
                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-[#e8622d] text-white flex items-center justify-center text-xs flex-shrink-0">✓</div>
                  <div className="w-0.5 flex-1 bg-[#e8622d] min-h-[26px]" />
                </div>
                <div className="pb-4 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-[15px]" style={{ color: '#5b3a1e' }}>订单信息</div>
                    <span className="rounded-full bg-[#a14e21] text-white text-[11px] px-2.5 py-0.5 flex-shrink-0">活动 到手{shoudaoTxt}元</span>
                  </div>
                  <div className="text-sm text-[#e8622d] mt-0.5">{freeOrderRebateDesc(freeConfirm.order)} = 到手{shoudaoTxt}元</div>
                </div>
              </div>
              <div className="flex gap-3 free-step" style={{ animationDelay: '0.45s' }}>
                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-[#e8622d] text-white flex items-center justify-center text-xs flex-shrink-0">✓</div>
                  <div className="w-0.5 flex-1 bg-[#e8622d] min-h-[26px]" />
                </div>
                <div className="pb-4 flex-1 min-w-0">
                  <div className="font-bold text-[15px]" style={{ color: '#5b3a1e' }}>补贴计算</div>
                  <div className="text-sm text-[#e8622d] mt-0.5">订单免单 {calc.symbol} 补{subsidyTxt}元</div>
                </div>
              </div>
              <div className="flex gap-3 free-step" style={{ animationDelay: '0.9s' }}>
                <div className="flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-[#e8622d] text-white flex items-center justify-center text-xs flex-shrink-0">✓</div>
                </div>
                <div className="pb-4 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-[15px]" style={{ color: '#5b3a1e' }}>为您免单</div>
                    <span className="rounded-full bg-[#a14e21] text-white text-[11px] px-2.5 py-0.5 flex-shrink-0">补贴后 到手0元</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="text-center text-sm pb-3 free-step" style={{ animationDelay: '1.4s', color: '#5b3a1e' }}>
              即将发放 <span className="font-bold text-[#e03e3e]">{subsidyTxt}元</span> 无门槛小蚕红包
            </div>
            <div className="flex gap-3">
              <Button block size="large" onClick={() => setFreeConfirm(null)}>我再想想</Button>
              <Button block size="large" theme="solid" loading={freeSubmitting} onClick={handleFreeOrderUse} style={{ backgroundColor: '#7a4a21' }}>立即使用</Button>
            </div>
          </div>
          );
        })()}

        {/* 步骤三: 发放成功 (官方图四) */}
        {freeDone && (
          <div className="text-center py-4">
            <div className="text-lg font-bold mb-4">恭喜获得{freeDone.amount.toFixed(2)}元红包</div>
            <div className="mx-auto w-28 h-32 rounded-2xl border-2 border-[#e03e3e] bg-white shadow-md flex flex-col items-center justify-center gap-1 free-pop">
              <div className="text-[#e03e3e] text-xs">¥{freeDone.amount.toFixed(2)}</div>
              <div className="rounded-b-2xl bg-[#e03e3e] text-white text-xs px-3 py-1 -mb-6">外卖红包</div>
            </div>
            <div className="text-xs text-semi-color-text-2 mt-6">{freeDone.expire}到期</div>
            <Button theme="solid" type="danger" block size="large" className="mt-4" onClick={() => { setFreeOrderVisible(false); setFreeConfirm(null); setFreeDone(null); }}>
              开心收下
            </Button>
            <div className="text-xs text-semi-color-text-2 mt-2">【我的红包】查看</div>
          </div>
        )}
      </Modal>

      {/* 返利扣除规则弹窗 (对齐小蚕APP官方规则文案) */}
      <Modal
        title="返利扣除规则"
        visible={rebateRuleVisible}
        onCancel={() => setRebateRuleVisible(false)}
        footer={
          <Button theme="solid" block onClick={() => setRebateRuleVisible(false)}>
            知道了
          </Button>
        }
        width={480}
        bodyStyle={{ maxHeight: '60vh', overflowY: 'auto' }}
      >
        <div className="text-sm space-y-3 leading-relaxed">
          <div>
            <div className="font-semibold mb-1">实付不满</div>
            <div className="text-semi-color-text-2">
              <div><Text strong>扣除活动返豆</Text>：外卖订单实付低于满返条件时，活动返豆=满额活动返豆-(活动返豆门槛-实付)。</div>
              <div><Text strong>扣除返利券</Text>：使用返利券下单，返利券返豆=实际活动返豆*返利券额外返(如110%)。返利券额外返豆上限为2豆。</div>
              <div><Text strong>扣除红包</Text>：红包返豆=实际活动返豆/满额活动返豆*满额红包返豆。</div>
              <div><Text strong>最高返利金额</Text>：活动返豆+返利券返豆+红包返豆不能超过该活动的返利门槛和实付金额。</div>
            </div>
          </div>
          <div>
            <div className="font-semibold mb-1">产生退款</div>
            <div className="text-semi-color-text-2">
              实际支付金额达标，但产生退款，若退款后实付金额不满足活动条件，则按实付不满规则扣除返豆。
            </div>
          </div>
          <div>
            <div className="font-semibold mb-1">未包含指定餐品</div>
            <div className="text-semi-color-text-2">
              扣除该笔订单的活动返豆；当订单存在多项异常情况时，优先扣除因未包含活动餐品、订单异常(如实付不满等)产生的返豆，再扣除其他图文反馈异常对应的返豆。
            </div>
          </div>
          <div>
            <div className="font-semibold mb-1">通用计算规则</div>
            <div className="text-semi-color-text-2">
              <div><Text strong>差额取整扣除</Text>：涉及金额差额计算时，均按整数扣除(如计算结果为小数，直接向下取整)。</div>
              <div><Text strong>最低扣除标准</Text>：若实际支付金额不足导致需扣除返豆，最低扣除1豆。</div>
            </div>
          </div>
        </div>
      </Modal>

      {/* 回填/修改外卖单号弹窗 (官方「下单流程」样式, 支持粘贴截图自动识别单号) */}
      <Modal
        title="小蚕霸王餐 · 下单流程"
        visible={!!uploadModalOrder}
        onOk={handleConfirmSubmitId}
        onCancel={() => {
          setUploadModalOrder(null);
          setPlatformOrderIdInput('');
          setModifyMode(false);
        }}
        confirmLoading={submitting}
        okText={modifyMode ? '确认修改单号' : '确认提交单号'}
        cancelText="取消"
        width={440}
        centered
      >
        <div className="space-y-3 py-1" onPaste={handlePasteScreenshot}>
          {(() => {
            // 对齐官方下单流程页: 只展示店铺卡片 + 倒计时 + 提示语 (圈红部分信息)
            const hasExt = Boolean(uploadModalOrder?.platform_order_id);
            const remain = uploadModalOrder?.timeout_time ? uploadModalOrder.timeout_time - nowTick : null;
            const hms = formatRemainingHMS(remain);
            const timedOut = remain !== null && remain <= 0;
            const plat = getPlatformBadge(uploadModalOrder?.platform);
            const avatarSrc = uploadModalOrder?.store_icon || DEFAULT_PLATFORM_ICONS[uploadModalOrder?.platform || 'meituan'];
            const rpRaw = Number(uploadModalOrder?.redpack_reward_num || 0);
            const rpYuan = rpRaw > 5 ? rpRaw / 100 : rpRaw;
            const tagRebate = parseFloat(
              (Math.max(Number(uploadModalOrder?.original_user_rebate || 0), Number(uploadModalOrder?.rebate_money || 0)) + rpYuan).toFixed(2)
            );
            const condTag = (String(uploadModalOrder?.condition || '无需评价')
              .replace(/[（(].*?需含字含图.*?[）)]/g, '')
              .replace(/[（(]需含字含图[）)]/g, '')
              .trim()) || '无需评价';
            const hasRebateTag = Number(uploadModalOrder?.original_user_rebate || 0) > 0 && Number(uploadModalOrder?.order_money || 0) > 0;
            return (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--semi-color-border-subtle)' }}>
                <div className="flex items-center gap-2.5 p-3">
                  <Avatar size="medium" shape="square" src={avatarSrc} color={plat.avatarColor} className="flex-shrink-0">
                    {uploadModalOrder?.store_name?.[0] || '外'}
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Tag color={plat.color} size="small" shape="square" className="flex-shrink-0">{plat.label}</Tag>
                      <Text strong ellipsis={{ showTooltip: true }} style={{ maxWidth: 190 }}>
                        {uploadModalOrder?.store_name}
                      </Text>
                      {hasRebateTag && (
                        <Tag color="red" size="small" shape="square" className="flex-shrink-0">
                          满{uploadModalOrder?.order_money}返{tagRebate}
                        </Tag>
                      )}
                      <Tag color="grey" size="small" shape="square" className="flex-shrink-0">
                        {normalizeConditionText(condTag)}
                      </Tag>
                    </div>
                  </div>
                </div>
                <div className="px-3 pb-1 text-center text-[13px] text-semi-color-text-1">
                  请在{' '}
                  <span className="font-mono font-semibold" style={{ color: 'var(--semi-color-warning-2)' }}>
                    {timedOut ? '已超时' : (hms || '--:--:--')}
                  </span>{' '}
                  内{hasExt ? '上传订单完成截图' : '提交外卖单号'}
                </div>
                <div className="px-3 pb-3 pt-1 text-center text-[15px] font-medium text-semi-color-text-0">
                  {hasExt ? (
                    <>收到外卖后，请返回小蚕<br />上传订单完成截图</>
                  ) : (
                    <>完成下单后，请返回小蚕<br />提交外卖单号</>
                  )}
                </div>
              </div>
            );
          })()}
          <div>
            <Text size="small" type="secondary" className="block mb-1">
              请输入外卖平台订单号：
            </Text>
            <Input
              placeholder="例如：3002311852210111003"
              value={platformOrderIdInput}
              onChange={(val) => setPlatformOrderIdInput(val || '')}
              autoFocus
            />
            <Banner
              type="info"
              className="rounded-lg text-xs mt-2"
              description={
                ocrLoading
                  ? '正在识别截图中的单号...'
                  : '一键识别：将鼠标停在订单详情页上按 Alt+Q，系统自动截屏识别并滚动翻页（识别不到会自动滚屏重试）；也可截图后按 Ctrl+V 粘贴识别，或手动输入'
              }
              closeIcon={null}
            />
          </div>

          {/* 取号三步引导 (内嵌展示, 不再单独弹窗) */}
          <div className="pt-1 border-t border-semi-color-border-subtle flex flex-col gap-2.5">
            <Text strong size="small">取号三步 (30 秒搞定)</Text>
            <div className="flex gap-2.5 items-start">
              <Tag color="blue" size="small" shape="circle" className="!mt-0.5 flex-shrink-0">1</Tag>
              <div className="flex-1">
                <Text strong size="small">复制对照信息</Text>
                <div className="text-xs text-semi-color-text-2 mt-0.5 leading-4">
                  复制店铺名与门槛金额，在美团/淘宝闪购订单列表按这两项快速定位这笔订单。
                </div>
                <Button
                  size="small"
                  theme="light"
                  className="mt-1.5"
                  onClick={() => {
                    const info = `${uploadModalOrder?.store_name || ''} ¥${uploadModalOrder?.order_money || 0}`;
                    navigator.clipboard.writeText(info).then(
                      () => Toast.success(`已复制: ${info}`),
                      () => Toast.error('复制失败，请手动记录')
                    );
                  }}
                >
                  复制店铺名与金额
                </Button>
              </div>
            </div>
            <div className="flex gap-2.5 items-start">
              <Tag color="blue" size="small" shape="circle" className="!mt-0.5 flex-shrink-0">2</Tag>
              <div className="flex-1">
                <Text strong size="small">进入外卖小程序订单页</Text>
                <div className="text-xs text-semi-color-text-2 mt-0.5 leading-4">
                  点击下方按钮唤起 PC 微信并直达对应外卖小程序；若未直达，在小程序面板搜索
                  <Text strong size="small">
                    {uploadModalOrder?.platform === 'eleme' ? '「淘宝闪购」' : uploadModalOrder?.platform === 'jingdong' ? '「京东外卖」' : '「美团外卖」'}
                  </Text>
                  打开【订单】列表找到这笔订单。
                </div>
                <Button
                  size="small"
                  theme="light"
                  type="primary"
                  className="mt-1.5"
                  onClick={() => {
                    const platform = uploadModalOrder?.platform || 'meituan';
                    // 各平台微信小程序 appid:
                    //   美团外卖 wx2c348cf579062e56 (订单页 pages/order/order, 见微信开放社区)
                    //   饿了么/淘宝闪购 wxece3a9a4c82f58c9 (公开可查; 订单页 path 无公开可靠来源, 落首页后点底部订单)
                    //   京东外卖/京东秒送: 2026-02 上线微信但 appid 无公开渠道, 暂走主窗兜底
                    // PC 微信不支持 dl/business 时仍会唤起微信主窗
                    let url = 'weixin://';
                    let tip = '请打开 PC 微信 → 小程序面板 → 搜索「京东外卖」→ 订单';
                    if (platform === 'meituan') {
                      url = 'weixin://dl/business/?appid=wx2c348cf579062e56&path=pages%2Forder%2Forder';
                      tip = '若未直达订单页：PC 微信 → 小程序面板 → 搜索「美团外卖」→ 订单';
                    } else if (platform === 'eleme') {
                      url = 'weixin://dl/business/?appid=wxece3a9a4c82f58c9';
                      tip = '若未直达：PC 微信 → 小程序面板 → 搜索「淘宝闪购」→ 底部「订单」→ 进入该笔订单';
                    }
                    window.location.href = url;
                    setTimeout(() => {
                      Toast.info(tip);
                    }, 1500);
                  }}
                >
                  进入外卖小程序
                </Button>
              </div>
            </div>
            <div className="flex gap-2.5 items-start">
              <Tag color="blue" size="small" shape="circle" className="!mt-0.5 flex-shrink-0">3</Tag>
              <div className="flex-1">
                <Text strong size="small">取号并回填</Text>
                <div className="text-xs text-semi-color-text-2 mt-0.5 leading-4">
                  鼠标停在订单详情页按 <Text code size="small">Alt+Q</Text> 一键截屏识别（自动滚动翻页）；
                  或复制单号填入上方输入框；或截图后回本弹窗按 <Text code size="small">Ctrl+V</Text> 自动识别。
                </div>
              </div>
            </div>
          </div>
          <Banner
            type="warning"
            description={
              modifyMode
                ? '修改将覆盖官方当前绑定的外卖单号（对应官方订单详情页「修改」），请务必核对新单号正确'
                : '单号提交后官方将锁定绑定关系，如需变更请使用「修改单号」，请务必核对正确'
            }
            className="rounded-lg text-xs"
          />
          {(uploadModalOrder?.order_type === 12 || Number(uploadModalOrder?.rebate_ratio || 0) > 0) && (
            <Banner
              type="info"
              className="rounded-lg text-xs"
              description="活动返利将在订单完成 24 小时后发放至美团钱包，红包、返利券额外返利将发放至蚕豆余额"
              closeIcon={null}
            />
          )}
        </div>
      </Modal>
    </div>
  );
};
export default OrdersView;
