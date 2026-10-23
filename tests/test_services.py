import asyncio
import json
import unittest

from ai.deepseek_client import AIError, DeepSeekClient
from ai.memory import ChatMemory
from backtest.runner import backtest, summarize
from config.settings import load_settings
from data.base import BudgetExhausted, DataError, make_df
from db.alerts import AlertRepo
from db.chat import ChatRepo
from db.database import Database
from db.kv import KV
from db.signals import SignalRepo
from db.users import UserRepo
from monitor.price_watcher import PriceWatcher
from monitor.scanner import Scanner, parse_ai_review
from services import formatter
from services.approval import ApprovalService
from services.chat_service import ChatService
from services.signal_service import SignalService
from services.watchlist import Watchlist
from tests.helpers import synth

NOW = 1767614400  # Monday 2026-01-05 12:00 UTC (forex khula, session ke andar)


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def setup_dict(**kw):
    s = dict(symbol="BTCUSD", mode="scalp", tf="5m", side="buy", entry_type="LIMIT", entry=100.0, sl=99.0,
             tp1=101.5, tp2=102.5, score=7.5, reasons=["trend up", "near support"], atr=1.0,
             pending_bars=24, tf_seconds=300, last_candle_ts=NOW - 300)
    s.update(kw)
    return s


def env():
    db = Database(":memory:")
    clock = Clock()
    users = UserRepo(db)
    approval = ApprovalService(users, 1)
    for uid in (2, 3):
        approval.request_access(uid, None, f"u{uid}")
        approval.approve(uid)
    repo = SignalRepo(db)
    svc = SignalService(repo, users, clock)
    return db, clock, users, approval, repo, svc


def candles_df(rows):
    """rows: [(minute_offset, o, h, l, c)] -> 1m DataFrame NOW ke hisaab se."""
    return make_df([(NOW + m * 60, o, h, l, c, 0) for m, o, h, l, c in rows])


class FakeMarket:
    def __init__(self, clock):
        self.clock = clock
        self.df = None
        self.error = None
        self.calls = []

    def get_recent_1m(self, symbol, count=15, priority="monitor"):
        self.calls.append((symbol, priority))
        if self.error:
            raise self.error
        return self.df


class SignalServiceTests(unittest.TestCase):
    def test_create_limit_and_market(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [1, 2])
        self.assertEqual((sig["status"], sig["entry_type"]), ("PENDING", "LIMIT"))
        self.assertEqual(sorted(svc.recipients(sig["id"])), [1, 2])
        self.assertEqual(sig["expires_ts"], NOW + 24 * 300)
        m = svc.create(setup_dict(entry_type="MARKET", symbol="ETHUSD"), "scan", [2])
        self.assertEqual(m["status"], "ACTIVE")
        self.assertEqual([e["type"] for e in repo.events(m["id"])], ["ENTRY_HIT"])
        self.assertEqual(len(repo.list_open()), 2)

    def test_can_create_dedupe_and_cooldown(self):
        db, clock, users, approval, repo, svc = env()
        self.assertTrue(svc.can_create("BTCUSD", "buy", "scalp", 3600))
        svc.create(setup_dict(), "scan", [2])
        self.assertFalse(svc.can_create("BTCUSD", "buy", "scalp"))          # open hai
        self.assertFalse(svc.can_create("BTCUSD", "sell", "scalp", 3600))   # cooldown
        clock.t += 3601
        self.assertTrue(svc.can_create("BTCUSD", "sell", "scalp", 3600))

    def test_process_persists_status_events_and_stats(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [2, 3])
        t0 = sig["last_candle_ts"]
        ev = svc.process(sig, [(t0, 101, 101, 99.9, 100.5)])
        self.assertEqual([e["type"] for e in ev], ["ENTRY_HIT"])
        sig = repo.get(sig["id"])
        ev = svc.process(sig, [(t0 + 60, 100.5, 102.6, 100.4, 102.5)])
        self.assertEqual([e["type"] for e in ev], ["TP1_HIT", "SL_TO_BE", "TP2_HIT"])
        sig = repo.get(sig["id"])
        self.assertEqual((sig["status"], sig["result_r"]), ("TP2", 2.0))
        self.assertEqual(len(repo.list_open()), 0)
        st = repo.stats(2)
        self.assertEqual((st["closed"], st["wins"], st["net_r"], st["win_rate"]), (1, 1, 2.0, 100.0))
        self.assertEqual(repo.stats(99)["closed"], 0)
        self.assertEqual(len(repo.closed_for_user(2)), 1)
        self.assertEqual(len(repo.open_for_user(2)), 0)

    def test_update_rejects_unknown_columns(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [2])
        with self.assertRaises(ValueError):
            repo.update(sig["id"], entry=1.0)


class WatcherTests(unittest.TestCase):
    def build(self, symbol="BTCUSD"):
        db, clock, users, approval, repo, svc = env()
        market = FakeMarket(clock)
        alerts = AlertRepo(db)
        sent = []

        async def notify(uid, text):
            sent.append((uid, text))

        w = PriceWatcher(market, svc, alerts, notify, None, clock=clock)
        return clock, svc, repo, alerts, market, w, sent

    def test_full_trade_alerts_reach_recipients_only(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        sig = svc.create(setup_dict(), "scan", [2, 3])
        t = sig["last_candle_ts"]
        # 1) entry hit
        market.df = make_df([(t, 101, 101, 99.9, 100.4, 0)])
        asyncio.run(w.tick())
        self.assertEqual(sorted(u for u, _ in sent), [2, 3])
        self.assertIn("Entry hit", sent[0][1])
        sent.clear()
        # 2) tp1 + breakeven ki khabar, aur tp2
        clock.t += 60
        market.df = make_df([(t, 101, 101, 99.9, 100.4, 0), (t + 60, 100.4, 102.7, 100.3, 102.6, 0)])
        asyncio.run(w.tick())
        texts = [x for u, x in sent if u == 2]
        self.assertTrue(any("TP1" in x for x in texts))
        self.assertTrue(any("TP2" in x for x in texts))
        self.assertEqual(repo.get(sig["id"])["status"], "TP2")
        # band signal par dobara kuch nahi
        sent.clear()
        clock.t += 60
        asyncio.run(w.tick())
        self.assertEqual(sent, [])

    def test_sl_alert_includes_result(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        sig = svc.create(setup_dict(entry_type="MARKET", entry=100.0), "scan", [2])
        t = sig["last_candle_ts"]
        market.df = make_df([(t, 100, 100.2, 98.8, 99.0, 0)])
        asyncio.run(w.tick())
        self.assertEqual(len(sent), 1)
        self.assertIn("SL hit", sent[0][1])
        self.assertIn("-1.00R", sent[0][1])

    def test_polling_interval_respected(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        svc.create(setup_dict(), "scan", [2])
        market.df = make_df([(NOW, 101, 101.5, 100.5, 101, 0)])
        asyncio.run(w.tick())
        asyncio.run(w.tick())
        self.assertEqual(len(market.calls), 1)          # crypto 30s ke andar dubara nahi
        clock.t += 31
        asyncio.run(w.tick())
        self.assertEqual(len(market.calls), 2)

    def test_price_alert_triggers_once(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        alerts.create(2, "BTCUSD", 105.0, "above", NOW)
        alerts.create(3, "BTCUSD", 90.0, "below", NOW)
        market.df = make_df([(NOW, 100, 105.5, 99, 104, 0)])
        asyncio.run(w.tick())
        self.assertEqual([u for u, _ in sent], [2])
        self.assertEqual(len(alerts.active()), 1)
        clock.t += 31
        asyncio.run(w.tick())
        self.assertEqual(len(sent), 1)

    def test_alert_ignores_candles_before_creation(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        alerts.create(2, "BTCUSD", 105.0, "above", NOW)
        market.df = make_df([(NOW - 600, 100, 110, 99, 104, 0)])
        asyncio.run(w.tick())
        self.assertEqual(sent, [])

    def test_data_errors_do_not_crash_and_budget_message_once(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        svc.create(setup_dict(), "scan", [2])
        market.error = DataError("down")
        asyncio.run(w.tick())
        market.error = BudgetExhausted("limit")
        clock.t += 100
        asyncio.run(w.tick())
        self.assertEqual(sent, [])

    def test_forex_skipped_when_market_closed(self):
        clock, svc, repo, alerts, market, w, sent = self.build()
        svc.create(setup_dict(symbol="XAUUSD"), "scan", [2])
        clock.t = NOW + 5 * 86400   # Saturday
        market.df = make_df([(clock.t, 1, 2, 0.5, 1, 0)])
        asyncio.run(w.tick())
        self.assertEqual(market.calls, [])

    def test_forex_interval_stretches_with_budget(self):
        class B:
            monitor_reserve = 250
        clock, svc, repo, alerts, market, w, sent = self.build()
        w.budget = B()
        self.assertEqual(w._interval("XAUUSD", 1), 345.6)       # 86400/250
        self.assertEqual(w._interval("XAUUSD", 3), 840)         # cap 14 minute
        self.assertEqual(w._interval("BTCUSD", 3), 30)


class FakeAnalysis:
    def __init__(self, setup=None, error=None):
        self.setup, self.error, self.calls = setup, error, []
        self.run_fresh = self.run

    def run(self, symbol, mode, priority="normal"):
        self.calls.append((symbol, mode))
        if self.error:
            raise self.error
        if not self.setup:
            return None, None
        a = {"symbol": symbol, "mode": mode, "tf": "5m", "price": 100.0, "atr": 1.0, "ema_fast": 99.0,
             "ema_slow": 98.0, "htf_trend": "up", "rsi": 40.0, "macd_hist": 0.1, "macd_cross": None,
             "divergence": None, "volume_spike": None, "candles": [], "chart_patterns": [], "levels": [],
             "score_buy": 7.0, "score_sell": 1.0}
        return a, dict(self.setup, symbol=symbol, mode=mode)


class FakeAI:
    def __init__(self, reply="", enabled=True, error=None):
        self.reply, self.enabled, self.error, self.calls = reply, enabled, error, []

    def chat(self, messages, temperature=0.3, max_tokens=700):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply


class ScannerTests(unittest.TestCase):
    def build(self, analysis, ai=None, **settings_kw):
        db, clock, users, approval, repo, svc = env()
        base = load_settings({"TELEGRAM_BOT_TOKEN": "x", "OWNER_ID": "1", "WATCHLIST": "BTCUSD,XAUUSD",
                              "CRYPTO_MODES": "scalp", "FOREX_MODES": "scalp"})
        s = base.__class__(**{**base.__dict__, **settings_kw})
        sent = []

        async def notify(uid, text):
            sent.append((uid, text))

        wl = Watchlist(KV(db), s.watchlist)
        sc = Scanner(s, analysis, svc, users, ai or FakeAI(enabled=False), None, notify, wl, clock)
        return clock, svc, repo, sc, sent

    def test_signal_broadcast_to_approved_unmuted_only(self):
        an = FakeAnalysis(setup_dict())
        clock, svc, repo, sc, sent = self.build(an)
        sc.users.set_muted(3, True)
        n = asyncio.run(sc.scan_once())
        self.assertEqual(n, 2)                              # BTC + XAU (Monday 12:00 UTC)
        self.assertEqual(sorted({u for u, _ in sent}), [1, 2])
        self.assertTrue(all("Signal #" in t for _, t in sent))
        self.assertEqual(len(repo.list_open()), 2)

    def test_not_due_again_and_cooldown(self):
        an = FakeAnalysis(setup_dict())
        clock, svc, repo, sc, sent = self.build(an)
        asyncio.run(sc.scan_once())
        calls = len(an.calls)
        asyncio.run(sc.scan_once())
        self.assertEqual(len(an.calls), calls)               # abhi due nahi
        clock.t += 6 * 60
        sent.clear()
        asyncio.run(sc.scan_once())                          # crypto due, lekin signal open hai
        self.assertEqual(sent, [])

    def test_forex_skipped_outside_session_and_weekend(self):
        an = FakeAnalysis(setup_dict())
        clock, svc, repo, sc, sent = self.build(an)
        clock.t = NOW + 10 * 3600          # 22:00 UTC, session 07-20 ke baad
        asyncio.run(sc.scan_once())
        self.assertEqual({s for s, _ in an.calls}, {"BTCUSD"})
        an.calls.clear()
        clock.t = NOW + 5 * 86400
        sc._last_scan.clear()
        asyncio.run(sc.scan_once())
        self.assertEqual({s for s, _ in an.calls}, {"BTCUSD"})

    def test_no_targets_no_scan(self):
        an = FakeAnalysis(setup_dict())
        clock, svc, repo, sc, sent = self.build(an)
        for u in (1, 2, 3):
            sc.users.set_muted(u, True)
        self.assertEqual(asyncio.run(sc.scan_once()), 0)
        self.assertEqual(an.calls, [])

    def test_budget_exhausted_does_not_crash(self):
        an = FakeAnalysis(error=BudgetExhausted("x"))
        clock, svc, repo, sc, sent = self.build(an)
        self.assertEqual(asyncio.run(sc.scan_once()), 0)

    def test_ai_note_attached_and_veto(self):
        ai = FakeAI(json.dumps({"verdict": "skip", "confidence": 30, "comment": "news risk"}))
        clock, svc, repo, sc, sent = self.build(FakeAnalysis(setup_dict()), ai)
        asyncio.run(sc.scan_once())
        self.assertEqual(len(repo.list_open()), 2)           # veto off: signal chala, note ke saath
        self.assertIn("news risk", sent[0][1])
        clock2, svc2, repo2, sc2, sent2 = self.build(FakeAnalysis(setup_dict()), ai, ai_veto=True)
        asyncio.run(sc2.scan_once())
        self.assertEqual(len(repo2.list_open()), 0)

    def test_ai_failure_does_not_block_signal(self):
        ai = FakeAI(error=AIError("down"))
        clock, svc, repo, sc, sent = self.build(FakeAnalysis(setup_dict()), ai, ai_veto=True)
        asyncio.run(sc.scan_once())
        self.assertEqual(len(repo.list_open()), 2)

    def test_parse_ai_review(self):
        self.assertEqual(parse_ai_review('ok {"verdict":"TAKE","confidence":"80","comment":"acha"} bye')["confidence"], 80)
        self.assertIsNone(parse_ai_review("no json"))
        self.assertIsNone(parse_ai_review('{"verdict":"maybe"}'))


class AITests(unittest.TestCase):
    def test_deepseek_request_and_parse(self):
        seen = {}

        def post(url, headers, payload):
            seen.update(url=url, headers=headers, payload=payload)
            return {"choices": [{"message": {"content": " hello "}}]}

        c = DeepSeekClient("KEY", "deepseek-chat", post)
        self.assertEqual(c.chat([{"role": "user", "content": "hi"}]), "hello")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer KEY")
        self.assertEqual(seen["payload"]["model"], "deepseek-chat")
        with self.assertRaises(AIError):
            DeepSeekClient("KEY", http_post=lambda *a: {"oops": 1}).chat([])
        with self.assertRaises(AIError):
            DeepSeekClient("").chat([])
        self.assertFalse(DeepSeekClient("").enabled)

    def test_memory_recent_and_summary(self):
        db = Database(":memory:")
        repo = ChatRepo(db)
        ai = FakeAI("SUMMARY TEXT")
        mem = ChatMemory(repo, ai, recent=4, summarize_after=6, clock=Clock())
        for i in range(4):
            mem.remember(7, f"q{i}", f"a{i}")          # 8 messages
        self.assertEqual(len(mem.history_messages(7)), 4)   # sirf aakhri 4
        self.assertTrue(mem.maybe_summarize(7))
        self.assertEqual(repo.count(7), 4)
        hist = mem.history_messages(7)
        self.assertIn("SUMMARY TEXT", hist[0]["content"])
        self.assertEqual(hist[-1]["content"], "a3")
        repo.clear(7)
        self.assertEqual(mem.history_messages(7), [])

    def test_memory_summary_failure_keeps_messages(self):
        repo = ChatRepo(Database(":memory:"))
        mem = ChatMemory(repo, FakeAI(error=AIError("x")), recent=2, summarize_after=3, clock=Clock())
        for i in range(3):
            mem.remember(1, "q", "a")
        self.assertFalse(mem.maybe_summarize(1))
        self.assertEqual(repo.count(1), 6)

    def test_chat_service_uses_memory_signals_and_market(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [2])
        ai = FakeAI("Jawab")
        an = FakeAnalysis(None)
        mem = ChatMemory(ChatRepo(db), ai, clock=clock)
        chat = ChatService(ai, mem, an, None, repo)
        out = chat.reply_blocking(2, "gold ka kya scene hai?")
        self.assertEqual(out, "Jawab")
        sent = ai.calls[0]
        ctx = " ".join(m["content"] for m in sent if m["role"] == "system")
        self.assertIn(f"#{sig['id']}", ctx)                 # user ka open signal context mein
        self.assertEqual(an.calls, [("XAUUSD", "scalp")])   # 'gold' pehchana gaya
        self.assertEqual(mem.repo.count(2), 2)
        chat.reply_blocking(2, "aur?")
        self.assertEqual(len(ai.calls[1]), 2 + 2 + 1)       # 2 system + pichli baat + naya sawal

    def test_chat_disabled_and_error(self):
        db, clock, users, approval, repo, svc = env()
        off = ChatService(FakeAI(enabled=False), None, None, None, repo)
        self.assertIn("DEEPSEEK_API_KEY", off.reply_blocking(2, "hi"))
        on = ChatService(FakeAI(error=AIError("x")), ChatMemory(ChatRepo(db), None), FakeAnalysis(), None, repo)
        self.assertIn("nahi mil", on.reply_blocking(2, "hi"))


class MiscTests(unittest.TestCase):
    def test_watchlist_persist(self):
        kv = KV(Database(":memory:"))
        wl = Watchlist(kv, ["BTCUSD", "BAD"])
        self.assertEqual(wl.get(), ["BTCUSD"])
        self.assertTrue(wl.add("XAUUSD"))
        self.assertFalse(wl.add("XAUUSD"))
        self.assertFalse(wl.add("NOPE"))
        self.assertEqual(Watchlist(kv, []).get(), ["BTCUSD", "XAUUSD"])
        self.assertTrue(wl.remove("BTCUSD"))
        self.assertFalse(wl.remove("BTCUSD"))

    def test_formatters(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(symbol="XAUUSD"), "scan", [2])
        txt = formatter.format_signal(sig)
        self.assertIn("LIMIT", txt)
        self.assertIn("100.00", txt)
        self.assertIn("financial advice", txt)
        self.assertIn("expire", formatter.format_event(sig, {"type": "EXPIRED", "price": None, "ts": 1, "note": "n"}))
        self.assertIn("XAUUSD", formatter.format_signal_line(sig))
        self.assertIn("Win rate: -", formatter.format_stats(repo.stats(2)))

    def test_muted_users_and_migration(self):
        import sqlite3, tempfile, os
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, "
                  "status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT (datetime('now')), "
                  "updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
        c.execute("INSERT INTO users (telegram_id, full_name, status) VALUES (5, 'Old', 'approved')")
        c.commit(); c.close()
        users = UserRepo(Database(path))               # Phase 1 wali database khul jaye
        self.assertEqual(users.broadcast_targets(), [5])
        users.set_muted(5, True)
        self.assertEqual(users.broadcast_targets(), [])


class BacktestTests(unittest.TestCase):
    def test_summarize(self):
        r = summarize([{"status": "TP2", "r": 2.0}, {"status": "SL", "r": -1.0}, {"status": "SL", "r": -1.0},
                       {"status": "EXPIRED", "r": 0.0}])
        self.assertEqual((r["trades"], r["wins"], r["losses"], r["net_r"], r["max_drawdown_r"], r["skipped"]),
                         (3, 1, 2, 0.0, 2.0, 1))
        self.assertIsNone(summarize([])["win_rate"])

    def test_backtest_runs_on_synthetic_data(self):
        df = synth(700, seed=3)
        r = backtest(df, "BTCUSD", "scalp", min_score=4.0, step=3)
        for k in ("signals", "trades", "win_rate", "net_r", "max_drawdown_r"):
            self.assertIn(k, r)
        self.assertGreater(r["signals"], 0)


if __name__ == "__main__":
    unittest.main()


class IntentTests(unittest.TestCase):
    def test_classify_from_real_chat_messages(self):
        from services.intents import classify
        cases = {
            "Koi signal hai": "signal",
            "Xausd ka signal do": "signal",
            "gold signal chahiye intraday": "signal",
            "Tp hit howa": "status",
            "Nhai main tumse poochh raha hun jo tumne abhi signal dea ha": "status",
            "signal ka status batao": "status",
            "jo signal diya wo cancel kyun hua": "status",
            "sl hit hua kya": "status",
            "gold ka kya scene hai": "chat",
            "hello": "chat",
            "": "chat",
        }
        for text, want in cases.items():
            self.assertEqual(classify(text), want, text)


class FreshTests(unittest.TestCase):
    def build(self, setup, rows):
        from services.analysis_service import AnalysisService

        clock = Clock()
        market = FakeMarket(clock)
        market.df = make_df([(ts, o, h, l, c, 0) for ts, o, h, l, c in rows]) if rows else None
        svc = AnalysisService(market)
        svc.run = lambda symbol, mode, priority="normal": ({"symbol": symbol}, setup)
        return svc, market

    def sell_limit(self, **kw):
        return setup_dict(side="sell", entry_type="LIMIT", entry=4087.66, sl=4092.20, tp1=4080.85, tp2=4076.30,
                          symbol="XAUUSD", last_candle_ts=1000, tf_seconds=300, **kw)

    def test_limit_discarded_when_entry_already_touched_in_gap(self):
        # gap = 1300 se; wahan price entry (4087.66) tak chadh gayi
        svc, _ = self.build(self.sell_limit(), [(1300, 4086, 4088.0, 4085.5, 4087.0), (1360, 4087, 4087.2, 4084, 4084.5)])
        a, setup = svc.run_fresh("XAUUSD", "scalp")
        self.assertIsNone(setup)

    def test_limit_discarded_when_price_already_ran_to_tp1(self):
        svc, _ = self.build(self.sell_limit(), [(1300, 4086, 4086.5, 4080.0, 4080.5)])
        self.assertIsNone(svc.run_fresh("XAUUSD", "scalp")[1])

    def test_limit_kept_when_still_waiting(self):
        svc, _ = self.build(self.sell_limit(), [(1300, 4085, 4086.0, 4084.0, 4085.0)])
        setup = svc.run_fresh("XAUUSD", "scalp")[1]
        self.assertEqual(setup["entry"], 4087.66)

    def test_candles_before_gap_ignored(self):
        svc, _ = self.build(self.sell_limit(), [(1100, 4090, 4095.0, 4089.0, 4090.0), (1300, 4085, 4086.0, 4084.0, 4085.0)])
        self.assertIsNotNone(svc.run_fresh("XAUUSD", "scalp")[1])

    def test_market_entry_moves_to_live_price_keeping_distances(self):
        s = setup_dict(entry_type="MARKET", entry=100.0, sl=99.0, tp1=101.5, tp2=102.5, last_candle_ts=1000, tf_seconds=300)
        svc, _ = self.build(s, [(1300, 100.5, 100.9, 100.4, 100.8)])
        out = svc.run_fresh("BTCUSD", "scalp")[1]
        self.assertAlmostEqual(out["entry"], 100.8)
        self.assertAlmostEqual(out["entry"] - out["sl"], 1.0)
        self.assertAlmostEqual(out["tp1"] - out["entry"], 1.5)

    def test_no_live_data_keeps_setup(self):
        svc, market = self.build(self.sell_limit(), None)
        market.error = DataError("down")
        self.assertIsNotNone(svc.run_fresh("XAUUSD", "scalp")[1])
        market.error = BudgetExhausted("limit")
        self.assertIsNotNone(svc.run_fresh("XAUUSD", "scalp")[1])


class StatusViewTests(unittest.TestCase):
    def test_cancel_message_explains_no_trade_happened(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(symbol="XAUUSD", side="sell", entry=4093.21, sl=4098.17, tp1=4085.76, tp2=4080.8), "scan", [2])
        txt = formatter.format_event(sig, {"type": "CANCELLED", "price": None, "ts": 1, "note": ""})
        self.assertIn("4093.21", txt)
        self.assertIn("koi trade nahi laga", txt)

    def test_my_signals_view_with_events(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [2])
        svc.process(sig, [(sig["last_candle_ts"], 101, 101, 99.9, 100.5)])
        sigs = repo.open_for_user(2)
        text = formatter.format_my_signals(sigs, {s["id"]: repo.events(s["id"]) for s in sigs})
        self.assertIn("Entry hit", text)
        self.assertIn("ACTIVE", text)
        self.assertIn("Aap ka abhi koi signal nahi", formatter.format_my_signals([], {}))

    def test_chat_context_includes_closed_signals(self):
        db, clock, users, approval, repo, svc = env()
        sig = svc.create(setup_dict(), "scan", [2])
        svc.process(sig, [(sig["last_candle_ts"], 100.5, 101.7, 98.5, 99)])   # entry + SL
        ai = FakeAI("ok")
        chat = ChatService(ai, ChatMemory(ChatRepo(db), ai, clock=clock), FakeAnalysis(), None, repo)
        chat.reply_blocking(2, "kya hua")
        ctx = " ".join(m["content"] for m in ai.calls[0] if m["role"] == "system")
        self.assertIn("SL", ctx)
        self.assertIn("band signals", ctx)
