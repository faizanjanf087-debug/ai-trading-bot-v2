"""Open signals aur price alerts ko dekhta rehta hai aur alert bhejta hai."""
import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, List

from config.markets import SYMBOLS
from data.base import BudgetExhausted, DataError
from data.sessions import forex_open
from services import formatter

log = logging.getLogger(__name__)

Notify = Callable[[int, str], Awaitable[None]]


def candles_to_tuples(df) -> List[tuple]:
    return [
        (int(ts.timestamp()), float(r.open), float(r.high), float(r.low), float(r.close))
        for ts, r in zip(df.index, df.itertuples())
    ]


class PriceWatcher:
    """Crypto har ~30 second; forex Twelve Data ke credits dekh kar (default 5 minute, budget kam ho to zyada)."""

    def __init__(self, market, signal_service, alert_repo, notify: Notify, budget=None,
                 crypto_interval: int = 30, forex_interval: int = 300, clock=time.time):
        self.market = market
        self.signals = signal_service
        self.alerts = alert_repo
        self.notify = notify
        self.budget = budget
        self.crypto_interval = crypto_interval
        self.forex_interval = forex_interval
        self.clock = clock
        self._last_poll: Dict[str, float] = {}
        self._warned_budget = False

    def _interval(self, symbol: str, n_forex_symbols: int) -> float:
        if SYMBOLS[symbol]["provider"] != "twelvedata":
            return self.crypto_interval
        interval = self.forex_interval
        if self.budget and n_forex_symbols:
            # Reserve credits ko poore din mein baantne par har symbol ka minimum interval
            per_day = max(1, self.budget.monitor_reserve)
            interval = max(interval, 86400 * n_forex_symbols / per_day)
        return min(interval, 840)   # 1m candles ke 15 ka window: is se zyada gap par touch miss ho sakta hai

    def _symbols_needed(self) -> Dict[str, dict]:
        need: Dict[str, dict] = {}
        for s in self.signals.signals.list_open():
            need.setdefault(s["symbol"], {"signals": [], "alerts": []})["signals"].append(s)
        for a in self.alerts.active():
            need.setdefault(a["symbol"], {"signals": [], "alerts": []})["alerts"].append(a)
        return need

    async def tick(self) -> None:
        now = self.clock()
        need = self._symbols_needed()
        forex_syms = [s for s in need if SYMBOLS[s]["provider"] == "twelvedata"]
        for symbol, items in need.items():
            meta = SYMBOLS[symbol]
            if meta["kind"] == "forex" and not forex_open(now):
                continue
            if now - self._last_poll.get(symbol, 0) < self._interval(symbol, len(forex_syms)):
                continue
            try:
                df = await asyncio.to_thread(self.market.get_recent_1m, symbol, 15, "monitor")
            except BudgetExhausted:
                if not self._warned_budget:
                    self._warned_budget = True
                    log.warning("Twelve Data credits khatam; monitoring ruk gayi.")
                continue
            except DataError as e:
                log.warning("Monitor data error %s: %s", symbol, e)
                self._last_poll[symbol] = now      # bar bar na maaren
                continue
            self._last_poll[symbol] = now
            candles = candles_to_tuples(df)
            await self._process(items, candles)

    async def _process(self, items: dict, candles: List[tuple]) -> None:
        for sig in items["signals"]:
            events = self.signals.process(sig, candles)
            if not events:
                continue
            fresh = self.signals.signals.get(sig["id"])
            recipients = self.signals.recipients(sig["id"])
            for text in formatter.format_events(fresh, events):
                for uid in recipients:
                    await self._send(uid, text)
        for a in items["alerts"]:
            hit = None
            for ts, o, h, l, c in candles:
                if ts < a["created_ts"] - 60:
                    continue
                if (a["direction"] == "above" and h >= a["price"]) or (a["direction"] == "below" and l <= a["price"]):
                    hit = c
                    break
            if hit is not None:
                self.alerts.trigger(a["id"], int(self.clock()))
                await self._send(a["user_id"], formatter.format_alert_hit(a, hit))

    async def _send(self, user_id: int, text: str) -> None:
        try:
            await self.notify(user_id, text)
        except Exception:
            log.warning("Alert nahi gaya user %s ko", user_id, exc_info=True)

    async def run(self, every: float = 15) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("PriceWatcher tick fail")
            await asyncio.sleep(every)
