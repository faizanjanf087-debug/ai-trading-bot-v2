"""Free chat: user likhe to DeepSeek jawab de, memory + signals + (zaroorat par) live analysis ke saath."""
import asyncio
import json
import logging
from typing import Optional

from ai import prompts
from ai.deepseek_client import AIError
from config.markets import MODES, SYMBOLS, find_symbols_in_text
from data.base import DataError
from services import formatter

log = logging.getLogger(__name__)


class ChatService:
    def __init__(self, ai_client, memory, analysis_service, news, signal_repo, calendar=None, discipline=None):
        self.ai = ai_client
        self.memory = memory
        self.analysis = analysis_service
        self.news = news
        self.signal_repo = signal_repo
        self.calendar = calendar
        self.discipline = discipline

    def _user_context(self, user_id: int) -> str:
        open_sigs = self.signal_repo.open_for_user(user_id)
        closed = self.signal_repo.closed_for_user(user_id, 3)
        st = self.signal_repo.stats(user_id)
        parts = []
        if open_sigs:
            parts.append("User ke open signals (database ka asli status):\n" + "\n".join(formatter.format_signal_line(s) for s in open_sigs))
        else:
            parts.append("User ka koi open signal nahi.")
        if closed:
            parts.append("User ke aakhri band signals (asli status):\n" + "\n".join(formatter.format_signal_line(s) for s in closed))
        parts.append(f"User ke band signals: {st['closed']} (wins {st['wins']}, losses {st['losses']}, net {st['net_r']}R)")
        if self.discipline is not None:
            try:
                parts.append(self.discipline.context_text(user_id))
            except Exception:
                log.warning("Discipline context fail", exc_info=True)
        return "\n".join(parts)

    def _market_context(self, text: str) -> str:
        out = []
        for sym in find_symbols_in_text(text, limit=2):
            try:
                a, setup = self.analysis.run(sym, "scalp")
            except DataError as e:
                out.append(f"{sym}: data abhi available nahi ({e})")
                continue
            if a is None:
                out.append(f"{sym}: analysis ke liye candles kam hain")
                continue
            compact = prompts._compact(a)
            out.append(f"{sym} live analysis: {json.dumps(compact, default=str)}"
                       + (f"\nSetup: {json.dumps({k: setup[k] for k in ('side','entry_type','entry','sl','tp1','tp2')}, default=str)}" if setup else "\nKoi saaf setup nahi."))
            kind = SYMBOLS[sym]["kind"]
            news = self.news.context(kind) if self.news else ""
            if news:
                out.append(news)
            cal = self.calendar.context(sym) if self.calendar else ""
            if cal:
                out.append(cal)
        return "\n\n".join(out)

    def reply_blocking(self, user_id: int, text: str, hint: str = "", extra: str = "") -> str:
        if not self.ai.enabled:
            return "AI abhi band hai (DEEPSEEK_API_KEY set nahi). Commands use karein: /help"
        context = self._user_context(user_id)
        market = self._market_context(text)
        if extra:
            market = (market + "\n\n" if market else "") + extra
        messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "system", "content": "Context:\n" + context + ("\n\n" + market if market else "")}]
        if hint:
            messages.append({"role": "system", "content": hint})
        messages += self.memory.history_messages(user_id)
        messages.append({"role": "user", "content": text})
        try:
            reply = self.ai.chat(messages)
        except AIError as e:
            log.warning("AI error: %s", e)
            return "AI se jawab nahi mil saka, thori der baad try karein."
        self.memory.remember(user_id, text, reply)
        try:
            self.memory.maybe_summarize(user_id)
        except Exception:
            log.warning("Summary fail", exc_info=True)
        return reply

    async def reply(self, user_id: int, text: str, hint: str = "", extra: str = "") -> str:
        return await asyncio.to_thread(self.reply_blocking, user_id, text, hint, extra)
