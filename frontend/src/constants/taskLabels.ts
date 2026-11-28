export const TASK_LABELS: Record<string, string> = {
  // 霸王餐抢单与预约
  store_grab: '霸王餐即时抢单',
  store_appoint: '倒计时预约抢单',
  store_monitor: '实时抢单名额监听',
  store_keyword: '商户定时搜索捡漏',
  store_search: '商户定向搜索捡漏',
  store_cancel: '霸王餐名额取消',

  // 订单特权与业务操作
  delay_card: '使用延时券',
  delay_voucher: '领红包延时',
  order_bind: '回填外卖单号',
  flash_exchange: '元宝秒杀兑换',
  account_sync: '官方资产同步',
  token_capture: '抓包凭据捕获',
  notify_test: '通知推送测试',

  // 日常自动化任务
  yb_task: '轻松赚元宝',
  daily: '元宝乐园综合打卡',
  collect_points: '收取未收元宝',
  group_lottery: '免费开红包与抽奖',
  redpack_rain: '整点红包雨',
  flash_sale: '元宝秒杀抢券',
  vip_expand: '会员每日签到',
  vip_rights_claim: '会员权益自动领取',
  brand_flash: '大牌畅享秒杀',
  svip_rebate: 'SVIP高额返利券',
  media_vip: '影音会员周卡',
  free_order: '订单全额免单券',
  expire_remind: '凭据/JWT到期预警',
  coupon_remind: '卡券/红包到期提醒',
  auto_withdraw: '账户佣金自动提现',

  // 双返与美团能力
  dual_rebate_scan: '同店双返扫描',
  dual_rebate_monitor: '同店双返监控',
  meituan_coupon: '美团官方领券打卡',
  meituan_auth: '美团官方扫码授权',

  // 历史任务 ID 兼容
  user_sign: '每日签到打卡',
  vip_task: '会员日常成长任务',
  daily_redpack: '每日全平台红包雨',
  lottery: '免费开红包与抽奖',
  step_reward: '阶段阶梯奖励领取',
  check_assets: '全资产与明细轮询',
  token_refresh: '多账号鉴权状态巡检',
};

export const STORE_TASK_KEYS = new Set([
  'store_grab',
  'store_appoint',
  'store_monitor',
  'store_keyword',
  'store_search',
  'store_cancel',
  'dual_rebate_scan',
  'dual_rebate_monitor',
]);

export const ORDER_PRIVILEGE_TASK_KEYS = new Set([
  'delay_card',
  'delay_voucher',
]);

export const getTaskLabel = (taskId?: string): string => {
  if (!taskId) return '调度任务';
  return TASK_LABELS[taskId] || `任务 [${taskId}]`;
};
