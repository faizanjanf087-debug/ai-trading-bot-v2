import unittest

from config.settings import load_settings
from db.database import Database
from db.users import UserRepo
from services import approval as ap

OWNER = 1


def make():
    db = Database(":memory:")
    return ap.ApprovalService(UserRepo(db), OWNER)


class ApprovalTests(unittest.TestCase):
    def test_owner_always_approved(self):
        svc = make()
        self.assertTrue(svc.is_approved(OWNER))
        self.assertEqual(svc.request_access(OWNER, None, "Owner"), ap.APPROVED)

    def test_new_user_flow(self):
        svc = make()
        self.assertFalse(svc.is_approved(2))
        self.assertEqual(svc.request_access(2, "ali", "Ali"), ap.NEW_REQUEST)
        self.assertEqual(svc.request_access(2, "ali", "Ali"), ap.ALREADY_PENDING)
        self.assertFalse(svc.is_approved(2))
        self.assertTrue(svc.approve(2))
        self.assertTrue(svc.is_approved(2))
        self.assertEqual(svc.request_access(2, "ali", "Ali"), ap.APPROVED)

    def test_reject_blocks_and_stays_blocked(self):
        svc = make()
        svc.request_access(3, None, "Sara")
        self.assertTrue(svc.reject(3))
        self.assertFalse(svc.is_approved(3))
        self.assertEqual(svc.request_access(3, None, "Sara"), ap.BLOCKED)

    def test_cannot_block_owner_or_unknown(self):
        svc = make()
        self.assertFalse(svc.block(OWNER))
        self.assertTrue(svc.is_approved(OWNER))
        self.assertFalse(svc.block(999))
        self.assertFalse(svc.approve(999))

    def test_block_after_approval(self):
        svc = make()
        svc.request_access(4, None, "Omar")
        svc.approve(4)
        svc.block(4)
        self.assertFalse(svc.is_approved(4))

    def test_list_users(self):
        svc = make()
        svc.request_access(5, "a", "A")
        svc.request_access(6, "b", "B")
        svc.approve(6)
        self.assertEqual(len(svc.users.list_by_status("pending")), 1)
        self.assertEqual(len(svc.users.list_by_status("approved")), 2)  # owner + 6
        self.assertEqual(len(svc.users.list_by_status()), 3)


class SettingsTests(unittest.TestCase):
    def test_missing_token(self):
        with self.assertRaises(RuntimeError):
            load_settings({"OWNER_ID": "1"})

    def test_bad_owner(self):
        with self.assertRaises(RuntimeError):
            load_settings({"TELEGRAM_BOT_TOKEN": "x", "OWNER_ID": "abc"})

    def test_ok(self):
        s = load_settings({"TELEGRAM_BOT_TOKEN": "x", "OWNER_ID": "42"})
        self.assertEqual((s.telegram_token, s.owner_id), ("x", 42))


if __name__ == "__main__":
    unittest.main()


class OwnerProfileTests(unittest.TestCase):
    def test_owner_profile_refreshed_on_start(self):
        svc = make()
        svc.request_access(OWNER, "faizi", "Faizan")
        u = svc.users.get(OWNER)
        self.assertEqual((u["username"], u["full_name"], u["status"]), ("faizi", "Faizan", "approved"))
