import unittest
from decimal import Decimal
from types import SimpleNamespace

from db.alerts import AlertRepo
from db.chat import ChatRepo
from db.database import Database
from db.factory import open_database
from db.journal import JournalRepo
from db.kv import KV
from db.postgres import ID_TABLES, TABLES, PostgresDatabase, insert_table, to_pg
from db.signals import SignalRepo
from db.users import UserRepo
from services.signal_service import SignalService
from tests.test_services import Clock, setup_dict


class ToPgTests(unittest.TestCase):
    def test_placeholders(self):
        self.assertEqual(to_pg("SELECT * FROM users WHERE telegram_id = ? AND status = ?"),
                         "SELECT * FROM users WHERE telegram_id = %s AND status = %s")

    def test_percent_in_sql_is_escaped(self):
        self.assertEqual(to_pg("SELECT 1 WHERE x LIKE 'a%' AND y = ?"), "SELECT 1 WHERE x LIKE 'a%%' AND y = %s")

    def test_insert_or_ignore(self):
        out = to_pg("INSERT OR IGNORE INTO signal_deliveries (signal_id, user_id) VALUES (?,?);")
        self.assertEqual(out, "INSERT INTO signal_deliveries (signal_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING")

    def test_datetime_now(self):
        out = to_pg("UPDATE users SET status = ?, updated_at = datetime('now') WHERE telegram_id = ?")
        self.assertNotIn("datetime(", out)
        self.assertIn("to_char(now() AT TIME ZONE 'utc'", out)
        self.assertEqual(out.count("%s"), 2)

    def test_on_conflict_do_update_unchanged(self):
        sql = "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        self.assertEqual(to_pg(sql), sql.replace("?", "%s"))

    def test_insert_or_replace_refused(self):
        with self.assertRaises(ValueError):
            to_pg("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)")

    def test_insert_table(self):
        self.assertEqual(insert_table("INSERT INTO signals (a) VALUES (?)"), "signals")
        self.assertEqual(insert_table("  insert or ignore into Users (a) VALUES (?)"), "users")
        self.assertIsNone(insert_table("SELECT * FROM signals"))
        self.assertIsNone(insert_table("UPDATE signals SET a = ?"))

    def test_id_tables_match_schema(self):
        self.assertTrue(ID_TABLES <= set(TABLES))
        self.assertEqual(len(TABLES), 9)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conn.log.append((sql, tuple(params)))
        if self.conn.fail:
            self.conn.fail -= 1
            raise ConnectionError("connection closed")
        rows, rowcount = self.conn.responder(sql, params)
        self._rows, self.rowcount = rows, rowcount
        self.description = [("x",)] if rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, responder=None, fail=0):
        self.log, self.fail, self.closed = [], fail, False
        self.responder = responder or (lambda sql, params: ([], 1))

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql):
        self.log.append((sql, ()))

    def close(self):
        self.closed = True


def make_db(responder=None, fail=0, retry=True, persistent=False):
    """persistent=True: naye connections bhi fail hote rahein (server sach mein down)."""
    conns = []

    def connect():
        c = FakeConn(responder, fail if (persistent or not conns) else 0)
        conns.append(c)
        return c

    db = PostgresDatabase("postgresql://x", connect=connect, retry_on=(ConnectionError,) if retry else (),
                          init_schema=False)
    return db, conns


class PostgresDatabaseTests(unittest.TestCase):
    def test_insert_into_id_table_returns_lastrowid(self):
        db, conns = make_db(lambda sql, p: ([{"id": 42}], 1))
        res = db.execute("INSERT INTO signals (symbol) VALUES (?)", ("BTCUSD",))
        self.assertEqual(res.lastrowid, 42)
        sql, params = conns[0].log[-1]
        self.assertTrue(sql.endswith("VALUES (%s) RETURNING id"))
        self.assertEqual(params, ("BTCUSD",))

    def test_no_returning_for_tables_without_id(self):
        db, conns = make_db()
        res = db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         ("a", "b"))
        self.assertIsNone(res.lastrowid)
        self.assertNotIn("RETURNING", conns[0].log[-1][0])

    def test_insert_or_ignore_with_id_table(self):
        db, conns = make_db(lambda sql, p: ([], 0))
        res = db.execute("INSERT OR IGNORE INTO analysis_journal (signal_id) VALUES (?)", (1,))
        self.assertIsNone(res.lastrowid)       # conflict: koi row nahi aayi
        self.assertTrue(conns[0].log[-1][0].endswith("ON CONFLICT DO NOTHING RETURNING id"))

    def test_rowcount(self):
        db, _ = make_db(lambda sql, p: ([], 3))
        self.assertEqual(db.execute("UPDATE users SET muted = ? WHERE telegram_id = ?", (1, 2)).rowcount, 3)

    def test_query_converts_decimal(self):
        db, _ = make_db(lambda sql, p: ([{"t": Decimal("5"), "u": Decimal("2.5"), "s": "x"}], 1))
        row = db.query("SELECT 1")[0]
        self.assertEqual((row["t"], row["u"], row["s"]), (5, 2.5, "x"))
        self.assertIsInstance(row["t"], int)

    def test_reconnects_once_after_dropped_connection(self):
        db, conns = make_db(lambda sql, p: ([{"c": 7}], 1), fail=1)
        self.assertEqual(db.query("SELECT COUNT(*) AS c FROM kv")[0]["c"], 7)
        self.assertEqual(len(conns), 2)
        self.assertTrue(conns[0].closed)

    def test_gives_up_after_second_failure(self):
        db, conns = make_db(fail=5, persistent=True)
        with self.assertRaises(ConnectionError):
            db.query("SELECT 1")

    def test_non_connection_errors_not_retried(self):
        def boom(sql, params):
            raise ValueError("syntax")
        db, conns = make_db(boom)
        with self.assertRaises(ValueError):
            db.query("SELECT 1")
        self.assertEqual(len(conns), 1)

    def test_export_all_reads_every_table(self):
        db, conns = make_db(lambda sql, p: ([{"a": 1}], 1))
        data = db.export_all()
        self.assertEqual(list(data), TABLES)
        self.assertEqual(data["kv"], [{"a": 1}])


class FactoryTests(unittest.TestCase):
    def test_sqlite_when_no_url(self):
        db = open_database(SimpleNamespace(database_url="", database_path=":memory:"))
        self.assertIsInstance(db, Database)

    def test_bad_url_gives_clear_error_and_never_falls_back_to_sqlite(self):
        with self.assertRaises(RuntimeError) as cm:
            open_database(SimpleNamespace(database_url="postgresql://u:topsecret@127.0.0.1:1/db",
                                          database_path=":memory:"))
        self.assertNotIn("topsecret", str(cm.exception))


class RecordedSqlTests(unittest.TestCase):
    """Saare repo methods chala kar dekho ke har SQL Postgres ke liye theek badalti hai."""

    def test_every_repo_statement_translates(self):
        seen = []

        class Recorder(Database):
            def execute(self, sql, params=()):
                seen.append(sql)
                return super().execute(sql, params)

            def query(self, sql, params=()):
                seen.append(sql)
                return super().query(sql, params)

        db = Recorder(":memory:")
        users, signals, alerts = UserRepo(db), SignalRepo(db), AlertRepo(db)
        chat, kv, journal = ChatRepo(db), KV(db), JournalRepo(db)
        users.create_pending(2, "u", "User")
        users.set_status(2, "approved")
        users.update_profile(2, "u2", "User Two")
        users.set_muted(2, True)
        users.get(2)
        users.list_by_status()
        users.list_by_status("approved")
        users.broadcast_targets()
        svc = SignalService(signals, users, Clock(), journal=journal)
        sig = svc.create(setup_dict(), "scan", [2], analysis={"htf_trend": "up"}, review={"verdict": "take"})
        signals.update(sig["id"], status="SL", result_r=-1.0)
        signals.get(sig["id"])
        signals.list_open()
        signals.open_for_user(2)
        signals.closed_for_user(2)
        signals.has_open("BTCUSD", "buy", "scalp")
        signals.last_created_ts("BTCUSD")
        signals.add_event(sig["id"], "SL_HIT", 1.0, 1, "n")
        signals.events(sig["id"])
        signals.add_delivery(sig["id"], 2)
        signals.recipients(sig["id"])
        signals.stats()
        signals.stats(2)
        aid = alerts.create(2, "BTCUSD", 100.0, "above", 1)
        alerts.active()
        alerts.for_user(2)
        alerts.count_for_user(2)
        alerts.trigger(aid, 2)
        alerts.delete(aid, 2)
        chat.add(2, "user", "hi", 1)
        chat.recent(2)
        chat.count(2)
        chat.oldest(2, 1)
        chat.delete_ids([1])
        chat.set_summary(2, "s", 1)
        chat.get_summary(2)
        chat.clear(2)
        kv.set("k", "v")
        kv.get("k")
        kv.delete_prefix("k")
        journal.get(sig["id"])
        journal.closed_rows()
        journal.closed_rows(2)

        self.assertGreater(len(set(seen)), 30)
        for sql in set(seen):
            pg = to_pg(sql)
            self.assertNotIn("?", pg, sql)
            self.assertNotIn("INSERT OR", pg.upper(), sql)
            self.assertNotIn("datetime(", pg, sql)
            self.assertNotIn("AUTOINCREMENT", pg.upper(), sql)


if __name__ == "__main__":
    unittest.main()
