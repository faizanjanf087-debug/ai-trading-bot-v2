"""Twelve Data free plan (8/minute, 800/day) ka hisaab. Har request 1 credit."""
import time
from collections import deque

from db.kv import KV


class CreditBudget:
    def __init__(self, kv: KV, per_minute: int = 8, per_day: int = 800,
                 monitor_reserve: int = 250, clock=time.time):
        self.kv = kv
        self.per_minute = per_minute
        self.per_day = per_day
        self.monitor_reserve = monitor_reserve
        self.clock = clock
        self._recent = deque()

    def _day_key(self) -> str:
        return "td_credits:" + time.strftime("%Y-%m-%d", time.gmtime(self.clock()))

    def used_today(self) -> int:
        return int(self.kv.get(self._day_key(), "0"))

    def remaining_today(self) -> int:
        return max(0, self.per_day - self.used_today())

    def try_spend(self, n: int = 1, priority: str = "normal") -> bool:
        """priority='monitor' reserve wale credits bhi use kar sakti hai; 'normal' nahi."""
        now = self.clock()
        while self._recent and now - self._recent[0] >= 60:
            self._recent.popleft()
        if len(self._recent) + n > self.per_minute:
            return False
        used = self.used_today()
        limit = self.per_day if priority == "monitor" else self.per_day - self.monitor_reserve
        if used + n > limit:
            return False
        for _ in range(n):
            self._recent.append(now)
        self.kv.set(self._day_key(), str(used + n))
        return True
