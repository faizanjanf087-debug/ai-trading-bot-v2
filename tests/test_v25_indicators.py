"""V2.5: stochastic, VWAP, pivot, Asia range, shock (tez move) guard."""
import unittest

import numpy as np
import pandas as pd

from analysis import indicators as ind
from analysis.levels import asia_range, pivot_levels
from analysis.signal_engine import build_setup


def _df(closes, start="2026-10-20 00:00", freq="5min", spread=0.5, vol=100.0):
    idx = pd.date_range(start, periods=len(closes), freq=freq)
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "open": c, "high": c + spread, "low": c - spread, "close": c,
        "volume": np.full(len(c), vol),
    }, index=idx)


class StochasticTests(unittest.TestCase):
    def test_range_0_to_100(self):
        rng = np.random.default_rng(1)
        closes = 100 + np.cumsum(rng.normal(0, 1, 200))
        k, d = ind.stochastic(_df(closes, spread=0.8))
        kv = k.dropna()
        self.assertTrue(((kv >= 0) & (kv <= 100)).all())
        self.assertFalse(d.dropna().empty)

    def test_top_of_range_is_high(self):
        closes = np.linspace(100, 150, 60)          # steady uptrend: close at high
        k, _ = ind.stochastic(_df(closes))
        self.assertGreater(k.iloc[-1], 80)


class VwapTests(unittest.TestCase):
    def test_resets_each_utc_day(self):
        d1 = _df(np.full(12, 100.0), start="2026-10-20 00:00")
        d2 = _df(np.full(12, 200.0), start="2026-10-21 00:00")
        v = ind.vwap_session(pd.concat([d1, d2]))
        self.assertAlmostEqual(v.iloc[11], 100.0, places=6)
        self.assertAlmostEqual(v.iloc[12], 200.0, places=6)   # naye din par naya VWAP


class ShockTests(unittest.TestCase):
    def test_flat_market_no_shock(self):
        closes = np.full(40, 100.0) + np.sin(np.arange(40)) * 0.2
        self.assertIsNone(ind.shock(_df(closes)))

    def test_sharp_crash_detected(self):
        closes = list(np.full(40, 100.0)) + [99.0, 97.0, 94.0]
        s = ind.shock(_df(closes))
        self.assertIsNotNone(s)
        self.assertEqual(s["dir"], "down")
        self.assertGreater(s["size_atr"], 3)

    def test_build_setup_blocked_during_shock(self):
        a = {"symbol": "XAUUSD", "mode": "scalp", "tf": "5m", "side": "buy", "price": 100.0, "atr": 1.0,
             "score_buy": 8.0, "score_sell": 1.0, "reasons_buy": ["x"], "reasons_sell": [],
             "levels": [], "ema_fast": 99.9, "htf_trend": "up", "ranging": False,
             "last_candle_ts": 0, "shock": {"dir": "down", "size_atr": 4.0}}
        self.assertIsNone(build_setup(a, min_score=6.0))
        a["shock"] = None
        self.assertIsNotNone(build_setup(a, min_score=6.0))


class PivotAndAsiaTests(unittest.TestCase):
    def test_pivot_uses_previous_day(self):
        prev = _df(np.array([100.0, 110.0, 90.0, 104.0]), start="2026-10-20 00:00", freq="6h", spread=0.0)
        today = _df(np.full(4, 105.0), start="2026-10-21 00:00", freq="6h", spread=0.0)
        p = pivot_levels(pd.concat([prev, today]))
        # prev day: H=110.5 (spread 0 => high=close, max 110), L=90, C=104
        self.assertAlmostEqual(p["P"], (110 + 90 + 104) / 3, places=6)
        self.assertLess(p["S1"], p["P"])
        self.assertGreater(p["R1"], p["P"])

    def test_pivot_none_without_previous_day(self):
        self.assertIsNone(pivot_levels(_df(np.full(10, 100.0))))

    def test_asia_range_after_session_only(self):
        # aaj ke 00:00-06:55 UTC (session khatam, last candle 07:00+)
        df = _df(np.linspace(100, 101, 96), start="2026-10-21 00:00", freq="5min", spread=0.2)
        r = asia_range(df)
        self.assertIsNotNone(r)
        self.assertLess(r["low"], r["high"])
        # session abhi khatam nahi (sirf 03:00 tak data)
        self.assertIsNone(asia_range(df.iloc[:36]))


if __name__ == "__main__":
    unittest.main()
