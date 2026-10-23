import unittest

from services import lifecycle as lc


def sig(side="buy", **kw):
    base = dict(side=side, entry=100.0, sl=99.0, sl_initial=99.0, tp1=101.5, tp2=102.5,
                status="PENDING", expires_ts=10_000, last_candle_ts=0, activated_ts=None)
    if side == "sell":
        base.update(sl=101.0, sl_initial=101.0, tp1=98.5, tp2=97.5)
    base.update(kw)
    return base


def C(ts, o, h, l, c):
    return (ts, o, h, l, c)


def types(events):
    return [e["type"] for e in events]


class LifecycleTests(unittest.TestCase):
    def test_pending_not_touched_stays_pending(self):
        s, ev = lc.evaluate(sig(), [C(60, 101, 101.2, 100.5, 101)], 100)
        self.assertEqual(s["status"], "PENDING")
        self.assertEqual(ev, [])

    def test_limit_buy_entry_then_tp1_then_tp2(self):
        s, ev = lc.evaluate(sig(), [
            C(60, 101, 101.0, 99.9, 100.2),     # entry hit
            C(120, 100.2, 101.6, 100.1, 101.5),  # TP1
            C(180, 101.5, 102.6, 101.0, 102.5),  # TP2
        ], 200)
        self.assertEqual(types(ev), ["ENTRY_HIT", "TP1_HIT", "SL_TO_BE", "TP2_HIT"])
        self.assertEqual(s["status"], "TP2")
        self.assertEqual(s["result_r"], 2.0)   # 0.5*1.5 + 0.5*2.5
        self.assertEqual(s["sl"], 100.0)

    def test_sl_hit_after_entry(self):
        s, ev = lc.evaluate(sig(), [C(60, 101, 101, 99.9, 100.1), C(120, 100, 100.2, 98.9, 99)], 200)
        self.assertEqual(types(ev), ["ENTRY_HIT", "SL_HIT"])
        self.assertEqual((s["status"], s["result_r"]), ("SL", -1.0))

    def test_entry_candle_ignores_tp(self):
        # Entry wali candle ki high TP se upar hai, lekin TP agle candle se dekha jata hai
        s, ev = lc.evaluate(sig(), [C(60, 100.5, 102.0, 99.9, 101.0)], 100)
        self.assertEqual(types(ev), ["ENTRY_HIT"])
        self.assertEqual(s["status"], "ACTIVE")

    def test_entry_candle_checks_sl(self):
        s, ev = lc.evaluate(sig(), [C(60, 100.5, 100.6, 98.5, 99.0)], 100)
        self.assertEqual(types(ev), ["ENTRY_HIT", "SL_HIT"])
        self.assertEqual(s["status"], "SL")

    def test_reevaluating_entry_candle_still_ignores_tp(self):
        s, _ = lc.evaluate(sig(), [C(60, 100.5, 100.6, 99.9, 100.2)], 100)
        # agli poll par wahi candle dobara, ab uski high TP1 tak gayi
        s, ev = lc.evaluate(s, [C(60, 100.5, 101.7, 99.9, 101.6)], 110)
        self.assertEqual(ev, [])
        self.assertEqual(s["status"], "ACTIVE")
        s, ev = lc.evaluate(s, [C(120, 101.6, 101.8, 101.0, 101.5)], 130)
        self.assertEqual(types(ev), ["TP1_HIT", "SL_TO_BE"])

    def test_sl_and_tp_same_candle_sl_first(self):
        s, _ = lc.evaluate(sig(), [C(60, 100.5, 100.6, 99.9, 100.2)], 100)
        s, ev = lc.evaluate(s, [C(120, 100.2, 101.8, 98.5, 100)], 200)
        self.assertEqual(types(ev), ["SL_HIT"])

    def test_breakeven_after_tp1(self):
        s, _ = lc.evaluate(sig(), [C(60, 100.5, 100.6, 99.9, 100.2), C(120, 100.2, 101.6, 100.1, 101.5)], 150)
        self.assertEqual(s["status"], "TP1")
        s, ev = lc.evaluate(s, [C(180, 101.5, 101.6, 99.95, 100.1)], 200)
        self.assertEqual(types(ev), ["BE_HIT"])
        self.assertEqual(s["status"], "BE")
        self.assertEqual(s["result_r"], 0.75)  # 0.5 * 1.5R

    def test_no_breakeven_option(self):
        s, _ = lc.evaluate(sig(), [C(60, 100.5, 100.6, 99.9, 100.2), C(120, 100.2, 101.6, 100.1, 101.5)], 150, False)
        self.assertEqual(s["sl"], 99.0)
        s, ev = lc.evaluate(s, [C(180, 101.5, 101.6, 98.9, 99.0)], 200, False)
        self.assertEqual(types(ev), ["SL_HIT"])

    def test_sell_side(self):
        s, ev = lc.evaluate(sig("sell"), [
            C(60, 99, 100.1, 98.9, 99.5),        # entry
            C(120, 99.5, 99.6, 98.4, 98.5),      # TP1
            C(180, 98.5, 98.6, 97.4, 97.5),      # TP2
        ], 200)
        self.assertEqual(types(ev), ["ENTRY_HIT", "TP1_HIT", "SL_TO_BE", "TP2_HIT"])
        self.assertEqual(s["status"], "TP2")

    def test_cancel_if_price_runs_to_tp1_before_entry(self):
        s, ev = lc.evaluate(sig(), [C(60, 101, 101.7, 100.5, 101.6)], 100)
        self.assertEqual(types(ev), ["CANCELLED"])
        self.assertEqual(s["status"], "CANCELLED")

    def test_expire_by_candle_and_by_clock(self):
        s, ev = lc.evaluate(sig(expires_ts=100), [C(120, 101, 101.2, 100.5, 101)], 130)
        self.assertEqual((s["status"], types(ev)), ("EXPIRED", ["EXPIRED"]))
        s, ev = lc.evaluate(sig(expires_ts=100), [], 130)
        self.assertEqual(s["status"], "EXPIRED")

    def test_old_candles_skipped(self):
        s, ev = lc.evaluate(sig(last_candle_ts=120), [C(60, 100, 100, 90, 90), C(120, 101, 101, 100.5, 101)], 200)
        self.assertEqual(s["status"], "PENDING")

    def test_market_entry_active_from_start(self):
        s0 = sig(status="ACTIVE", activated_ts=5, last_candle_ts=60)
        s, ev = lc.evaluate(s0, [C(60, 100, 101.6, 99.9, 101.5)], 100)
        self.assertEqual(types(ev), ["TP1_HIT", "SL_TO_BE"])

    def test_terminal_status_not_reprocessed(self):
        s, _ = lc.evaluate(sig(), [C(60, 100.5, 100.6, 98.5, 99.0)], 100)
        self.assertEqual(s["status"], "SL")


if __name__ == "__main__":
    unittest.main()
