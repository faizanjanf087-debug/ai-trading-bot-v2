"""Watchlist ke pairs ko waqfe waqfe scan karta hai; achha setup mile to approved users ko signal bhejta hai."""
import asyncio
import json
import logging
import re
import time
from typing import Awaitable, Callable, Dict, Optional, Tuple

from ai import prompts
from ai.deepseek_client import AIError
from config.markets import SYMBOLS
from data.base import BudgetExhausted, DataError
from data.sessions import forex_open, in_session
from services import formatter

log = logging.getLogger(__name__)
Notify = Callable[[int, str], Awaitable[None]]


def parse_ai_review(text: str) -> Optional[dict]:
    """AI ke jawab se JSON nikalo. Na mile to None."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    verdict = str(d.get("verdict", "")).lower()
    if verdict not in ("take", "skip"):
        return None
    try:
        conf = int(float(d.get("confidence", 0)))
    except (TypeError, ValueError):
        conf = 0
    return {"verdict": verdict, "confidence": conf, "comment": str(d.get("comment", ""))[:300]}


class Scanner:
    def __init__(self, settings, analysis, signal_service, users, ai, news, notify: Notify,
                 watchlist, clock=time.time, calendar=None):
        self.s = settings
        self.analysis = analysis
        self.signals = signal_service
        self.users = users
        self.ai = ai
        self.news = news
        self.notify = notify
        self.watchlist = watchlist
        self.clock = clock
        self.calendar = calendar
        self._last_scan: Dict[Tuple[str, str], float] = {}

    def _modes(self, symbol: str):
        return self.s.forex_modes if SYMBOLS[symbol]["kind"] == "forex" else self.s.crypto_modes

    def _due(self, symbol: str, mode: str, now: float) -> bool:
        minutes = self.s.forex_scan_minutes if SYMBOLS[symbol]["kind"] == "forex" else self.s.crypto_scan_minutes
        return now - self._last_scan.get((symbol, mode), 0) >= minutes * 60

    def _review(self, analysis: dict, setup: dict) -> Optional[dict]:
        if not self.ai.enabled:
            return None
        kind = SYMBOLS[analysis["symbol"]]["kind"]
        try:
            news = self.news.context(kind) if self.news else ""
            cal = self.calendar.context(analysis["symbol"]) if self.calendar else ""
            news = "\n\n".join(x for x in (news, cal) if x)
            return parse_ai_review(self.ai.chat(prompts.signal_review_prompt(analysis, setup, news),
                                                temperature=0.2, max_tokens=300))
        except AIError as e:
            log.warning("AI review fail: %s", e)
            return None

    async def scan_once(self) -> int:
        """Ek round. Kitne naye signals bane, wapas deta hai."""
        now = self.clock()
        targets = self.users.broadcast_targets()
        if not targets:
            return 0
        created = 0
        for symbol in self.watchlist.get():
            meta = SYMBOLS[symbol]
            if meta["kind"] == "forex" and (not forex_open(now) or not in_session(now, self.s.session_utc)):
                continue
            for mode in self._modes(symbol):
                if not self._due(symbol, mode, now):
                    continue
                self._last_scan[(symbol, mode)] = now
                if self.calendar is not None:        # bari khabar ke aas-paas auto signal nahi (credit bhi bachta hai)
                    ev = self.calendar.blackout(symbol, now, self.s.news_blackout_before_min, self.s.news_blackout_after_min)
                    if ev:
                        log.info("%s: news blackout (%s %s), scan chhod diya", symbol, ev["currency"], ev["title"])
                        continue
                try:
                    a, setup = await asyncio.to_thread(self.analysis.run_fresh, symbol, mode, "normal")
                except BudgetExhausted:
                    log.info("Credits kam, %s scan chhod diya", symbol)
                    break
                except DataError as e:
                    log.warning("Scan data error %s: %s", symbol, e)
                    continue
                if not setup:
                    continue
                if not self.signals.can_create(symbol, setup["side"], mode, self.s.signal_cooldown_minutes * 60):
                    continue
                review = await asyncio.to_thread(self._review, a, setup)
                if review and self.s.ai_veto and review["verdict"] == "skip":
                    log.info("AI ne %s signal skip kiya", symbol)
                    continue
                note = f"{review['verdict'].upper()} ({review['confidence']}%): {review['comment']}" if review else None
                sig = self.signals.create(setup, "scan", targets, ai_note=note, analysis=a, review=review)
                text = formatter.format_signal(sig)
                for uid in targets:
                    try:
                        await self.notify(uid, text)
                    except Exception:
                        log.warning("Signal nahi gaya user %s ko", uid, exc_info=True)
                created += 1
        return created

    async def run(self, every: float = 30) -> None:
        while True:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scanner round fail")
            await asyncio.sleep(every)
