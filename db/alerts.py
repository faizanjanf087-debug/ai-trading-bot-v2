from typing import List, Optional

from db.database import Database


class AlertRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, symbol: str, price: float, direction: str, ts: int) -> int:
        cur = self.db.execute(
            "INSERT INTO alerts (user_id, symbol, price, direction, created_ts) VALUES (?,?,?,?,?)",
            (user_id, symbol, price, direction, ts),
        )
        return cur.lastrowid

    def active(self) -> List[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM alerts WHERE active = 1 ORDER BY id")]

    def for_user(self, user_id: int) -> List[dict]:
        rows = self.db.query("SELECT * FROM alerts WHERE user_id = ? AND active = 1 ORDER BY id", (user_id,))
        return [dict(r) for r in rows]

    def count_for_user(self, user_id: int) -> int:
        return len(self.for_user(user_id))

    def trigger(self, alert_id: int, ts: int) -> None:
        self.db.execute("UPDATE alerts SET active = 0, triggered_ts = ? WHERE id = ?", (ts, alert_id))

    def delete(self, alert_id: int, user_id: int) -> bool:
        cur = self.db.execute(
            "UPDATE alerts SET active = 0 WHERE id = ? AND user_id = ? AND active = 1", (alert_id, user_id)
        )
        return cur.rowcount > 0
