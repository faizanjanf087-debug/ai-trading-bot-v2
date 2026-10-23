import unittest

import numpy as np
import pandas as pd

from analysis import indicators as ind
from analysis.divergence import rsi_divergence
from analysis.levels import fibonacci, market_structure, nearest_level, pivots, support_resistance
from analysis.patterns import candlestick, chart_patterns
from analysis.signal_engine import analyze, build_setup
from tests.helpers import synth


def df_from(rows, freq="5min"):
    idx = pd.date_range("2026-01-05", periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=0.0)


class IndicatorTests(unittest.TestCase):
    def test_rsi_extremes(self):
        up = pd.Series(np.arange(1, 60, dtype=float))
        self.assertGreater(ind.rsi(up).iloc[-1], 95)
        down = pd.Series(np.arange(60, 1, -1, dtype=float))
        self.assertLess(ind.rsi(down).iloc[-1], 5)
        self.assertEqual(ind.rsi(pd.Series([100.0] * 50)).iloc[-1], 50.0)

    def test_macd_trend_sign(self):
        up = pd.Series(np.linspace(100, 130, 120))
        line, sig, hist = ind.macd(up)
        self.assertGreater(line.iloc[-1], 0)

    def test_atr_constant_range(self):
        df = df_from([[10, 11, 9, 10]] * 40)
        self.assertAlmostEqual(ind.atr(df).iloc[-1], 2.0, places=3)

    def test_volume_spike(self):
        df = synth(60)
        df.loc[df.index[-1], "volume"] = 10_000
        self.assertTrue(ind.volume_spike(df))
        self.assertIsNone(ind.volume_spike(synth(60, volume=False)))

    def test_resample(self):
        df = df_from([[i, i + 1, i - 1, i + 0.5] for i in range(10)])
        r = ind.resample(df, 3)
        self.assertEqual(len(r), 3)
        # aakhir se gin kar: pehli candle (index 1) se shuru
        self.assertEqual(r["open"].iloc[0], 1)
        self.assertEqual(r["high"].iloc[0], 4)
        self.assertEqual(r["close"].iloc[-1], 9.5)


class LevelTests(unittest.TestCase):
    def zigzag(self):
        pts = []
        price = 100.0
        for _ in range(8):
            for p in (101, 102, 103, 104, 105, 104, 103, 102, 101, 100):
                pts.append([p, p + 0.2, p - 0.2, p])
        return df_from(pts)

    def test_pivots_found(self):
        highs, lows = pivots(self.zigzag(), 3)
        self.assertTrue(len(highs) >= 5 and len(lows) >= 5)
        self.assertTrue(all(abs(p - 105.2) < 0.01 for _, p in highs))

    def test_support_resistance_clusters(self):
        df = self.zigzag()
        lv = support_resistance(df, atr_value=1.0)
        prices = [round(l["price"]) for l in lv]
        self.assertIn(105, prices)
        top = max(lv, key=lambda l: l["touches"])
        self.assertGreaterEqual(top["touches"], 4)
        self.assertIsNotNone(nearest_level(lv, 102.5, "support"))
        self.assertIsNotNone(nearest_level(lv, 102.5, "resistance"))
        self.assertIsNone(nearest_level(lv, 200, "resistance"))

    def test_fibonacci_up_and_down_move(self):
        def row(p):
            return [p, p + 0.3, p - 0.3, p]

        up = ([row(100.0)] * 6 + [row(100 - i) for i in range(10)]      # girawat 100 -> 91
              + [row(91 + i) for i in range(20)]                          # chadhai 91 -> 110
              + [row(109 - i) for i in range(5)] + [row(105.5)] * 4)     # chhota pullback
        f = fibonacci(df_from(up), n=3)
        self.assertEqual(f["direction"], "up")
        self.assertAlmostEqual(f["start"], 90.7, places=1)
        self.assertAlmostEqual(f["end"], 110.3, places=1)
        self.assertAlmostEqual(f["levels"][0.5], f["end"] - 0.5 * (f["end"] - f["start"]), places=6)
        down = [[2 * 200 - r[0], 2 * 200 - r[2], 2 * 200 - r[1], 2 * 200 - r[3]] for r in up]  # sheesha
        self.assertEqual(fibonacci(df_from(down), n=3)["direction"], "down")


class PatternTests(unittest.TestCase):
    base = [[100 - i * 0.2, 100 - i * 0.2 + 0.3, 100 - i * 0.2 - 0.3, 100 - i * 0.2 - 0.1] for i in range(10)]

    def test_bullish_engulfing(self):
        rows = self.base + [[98.2, 98.3, 97.5, 97.6], [97.4, 98.9, 97.3, 98.8]]
        names = [n for n, _ in candlestick(df_from(rows))]
        self.assertIn("Bullish Engulfing", names)

    def test_bearish_engulfing(self):
        up = [[100 + i * 0.2, 100 + i * 0.2 + 0.3, 100 + i * 0.2 - 0.3, 100 + i * 0.2 + 0.1] for i in range(10)]
        rows = up + [[102.0, 102.5, 101.9, 102.4], [102.6, 102.7, 101.4, 101.5]]
        self.assertIn("Bearish Engulfing", [n for n, _ in candlestick(df_from(rows))])

    def test_hammer_in_downtrend(self):
        rows = self.base + [[98.0, 98.05, 97.0, 98.0 + 0.02]]
        rows[-1] = [98.0, 98.1, 96.8, 98.05]
        names = [n for n, b in candlestick(df_from(rows))]
        self.assertIn("Hammer", names)

    def test_doji(self):
        rows = self.base + [[98.0, 98.5, 97.5, 98.01]]
        self.assertIn("Doji", [n for n, _ in candlestick(df_from(rows))])

    def test_range_breakout(self):
        rows = [[100.0 + (i % 2) * 0.2, 100.4, 99.8, 100.1] for i in range(40)]
        rows[-1] = [100.2, 102.5, 100.1, 102.4]
        names = [n for n, _ in chart_patterns(df_from(rows), atr_value=0.6)]
        self.assertIn("Range Breakout Up", names)

    def test_no_patterns_on_short_data(self):
        self.assertEqual(candlestick(df_from([[1, 2, 0, 1]] * 3)), [])
        self.assertEqual(chart_patterns(df_from([[1, 2, 0, 1]] * 10), 1.0), [])


class DivergenceTests(unittest.TestCase):
    def test_bullish_divergence(self):
        # price do baar neeche gaya (lower low), RSI series haath se banayi: dusre low par RSI zyada
        n = 80
        close = np.full(n, 100.0)
        low = np.full(n, 100.0)
        high = low + 1
        low[40], low[60] = 90.0, 88.0
        df = pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 0.0},
                          index=pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC"))
        rsi = pd.Series(50.0, index=df.index)
        rsi.iloc[40], rsi.iloc[60] = 20.0, 30.0
        self.assertEqual(rsi_divergence(df, rsi), "bullish")
        rsi.iloc[60] = 15.0
        self.assertIsNone(rsi_divergence(df, rsi))


class EngineTests(unittest.TestCase):
    def test_analyze_shape_and_none_on_short(self):
        self.assertIsNone(analyze(synth(30), "BTCUSD", "scalp"))
        a = analyze(synth(300), "BTCUSD", "scalp")
        for k in ("price", "atr", "rsi", "levels", "score_buy", "score_sell", "reasons_buy", "htf_trend"):
            self.assertIn(k, a)
        self.assertGreaterEqual(a["score_buy"], 0)

    def _a(self, **kw):
        a = dict(symbol="XAUUSD", mode="scalp", tf="5m", price=100.0, atr=1.0, ema_fast=99.5, ema_slow=98.0,
                 htf_trend="up", rsi=40, macd_hist=0.1, macd_hist_prev=0.05, macd_cross=None, levels=[],
                 fib=None, candles=[], chart_patterns=[], divergence=None, volume_spike=None, last_candle_ts=1000,
                 score_buy=7.0, score_sell=1.0, reasons_buy=["x"], reasons_sell=[])
        a.update(kw)
        return a

    def test_setup_none_if_low_score_or_close_scores(self):
        self.assertIsNone(build_setup(self._a(score_buy=4.0)))
        self.assertIsNone(build_setup(self._a(score_buy=7.0, score_sell=6.0)))
        self.assertIsNone(build_setup(None))

    def test_buy_limit_at_support(self):
        a = self._a(levels=[{"price": 98.8, "touches": 3, "kind": "support"},
                            {"price": 110.0, "touches": 2, "kind": "resistance"}])
        s = build_setup(a)
        self.assertEqual((s["side"], s["entry_type"]), ("buy", "LIMIT"))
        self.assertLess(s["entry"], 100.0)
        self.assertLess(s["sl"], s["entry"])
        risk = s["entry"] - s["sl"]
        self.assertAlmostEqual(s["tp1"], s["entry"] + 1.5 * risk)
        self.assertAlmostEqual(s["tp2"], s["entry"] + 2.5 * risk)
        self.assertGreaterEqual(risk, 1.0)

    def test_market_entry_when_no_level_nearby(self):
        s = build_setup(self._a(ema_fast=99.95, levels=[]))
        self.assertEqual(s["entry_type"], "MARKET")
        self.assertEqual(s["entry"], 100.0)

    def test_sell_side_mirrored(self):
        a = self._a(score_buy=1.0, score_sell=7.5, ema_fast=100.4, reasons_sell=["y"],
                    levels=[{"price": 101.2, "touches": 2, "kind": "resistance"}])
        s = build_setup(a)
        self.assertEqual(s["side"], "sell")
        self.assertGreater(s["sl"], s["entry"])
        self.assertLess(s["tp2"], s["tp1"])
        self.assertLess(s["tp1"], s["entry"])

    def test_rejected_when_opposing_level_blocks_tp(self):
        a = self._a(ema_fast=99.95, levels=[{"price": 100.5, "touches": 4, "kind": "resistance"}])
        self.assertIsNone(build_setup(a))


class MultiTimeframeTests(unittest.TestCase):
    def test_adx_strong_trend_vs_flat(self):
        up = synth(200, drift=0.4, vol=0.1)
        adx_s, plus_di, minus_di = ind.adx(up)
        self.assertGreater(adx_s.iloc[-1], 25)
        self.assertGreater(plus_di.iloc[-1], minus_di.iloc[-1])
        flat = df_from([[100 + (i % 2) * 0.1, 100.3, 99.8, 100.05 - (i % 2) * 0.1] for i in range(120)])
        self.assertLess(ind.adx(flat)[0].iloc[-1], 15)

    def test_bollinger_contains_price_and_widens_with_volatility(self):
        close = pd.Series(np.r_[np.full(30, 100.0), np.linspace(100, 110, 30)])
        mid, up, lo = ind.bollinger(close)
        self.assertTrue((up.dropna() >= lo.dropna()).all())
        self.assertGreater(up.iloc[-1] - lo.iloc[-1], up.iloc[25] - lo.iloc[25])

    def test_market_structure(self):
        def wave(levels):
            rows = []
            for lo, hi in levels:
                for p in list(np.linspace(lo, hi, 8)) + list(np.linspace(hi, lo, 8)):
                    rows.append([p, p + 0.1, p - 0.1, p])
            return df_from(rows)
        self.assertEqual(market_structure(wave([(100, 105), (102, 108), (104, 111), (106, 114)])), "bullish")
        self.assertEqual(market_structure(wave([(106, 114), (104, 111), (102, 108), (100, 105)])), "bearish")
        self.assertIsNone(market_structure(df_from([[1, 2, 0, 1]] * 10)))

    def test_analyze_reports_three_timeframes(self):
        a = analyze(synth(700, drift=0.05), "BTCUSD", "scalp")
        self.assertEqual((a["htf_tf"], a["htf2_tf"]), ("15m", "1h"))
        a = analyze(synth(720, freq="15min", drift=0.05), "BTCUSD", "intraday")
        self.assertEqual((a["htf_tf"], a["htf2_tf"]), ("1h", "4h"))
        self.assertIn(a["mtf_alignment"], ("aligned_up", "aligned_down", "mixed"))
        # kam data par bhi chalta hai, top timeframe flat rehta hai
        self.assertEqual(analyze(synth(250), "BTCUSD", "scalp")["htf2_trend"], "flat")

    def test_aligned_timeframes_add_score_and_reasons(self):
        from analysis.signal_engine import _mtf_alignment, _score
        self.assertEqual(_mtf_alignment("up", "up", "up"), "aligned_up")
        self.assertEqual(_mtf_alignment("up", "up", "down"), "mixed")
        self.assertEqual(_mtf_alignment("flat", "flat", "flat"), "mixed")
        base = dict(symbol="X", mode="scalp", tf="5m", price=100.0, atr=1.0, ema_fast=100.0, ema_slow=100.0,
                    htf_trend="flat", rsi=50, macd_hist=0.0, macd_hist_prev=0.0, macd_cross=None, levels=[],
                    fib=None, candles=[], chart_patterns=[], divergence=None, volume_spike=None)
        a = dict(base, htf2_trend="up", mtf_alignment="aligned_up", structure="bullish")
        _score(a)
        self.assertEqual(a["score_buy"], 2.5)
        self.assertIn("Multi-timeframe aligned up", a["reasons_buy"])
        self.assertEqual(a["score_sell"], 0)

    def test_ranging_market_needs_extra_score(self):
        weak = EngineTests()._a(score_buy=6.2, ranging=True)
        self.assertIsNone(build_setup(weak, min_score=6.0))
        strong = EngineTests()._a(score_buy=6.6, ranging=True, ema_fast=99.95)
        self.assertIsNotNone(build_setup(strong, min_score=6.0))
        self.assertIsNotNone(build_setup(EngineTests()._a(score_buy=6.2, ema_fast=99.95), min_score=6.0))

    def test_format_and_prompt_include_new_fields(self):
        from ai.prompts import _compact
        from services.formatter import format_analysis
        a = analyze(synth(700, drift=0.05), "BTCUSD", "scalp")
        text = format_analysis(a)
        self.assertIn("Multi-TF:", text)
        self.assertIn("ADX", text)
        c = _compact(a)
        self.assertIn("trend_by_timeframe", c)
        self.assertIn("multi_timeframe", c)
        # purana analysis dict (naye fields ke baghair) bhi nahi toot'ta
        old = {k: v for k, v in a.items() if k not in ("htf2_tf", "htf2_trend", "mtf_alignment", "adx", "structure")}
        self.assertNotIn("Multi-TF:", format_analysis(old))
        _compact(old)


if __name__ == "__main__":
    unittest.main()
