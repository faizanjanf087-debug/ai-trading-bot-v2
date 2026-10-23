"""Analysis journal: har signal ke waqt market ka snapshot. Nateeja (win/loss) signals table se join hota hai."""
import json
from typing import List, Optional

from analysis.factors import factor_keys, htf_alignment
from db.database import Database
from db.signals import OPEN_STATUSES


class JournalRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, signal_id: int, setup: dict, analysis: Optional[dict] = None, review: Optional[dict] = None,
            now: int = 0, source: Optional[str] = None) -> None:
        a = analysis or {}
        r = review or {}
        side = setup["side"]
        htf = a.get("htf_trend")
        self.db.execute(
            """INSERT OR IGNORE INTO analysis_journal
               (signal_id, created_ts, symbol, mode, tf, side, entry_type, source, price, atr, rsi,
                htf_trend, htf_alignment, macd_cross, divergence, score, score_buy, score_sell,
                factors, ai_verdict, ai_confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                signal_id, now, setup["symbol"], setup["mode"], setup.get("tf"), side, setup.get("entry_type"),
                source, a.get("price"), a.get("atr", setup.get("atr")), a.get("rsi"), htf,
                htf_alignment(side, htf) if htf else None, a.get("macd_cross"), a.get("divergence"),
                setup.get("score"), a.get("score_buy"), a.get("score_sell"),
                json.dumps(factor_keys(setup.get("reasons", []))),
                r.get("verdict"), r.get("confidence"),
            ),
        )

    def get(self, signal_id: int) -> Optional[dict]:
        rows = self.db.query("SELECT * FROM analysis_journal WHERE signal_id = ?", (signal_id,))
        if not rows:
            return None
        d = dict(rows[0])
        d["factors"] = json.loads(d["factors"] or "[]")
        return d

    def closed_rows(self, user_id: Optional[int] = None) -> List[dict]:
        """Band signals + unka journal (journal na ho to factors khali). user_id None = sab."""
        q = ",".join("?" * len(OPEN_STATUSES))
        base = """SELECT s.id, s.symbol, s.mode, s.side, s.entry_type, s.status, s.result_r, s.source,
                         j.htf_alignment, j.ai_verdict, j.ai_confidence, j.factors, j.score
                  FROM signals s LEFT JOIN analysis_journal j ON j.signal_id = s.id"""
        if user_id is None:
            rows = self.db.query(f"{base} WHERE s.status NOT IN ({q}) ORDER BY s.id", OPEN_STATUSES)
        else:
            rows = self.db.query(
                f"""{base} JOIN signal_deliveries d ON d.signal_id = s.id AND d.user_id = ?
                    WHERE s.status NOT IN ({q}) ORDER BY s.id""",
                (user_id, *OPEN_STATUSES),
            )
        out = []
        for r in rows:
            d = dict(r)
            d["factors"] = json.loads(d["factors"] or "[]")
            out.append(d)
        return out
