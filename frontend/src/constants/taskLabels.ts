/**
 * 任务 ID → 中文名称映射 (统一由 LogsView 列表与 LogDetailModal 详情弹窗共用)
 * 新增任务时在此处补充映射即可
 */
export const TASK_LABELS: Record<string, string> = {
  // 霸王餐抢单与预约
  store_grab: '霸王餐即时抢单',
  store_appoint: '倒计时预约抢单',
  store_monitor: '实时名额监听捡漏',
  store_keyword: '商户定时搜索捡漏',
  store_search: '商户定向搜索捡漏',
  store_cancel: '霸王餐名额取消',

  // 日常自动化任务 (现役)
  yb_task: '领天天赚元宝',
  yb_sign: '天天赚元宝签到',
  collect_points: '收取未收元宝',
  daily: '元宝乐园综合打卡',
  group_lottery: '免费开红包与抽奖',
  redpack_rain: '整点红包雨',
  flash_sale: '元宝秒杀抢券',
  vip_expand: '会员每日签到',
  brand_flash: '大牌畅享秒杀',
  svip_rebate: 'SVIP高额返利券',
  media_vip: '影音会员周卡',
  free_order: '订单全额免单券',
  expire_remind: '凭据/JWT到期预警',
  coupon_remind: '卡券/红包到期提醒',
  dual_rebate_monitor: '美团同店双返利监控',
  meituan_coupon: '美团官方领券打卡',
  meituan_auth: '美团官方扫码授权',
  clawbot_alert: '微信 ClawBot 会话提醒',
  notify_health: '通知通道连通性巡检',

  // 历史日志兼容 (旧版键名, 避免历史记录显示原始 ID)
  user_sign: '每日签到打卡',
  sign_in_lottery: '天天赚元宝抽奖',
  vip_task: '会员日常成长任务',
  daily_redpack: '每日全平台红包雨',
  lottery: '免费开红包与抽奖',
  step_reward: '阶段阶梯打卡进度领取',
  auto_withdraw: '账户佣金自动提现',
  check_assets: '全资产与明细轮询',
  token_refresh: '多账号鉴权状态巡检',
};

/** 商家抢单类任务键集合 (用于列表分类筛选) */
export const STORE_TASK_KEYS = new Set([
  'store_grab',
  'store_appoint',
  'store_monitor',
  'store_keyword',
  'store_search',
  'store_cancel',
]);

export const getTaskLabel = (taskId: string): string =>
  TASK_LABELS[taskId] || (taskId ? `任务 [${taskId}]` : '调度任务');
