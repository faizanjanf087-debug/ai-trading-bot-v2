"""User approval ka logic. Telegram se alag rakha gaya hai taake aasani se test ho."""
from typing import Optional

from db.users import UserRepo

# request_access() ke natije
NEW_REQUEST = "new_request"        # pehli baar aaya, owner ko batana hai
ALREADY_PENDING = "already_pending"
APPROVED = "approved"
BLOCKED = "blocked"


class ApprovalService:
    def __init__(self, users: UserRepo, owner_id: int):
        self.users = users
        self.owner_id = owner_id
        # Owner hamesha approved rahe
        if self.users.get(owner_id) is None:
            self.users.create_pending(owner_id, None, "Owner")
        self.users.set_status(owner_id, "approved")

    def is_owner(self, telegram_id: int) -> bool:
        return telegram_id == self.owner_id

    def is_approved(self, telegram_id: int) -> bool:
        if self.is_owner(telegram_id):
            return True
        user = self.users.get(telegram_id)
        return bool(user and user["status"] == "approved")

    def request_access(self, telegram_id: int, username: Optional[str], full_name: str) -> str:
        if self.is_owner(telegram_id):
            self.users.update_profile(telegram_id, username, full_name)
            return APPROVED
        user = self.users.get(telegram_id)
        if user is None:
            self.users.create_pending(telegram_id, username, full_name)
            return NEW_REQUEST
        if user["status"] == "approved":
            return APPROVED
        if user["status"] == "blocked":
            return BLOCKED
        return ALREADY_PENDING

    def approve(self, telegram_id: int) -> bool:
        if self.users.get(telegram_id) is None:
            return False
        return self.users.set_status(telegram_id, "approved")

    def reject(self, telegram_id: int) -> bool:
        """Reject = block. User dobara /start kare to bhi access nahi milega."""
        return self.block(telegram_id)

    def block(self, telegram_id: int) -> bool:
        if self.is_owner(telegram_id) or self.users.get(telegram_id) is None:
            return False
        return self.users.set_status(telegram_id, "blocked")
