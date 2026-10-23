import unittest

from analysis.factors import factor_key, factor_keys, htf_alignment
from analysis.signal_engine import build_setup
from db.database import Database
from db.journal import JournalRepo
from db.signals import SignalRepo
from db.users import UserRepo
from services import formatter, report
from services.approval import ApprovalService
from services.signal_service import SignalService
from tests.test_services import Clock, NOW, setup_dict


class FactorTests(unittest.TestCase):
    def test_numbers_and_timeframes_removed(self):
        self.assertEqual(factor_key("5m trend up (EMA20>EMA50)"), "ltf_trend_up")
        self.assertEqual(factor_key("15m trend down (EMA20<EMA50)"), "ltf_trend_down")
        self.assertEqual(factor_key("Near support 4068.4 (2 touches)"), "near_support")
        self.assertEqual(factor_key("Near resistance 2396.5 (4 touches)"), "near_resistance")
        self.assertEqual(factor_key("RSI oversold (28)"), "rsi_oversold")
        self.assertEqual(factor_key("Fib 50-61.8% pullback in uptrend"), "fib_pullback_in_uptrend")
        self.assertEqual(factor_key("Double Top"), "double_top")
        self.assertEqual(factor_key("Higher timeframe trend up"), "higher_timeframe_trend_up")

    def test_keys_sorted_unique(self):
        self.assertEqual(factor_keys(["Double Top", "double top", "MACD bearish cross", ""]),
                         ["double_top", "macd_bearish_cross"])

    def test_htf_alignment(self):
        self.assertEqual(htf_alignment("buy", "up"), "with")
        self.assertEqual(htf_alignment("buy", "down"), "against")
        self.assertEqual(htf_alignment("sell", "down"), "with")
        self.assertEqual(htf_alignment("sell", "up"), "against")
        self.assertEqual(htf_alignment("buy", "flat"), "flat")
        self.assertEqual(htf_alignment("buy", None), "flat")


def make_env():
    db = Database(":memory:")
    clock = Clock()
    users = UserRepo(db)
    approval = ApprovalService(users, 1)
    approval.request_access(2, None, "u2")
    approval.approve(2)
    approval.request_access(3, None, "u3")
    approval.approve(3)
    repo = SignalRepo(db)
    journal = JournalRepo(db)
    svc = SignalService(repo, users, clock, journal=journal)
    return db, repo, journal, svc


ANALYSIS = dict(price=100.0, atr=1.0, rsi=41.0, htf_trend="down", macd_cross="bearish", divergence=None,
                score_buy=2.0, score_sell=7.5)


class JournalTests(unittest.TestCase):
    def test_signal_creation_writes_journal(self):
        db, repo, journal, svc = make_env()
        setup = setup_dict(side="sell", entry=100.0, sl=101.0, tp1=98.5, tp2=97.5,
                           reasons=["5m trend down (EMA20<EMA50)", "Double Top", "Near resistance 100.5 (2 touches)"])
        sig = svc.create(setup, "scan", [2], analysis=ANALYSIS, review={"verdict": "take", "confidence": 65})
        j = journal.get(sig["id"])
        self.assertEqual(j["symbol"], "BTCUSD")
        self.assertEqual(j["htf_alignment"], "with")          # sell + higher TF down
        self.assertEqual(j["factors"], ["double_top", "ltf_trend_down", "near_resistance"])
        self.assertEqual((j["ai_verdict"], j["ai_confidence"]), ("take", 65))
        self.assertEqual(j["macd_cross"], "bearish")

    def test_manual_signal_without_review_or_analysis(self):
        db, repo, journal, svc = make_env()
        sig = svc.create(setup_dict(), "user", [2])
        j = journal.get(sig["id"])
        self.assertIsNone(j["ai_verdict"])
        self.assertIsNone(j["htf_alignment"])

    def test_journal_failure_does_not_block_signal(self):
        db, repo, journal, svc = make_env()

        class Broken:
            def add(self, *a, **k):
                raise RuntimeError("db down")

        svc.journal = Broken()
        sig = svc.create(setup_dict(), "scan", [2])
        self.assertIsNotNone(repo.get(sig["id"]))

    def test_closed_rows_join_and_user_scope(self):
        db, repo, journal, svc = make_env()
        a = svc.create(setup_dict(reasons=["Double Bottom"]), "scan", [2], analysis=dict(ANALYSIS, htf_trend="up"))
        b = svc.create(setup_dict(side="sell", sl=101.0, tp1=98.5, tp2=97.5, reasons=["Double Top"]), "scan", [3],
                       analysis=ANALYSIS)
        repo.update(a["id"], status="SL", result_r=-1.0)
        repo.update(b["id"], status="TP2", result_r=1.5)
        self.assertEqual(len(journal.closed_rows()), 2)
        mine = journal.closed_rows(2)
        self.assertEqual([r["id"] for r in mine], [a["id"]])
        self.assertEqual(mine[0]["factors"], ["double_bottom"])
        self.assertEqual(mine[0]["htf_alignment"], "with")      # buy + HTF up

    def test_old_signals_without_journal_still_listed(self):
        db, repo, journal, svc = make_env()
        svc.journal = None
        s = svc.create(setup_dict(), "scan", [2])
        repo.update(s["id"], status="SL", result_r=-1.0)
        rows = journal.closed_rows()
        self.assertEqual(rows[0]["factors"], [])
        self.assertIsNone(rows[0]["htf_alignment"])


def row(i, status, r, side="sell", entry="LIMIT", htf="with", ai="take", factors=(), symbol="XAUUSD"):
    return dict(id=i, symbol=symbol, mode="scalp", side=side, entry_type=entry, status=status, result_r=r,
                source="scan", htf_alignment=htf, ai_verdict=ai, ai_confidence=60, factors=list(factors), score=7.0)


class ReportTests(unittest.TestCase):
    def test_overall_and_missed(self):
        rows = [row(1, "TP2", 1.5), row(2, "SL", -1.0), row(3, "CANCELLED", 0.0), row(4, "CANCELLED", 0.0),
                row(5, "EXPIRED", 0.0), row(6, "BE", 0.75)]
        rep = report.build(rows)
        o = rep["overall"]
        self.assertEqual((o["closed"], o["wins"], o["losses"], o["n"]), (6, 2, 1, 3))
        self.assertAlmostEqual(o["net_r"], 1.25)
        self.assertEqual((o["missed"], o["expired"], o["limit_total"]), (2, 1, 6))
        self.assertAlmostEqual(o["missed_rate"], 33.3, places=1)
        self.assertFalse(rep["reliable"])

    def test_groups_and_factors(self):
        rows = [row(1, "TP2", 1.5, htf="with", ai="take", factors=["double_top", "x"]),
                row(2, "SL", -1.0, htf="against", ai="skip", factors=["double_top"]),
                row(3, "SL", -1.0, htf="against", ai="skip", factors=["double_top"]),
                row(4, "TP2", 1.5, htf="with", ai="none", factors=["x"])]
        rep = report.build(rows)
        htf = dict(rep["groups"]["htf"])
        self.assertEqual((htf["with"]["wins"], htf["with"]["losses"]), (2, 0))
        self.assertEqual((htf["against"]["wins"], htf["against"]["losses"]), (0, 2))
        ai = dict(rep["groups"]["ai"])
        self.assertEqual(ai["skip"]["losses"], 2)
        fac = dict(rep["factors"])
        self.assertEqual((fac["double_top"]["wins"], fac["double_top"]["losses"]), (1, 2))
        self.assertEqual(rep["factors"][0][0], "double_top")      # sab se zyada n

    def test_empty_report_text(self):
        txt = formatter.format_report(report.build([]), "Test")
        self.assertIn("Abhi koi band signal nahi", txt)

    def test_report_text_has_key_sections(self):
        rows = [row(1, "TP2", 1.5, factors=["double_top"]), row(2, "SL", -1.0, factors=["double_top"]),
                row(3, "CANCELLED", 0.0)]
        txt = formatter.format_report(report.build(rows), "Sab signals")
        self.assertIn("Missed", txt)
        self.assertIn("higher TF ke saath", txt)
        self.assertIn("double_top", txt)
        self.assertIn("pakka nahi", txt)           # kam trades ki tanbeeh
        self.assertLess(len(txt), 4000)            # Telegram ki hadd


class EventFormatTests(unittest.TestCase):
    def sig(self, **kw):
        s = dict(id=6, symbol="XAUUSD", side="buy", entry=4069.06, sl=4062.76, tp1=4078.51, status="SL", result_r=-1.0)
        s.update(kw)
        return s

    def test_entry_and_sl_in_same_batch_is_one_message(self):
        evs = [{"type": "ENTRY_HIT", "price": 4069.06, "ts": 1, "note": ""},
               {"type": "SL_HIT", "price": 4062.76, "ts": 1, "note": ""}]
        msgs = formatter.format_events(self.sig(), evs)
        self.assertEqual(len(msgs), 1)
        self.assertIn("Entry hit", msgs[0])
        self.assertIn("SL bhi hit", msgs[0])
        self.assertIn("-1.00R", msgs[0])

    def test_entry_hit_alone_has_no_result(self):
        evs = [{"type": "ENTRY_HIT", "price": 4069.06, "ts": 1, "note": ""}]
        msgs = formatter.format_events(self.sig(status="ACTIVE", result_r=None), evs)
        self.assertNotIn("Result", msgs[0])

    def test_tp1_in_batch_with_tp2_does_not_show_final_result(self):
        evs = [{"type": "TP1_HIT", "price": 4078.0, "ts": 1, "note": ""},
               {"type": "SL_TO_BE", "price": 4069.0, "ts": 1, "note": "x"},
               {"type": "TP2_HIT", "price": 4084.0, "ts": 1, "note": ""}]
        msgs = formatter.format_events(self.sig(status="TP2", result_r=1.5), evs)
        self.assertEqual(len(msgs), 3)
        self.assertNotIn("Result", msgs[0])
        self.assertNotIn("Result", msgs[1])
        self.assertIn("+1.50R", msgs[2])

    def test_entry_then_sl_separate_batches_stay_separate(self):
        msgs = formatter.format_events(self.sig(), [{"type": "SL_HIT", "price": 4062.76, "ts": 2, "note": ""}])
        self.assertEqual(len(msgs), 1)
        self.assertIn("SL hit", msgs[0])
        self.assertIn("-1.00R", msgs[0])


class CounterTrendTests(unittest.TestCase):
    def _a(self, **kw):
        a = dict(symbol="XAUUSD", mode="scalp", tf="5m", price=100.0, atr=1.0, ema_fast=99.95, ema_slow=98.0,
                 htf_trend="down", rsi=40, macd_hist=0.1, macd_hist_prev=0.05, macd_cross=None, levels=[],
                 fib=None, candles=[], chart_patterns=[], divergence=None, volume_spike=None, last_candle_ts=1000,
                 score_buy=6.5, score_sell=1.0, reasons_buy=["x"], reasons_sell=[])
        a.update(kw)
        return a

    def test_default_allows_counter_trend(self):
        self.assertIsNotNone(build_setup(self._a()))

    def test_counter_trend_needs_extra_score(self):
        self.assertIsNone(build_setup(self._a(), 6.0, 1.0))                     # 6.5 < 7.0
        self.assertIsNotNone(build_setup(self._a(score_buy=7.2), 6.0, 1.0))     # 7.2 >= 7.0

    def test_with_trend_unaffected(self):
        self.assertIsNotNone(build_setup(self._a(htf_trend="up"), 6.0, 1.0))
        self.assertIsNotNone(build_setup(self._a(htf_trend="flat"), 6.0, 1.0))

    def test_sell_against_uptrend(self):
        a = self._a(htf_trend="up", score_buy=1.0, score_sell=6.5, reasons_sell=["y"], ema_fast=100.05)
        self.assertIsNone(build_setup(a, 6.0, 1.0))


if __name__ == "__main__":
    unittest.main()
