from typing import List, Optional

from db.database import Database


class ChatRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, user_id: int, role: str, content: str, ts: int) -> None:
        self.db.execute(
            "INSERT INTO chat_messages (user_id, role, content, ts) VALUES (?,?,?,?)",
            (user_id, role, content, ts),
        )

    def recent(self, user_id: int, limit: int = 10) -> List[dict]:
        rows = self.db.query(
            "SELECT id, role, content, ts FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in reversed(rows)]

    def count(self, user_id: int) -> int:
        return self.db.query("SELECT COUNT(*) AS c FROM chat_messages WHERE user_id = ?", (user_id,))[0]["c"]

    def oldest(self, user_id: int, limit: int) -> List[dict]:
        rows = self.db.query(
            "SELECT id, role, content, ts FROM chat_messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    def delete_ids(self, ids: List[int]) -> None:
        if not ids:
            return
        q = ",".join("?" * len(ids))
        self.db.execute(f"DELETE FROM chat_messages WHERE id IN ({q})", tuple(ids))

    def get_summary(self, user_id: int) -> Optional[str]:
        rows = self.db.query("SELECT summary FROM chat_summary WHERE user_id = ?", (user_id,))
        return rows[0]["summary"] if rows else None

    def set_summary(self, user_id: int, summary: str, ts: int) -> None:
        self.db.execute(
            "INSERT INTO chat_summary (user_id, summary, updated_ts) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET summary = excluded.summary, updated_ts = excluded.updated_ts",
            (user_id, summary, ts),
        )

    def clear(self, user_id: int) -> None:
        self.db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        self.db.execute("DELETE FROM chat_summary WHERE user_id = ?", (user_id,))
