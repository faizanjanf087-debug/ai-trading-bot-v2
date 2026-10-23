"""Signals banana, tracking update karna, results save karna."""
import logging
import time
from typing import List, Optional

from db.signals import SignalRepo
from db.users import UserRepo
from services import lifecycle

log = logging.getLogger(__name__)

UPDATE_FIELDS = ("status", "sl", "activated_ts", "closed_ts", "result_r", "last_candle_ts")


class SignalService:
    def __init__(self, signals: SignalRepo, users: UserRepo, clock=time.time,
                 breakeven_after_tp1: bool = True, journal=None):
        self.signals = signals
        self.users = users
        self.clock = clock
        self.breakeven = breakeven_after_tp1
        self.journal = journal

    def create(self, setup: dict, source: str, recipients: List[int], owner_id: Optional[int] = None,
               ai_note: Optional[str] = None, analysis: Optional[dict] = None,
               review: Optional[dict] = None) -> dict:
        now = int(self.clock())
        market_entry = setup["entry_type"] == "MARKET"
        signal = {
            "symbol": setup["symbol"], "mode": setup["mode"], "side": setup["side"],
            "entry_type": setup["entry_type"], "entry": setup["entry"], "sl": setup["sl"],
            "tp1": setup["tp1"], "tp2": setup["tp2"], "score": setup["score"],
            "reason": "; ".join(setup["reasons"]), "ai_note": ai_note, "source": source,
            "owner_id": owner_id, "created_ts": now,
            "expires_ts": now + setup["pending_bars"] * setup["tf_seconds"],
            "status": "ACTIVE" if market_entry else "PENDING",
            "activated_ts": now if market_entry else None,
            # Monitoring 1-minute candles se hoti hai: bani hui minute ke baad wali candles dekhni hain
            "last_candle_ts": (now // 60) * 60 + 60,
        }
        sid = self.signals.create(signal)
        if market_entry:
            self.signals.add_event(sid, "ENTRY_HIT", setup["entry"], now, "Market entry")
        for uid in recipients:
            self.signals.add_delivery(sid, uid)
        if self.journal is not None:
            try:      # journal ki kharabi se signal nahi rukna chahiye
                self.journal.add(sid, setup, analysis, review, now, source)
            except Exception:
                log.warning("Journal mein signal %s nahi likha ja saka", sid, exc_info=True)
        return self.signals.get(sid)

    def can_create(self, symbol: str, side: str, mode: str, cooldown_seconds: int = 0) -> bool:
        if self.signals.has_open(symbol, side, mode):
            return False
        last = self.signals.last_created_ts(symbol)
        return not (last and self.clock() - last < cooldown_seconds)

    def process(self, signal: dict, candles) -> List[dict]:
        """Naye candles dekh kar signal ka status badlo. Events wapas karta hai (alerts ke liye)."""
        updated, events = lifecycle.evaluate(signal, candles, int(self.clock()), self.breakeven)
        fields = {k: updated[k] for k in UPDATE_FIELDS if updated.get(k) != signal.get(k)}
        if fields:
            self.signals.update(signal["id"], **fields)
        for e in events:
            self.signals.add_event(signal["id"], e["type"], e["price"], e["ts"], e.get("note", ""))
        return events

    def recipients(self, signal_id: int) -> List[int]:
        return self.signals.recipients(signal_id)
