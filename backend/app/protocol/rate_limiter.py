"""
全局请求限速与 WAF 冷却平滑恢复

设计目标(纯软件层, 不与风控对抗):
1. 全局令牌桶: 所有任务(抢单监听 / 秒杀 / 红包雨 / 每日任务 / 订单同步等)共享同一个 RPS 上限,
   避免多个任务同时开火叠加速率, 这是多任务场景下触发腾讯云 WAF 的最常见原因。
2. 平滑恢复: 触发 WAF 冷却后清空令牌, 冷却结束后的若干秒内以半速放行, 避免解封瞬间全速冲击再次被拦。
"""

import asyncio
import time


class GlobalRateLimiter:
    """异步令牌桶 (单进程共享)"""

    def __init__(self, rate: float = 8.0, burst: int = 12):
        self._rate = float(rate)
        self._burst = max(1, int(burst))
        self._tokens = float(self._burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()
        self._recover_until = 0.0

    @property
    def rate(self) -> float:
        return self._rate

    def set_rate(self, rate: float, burst: int = None):
        """动态调整全局 RPS 上限 (rate<=0 表示不限速)"""
        self._rate = max(0.0, float(rate))
        if burst is not None:
            self._burst = max(1, int(burst))
        self._tokens = float(self._burst)
        self._last = time.monotonic()

    def penalize(self, seconds: float):
        """WAF 冷却: 清空令牌, 冷却结束后 5 秒内半速平滑恢复"""
        self._tokens = 0.0
        self._last = time.monotonic()
        self._recover_until = time.monotonic() + max(1.0, float(seconds)) + 5.0

    async def acquire(self):
        """获取一个令牌; 不足时按当前速率精确等待 (循环补算, 保证实际速率与配置一致)"""
        if self._rate <= 0:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                cur_rate = self._rate
                if time.monotonic() < self._recover_until:
                    cur_rate = self._rate * 0.5  # 平滑恢复期半速
                self._tokens = min(float(self._burst), self._tokens + elapsed * cur_rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / cur_rate if cur_rate > 0 else 0.2
                await asyncio.sleep(min(max(wait, 0.005), 1.0))


# 全局单例: 默认 8 次/秒(突发 20), 约为官方正常用户操作速率的数倍, 兼顾抢单时效与风控安全
GLOBAL_LIMITER = GlobalRateLimiter(rate=8.0, burst=20)


def set_global_rate(rate: float, burst: int = None):
    GLOBAL_LIMITER.set_rate(rate, burst)
