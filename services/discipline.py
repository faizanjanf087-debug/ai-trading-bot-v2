"""Trading discipline: user ke apne signal record se loss streak, ziyada trading aur revenge-trade ka khatra pehchanna.

Yeh sirf yaad-dehani hai, bot signal rokta nahi: faisla hamesha user ka hai.
Sab figures database se aate hain (AI ka andaza nahi).
"""
import time
from typing import List, Optional

DAY = 86400
REVENGE_WINDOW_MIN = 30
REAL_OUTCOMES = ("TP2", "SL", "BE")


class DisciplineService:
    def __init__(self, signal_repo, clock=time.time, loss_streak_warn: int = 3,
                 daily_loss_limit_r: float = 3.0, max_signals_per_day: int = 6):
        self.repo = signal_repo
        self.clock = clock
        self.loss_streak_warn = loss_streak_warn
        self.daily_loss_limit_r = daily_loss_limit_r
        self.max_signals_per_day = max_signals_per_day

    def snapshot(self, user_id: int) -> dict:
        now = self.clock()
        closed = self.repo.closed_for_user(user_id, 30)           # sab se naya pehle
        opened = self.repo.open_for_user(user_id)
        outcomes = [s for s in closed if s["status"] in REAL_OUTCOMES and s.get("result_r") is not None]
        streak = 0
        for s in outcomes:
            if s["result_r"] < 0:
                streak += 1
            else:
                break
        r_24h = sum(s["result_r"] for s in outcomes if (s.get("closed_ts") or 0) >= now - DAY)
        n_24h = sum(1 for s in opened + closed if (s.get("created_ts") or 0) >= now - DAY)
        since_loss: Optional[float] = None
        if outcomes and outcomes[0]["result_r"] < 0 and outcomes[0].get("closed_ts"):
            since_loss = (now - outcomes[0]["closed_ts"]) / 60
        return {"loss_streak": streak, "r_24h": round(r_24h, 2), "signals_24h": n_24h,
                "minutes_since_loss": since_loss, "open": len(opened)}

    def warnings(self, user_id: int, snap: Optional[dict] = None) -> List[str]:
        s = snap or self.snapshot(user_id)
        out: List[str] = []
        if s["r_24h"] <= -abs(self.daily_loss_limit_r):
            out.append(f"🛑 Pichle 24 ghante mein {s['r_24h']:+.1f}R. Apni limit ({self.daily_loss_limit_r:g}R) par "
                       "pahunch gaye hain; aaj aur trade se behtar hai ruk jayein.")
        if s["loss_streak"] >= self.loss_streak_warn:
            out.append(f"⚠️ Lagatar {s['loss_streak']} loss. Thora break lein, risk chhota rakhein, aur loss wapas "
                       "lene ki jaldi na karein.")
        elif s["minutes_since_loss"] is not None and s["minutes_since_loss"] < REVENGE_WINDOW_MIN:
            out.append(f"⏱ Abhi {int(s['minutes_since_loss'])} minute pehle loss hua hai. Naya trade lene se pehle "
                       f"{REVENGE_WINDOW_MIN} minute ruk kar sochein (revenge trade se bachne ke liye).")
        if s["signals_24h"] >= self.max_signals_per_day:
            out.append(f"⚠️ 24 ghante mein {s['signals_24h']} signals. Zyada trading aksar nuqsan deti hai; "
                       "quantity nahi, quality dekhein.")
        return out

    def context_text(self, user_id: int) -> str:
        """AI ke liye: user ki asli halat (taake tasalli andaze par nahi, hisaab par ho)."""
        s = self.snapshot(user_id)
        parts = [f"Discipline (database se): lagatar loss {s['loss_streak']}, pichle 24h ka natija {s['r_24h']:+.1f}R, "
                 f"pichle 24h ke signals {s['signals_24h']}."]
        parts += [w.split(" ", 1)[1] for w in self.warnings(user_id, s)]
        return " ".join(parts)

    def format_summary(self, user_id: int) -> str:
        s = self.snapshot(user_id)
        lines = ["🧭 Aap ka discipline (apne signals ke hisaab se)",
                 f"Lagatar loss: {s['loss_streak']}",
                 f"Pichle 24 ghante ka natija: {s['r_24h']:+.1f}R (limit {self.daily_loss_limit_r:g}R)",
                 f"Pichle 24 ghante ke signals: {s['signals_24h']} (hadd {self.max_signals_per_day})",
                 f"Abhi open signals: {s['open']}"]
        w = self.warnings(user_id, s)
        lines += [""] + w if w else ["", "✅ Abhi koi tanbeeh nahi. Isi tarah risk chhota aur rules par qayam rahein."]
        lines.append("\nYeh sirf yaad-dehani hai; bot aap ko trade se rokta nahi.")
        return "\n".join(lines)
