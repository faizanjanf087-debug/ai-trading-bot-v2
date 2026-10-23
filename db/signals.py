from typing import List, Optional

from db.database import Database

OPEN_STATUSES = ("PENDING", "ACTIVE", "TP1")
SIGNAL_COLUMNS = {
    "status", "sl", "activated_ts", "closed_ts", "result_r", "last_candle_ts", "ai_note",
}


class SignalRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, s: dict) -> int:
        cur = self.db.execute(
            """INSERT INTO signals
               (symbol, mode, side, entry_type, entry, sl, sl_initial, tp1, tp2, status, score,
                reason, ai_note, source, owner_id, created_ts, expires_ts, activated_ts, last_candle_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                s["symbol"], s["mode"], s["side"], s["entry_type"], s["entry"], s["sl"], s["sl"],
                s["tp1"], s["tp2"], s["status"], s.get("score"), s.get("reason"), s.get("ai_note"),
                s.get("source", "scan"), s.get("owner_id"), s["created_ts"], s.get("expires_ts"),
                s.get("activated_ts"), s.get("last_candle_ts", 0),
            ),
        )
        return cur.lastrowid

    def get(self, signal_id: int) -> Optional[dict]:
        rows = self.db.query("SELECT * FROM signals WHERE id = ?", (signal_id,))
        return dict(rows[0]) if rows else None

    def update(self, signal_id: int, **fields) -> None:
        bad = set(fields) - SIGNAL_COLUMNS
        if bad:
            raise ValueError(f"Update na hone wale columns: {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE signals SET {sets} WHERE id = ?", (*fields.values(), signal_id))

    def list_open(self) -> List[dict]:
        q = ",".join("?" * len(OPEN_STATUSES))
        rows = self.db.query(f"SELECT * FROM signals WHERE status IN ({q}) ORDER BY id", OPEN_STATUSES)
        return [dict(r) for r in rows]

    def open_for_user(self, user_id: int) -> List[dict]:
        q = ",".join("?" * len(OPEN_STATUSES))
        rows = self.db.query(
            f"""SELECT s.* FROM signals s JOIN signal_deliveries d ON d.signal_id = s.id
                WHERE d.user_id = ? AND s.status IN ({q}) ORDER BY s.id""",
            (user_id, *OPEN_STATUSES),
        )
        return [dict(r) for r in rows]

    def closed_for_user(self, user_id: int, limit: int = 10) -> List[dict]:
        q = ",".join("?" * len(OPEN_STATUSES))
        rows = self.db.query(
            f"""SELECT s.* FROM signals s JOIN signal_deliveries d ON d.signal_id = s.id
                WHERE d.user_id = ? AND s.status NOT IN ({q}) ORDER BY s.id DESC LIMIT ?""",
            (user_id, *OPEN_STATUSES, limit),
        )
        return [dict(r) for r in rows]

    def has_open(self, symbol: str, side: str, mode: str) -> bool:
        q = ",".join("?" * len(OPEN_STATUSES))
        rows = self.db.query(
            f"SELECT 1 FROM signals WHERE symbol=? AND side=? AND mode=? AND status IN ({q}) LIMIT 1",
            (symbol, side, mode, *OPEN_STATUSES),
        )
        return bool(rows)

    def last_created_ts(self, symbol: str, source: str = "scan") -> int:
        rows = self.db.query(
            "SELECT MAX(created_ts) AS t FROM signals WHERE symbol = ? AND source = ?",
            (symbol, source),
        )
        return rows[0]["t"] or 0

    def add_event(self, signal_id: int, type_: str, price: Optional[float], ts: int, note: str = "") -> None:
        self.db.execute(
            "INSERT INTO signal_events (signal_id, type, price, ts, note) VALUES (?,?,?,?,?)",
            (signal_id, type_, price, ts, note),
        )

    def events(self, signal_id: int) -> List[dict]:
        rows = self.db.query("SELECT * FROM signal_events WHERE signal_id = ? ORDER BY id", (signal_id,))
        return [dict(r) for r in rows]

    def add_delivery(self, signal_id: int, user_id: int) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO signal_deliveries (signal_id, user_id) VALUES (?,?)",
            (signal_id, user_id),
        )

    def recipients(self, signal_id: int) -> List[int]:
        rows = self.db.query("SELECT user_id FROM signal_deliveries WHERE signal_id = ?", (signal_id,))
        return [r["user_id"] for r in rows]

    def stats(self, user_id: Optional[int] = None) -> dict:
        """Band ho chuke signals ka hisaab: wins/losses/net R."""
        q = ",".join("?" * len(OPEN_STATUSES))
        if user_id is None:
            rows = self.db.query(
                f"SELECT status, result_r FROM signals WHERE status NOT IN ({q})", OPEN_STATUSES
            )
        else:
            rows = self.db.query(
                f"""SELECT s.status, s.result_r FROM signals s
                    JOIN signal_deliveries d ON d.signal_id = s.id
                    WHERE d.user_id = ? AND s.status NOT IN ({q})""",
                (user_id, *OPEN_STATUSES),
            )
        wins = sum(1 for r in rows if (r["result_r"] or 0) > 0)
        losses = sum(1 for r in rows if (r["result_r"] or 0) < 0)
        flat = sum(1 for r in rows if r["status"] in ("BE", "EXPIRED", "CANCELLED") and not (r["result_r"] or 0))
        net = sum((r["result_r"] or 0) for r in rows)
        decided = wins + losses
        return {
            "closed": len(rows), "wins": wins, "losses": losses, "flat": flat,
            "net_r": round(net, 2), "win_rate": round(100 * wins / decided, 1) if decided else None,
        }
