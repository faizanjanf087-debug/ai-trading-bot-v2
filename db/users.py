from typing import List, Optional

from db.database import Database

VALID_STATUSES = ("pending", "approved", "blocked")


class UserRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, telegram_id: int) -> Optional[dict]:
        rows = self.db.query("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(rows[0]) if rows else None

    def create_pending(self, telegram_id: int, username: Optional[str], full_name: str) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, full_name, status) "
            "VALUES (?, ?, ?, 'pending')",
            (telegram_id, username, full_name),
        )
        return self.get(telegram_id)

    def set_status(self, telegram_id: int, status: str) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"Galat status: {status}")
        cur = self.db.execute(
            "UPDATE users SET status = ?, updated_at = datetime('now') WHERE telegram_id = ?",
            (status, telegram_id),
        )
        return cur.rowcount > 0

    def update_profile(self, telegram_id: int, username, full_name: str) -> None:
        self.db.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?",
            (username, full_name, telegram_id),
        )

    def set_muted(self, telegram_id: int, muted: bool) -> bool:
        cur = self.db.execute(
            "UPDATE users SET muted = ? WHERE telegram_id = ?", (1 if muted else 0, telegram_id)
        )
        return cur.rowcount > 0

    def list_by_status(self, status: Optional[str] = None) -> List[dict]:
        if status is None:
            rows = self.db.query("SELECT * FROM users ORDER BY created_at")
        else:
            rows = self.db.query(
                "SELECT * FROM users WHERE status = ? ORDER BY created_at", (status,)
            )
        return [dict(r) for r in rows]

    def broadcast_targets(self) -> List[int]:
        """Approved aur unmuted users (signals inhi ko jate hain)."""
        rows = self.db.query(
            "SELECT telegram_id FROM users WHERE status = 'approved' AND muted = 0"
        )
        return [r["telegram_id"] for r in rows]
