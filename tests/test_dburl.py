import unittest

from config.settings import load_settings, mask_db_url

BASE = {"TELEGRAM_BOT_TOKEN": "x", "OWNER_ID": "1"}


class DatabaseUrlTests(unittest.TestCase):
    def test_default_is_empty(self):
        self.assertEqual(load_settings(BASE).database_url, "")

    def test_valid_urls_accepted(self):
        for u in ("postgresql://postgres.abc:secret@host.example.com:5432/postgres",
                  "postgres://postgres:secret@host/db"):
            self.assertEqual(load_settings({**BASE, "DATABASE_URL": f"  {u}  "}).database_url, u)

    def test_https_project_url_rejected(self):
        with self.assertRaises(RuntimeError) as cm:
            load_settings({**BASE, "DATABASE_URL": "https://abc.supabase.co"})
        self.assertIn("postgresql://", str(cm.exception))

    def test_password_placeholder_rejected(self):
        with self.assertRaises(RuntimeError) as cm:
            load_settings({**BASE, "DATABASE_URL": "postgresql://postgres:[YOUR-PASSWORD]@host:5432/postgres"})
        self.assertIn("placeholder", str(cm.exception))

    def test_mask_hides_password(self):
        m = mask_db_url("postgresql://postgres.abc:sup3r@secret@host:5432/postgres")
        self.assertNotIn("sup3r", m)
        self.assertNotIn("secret", m)
        self.assertEqual(m, "postgresql://postgres.abc:***@host:5432/postgres")

    def test_mask_empty(self):
        self.assertEqual(mask_db_url(""), "")


if __name__ == "__main__":
    unittest.main()
