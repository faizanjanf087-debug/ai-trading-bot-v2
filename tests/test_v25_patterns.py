"""V2.5: Head & Shoulders, triangles, tez move ki chetavni."""
import unittest

import numpy as np
import pandas as pd

from analysis.patterns import chart_patterns, head_shoulders, triangles
from services import formatter


def _path(points, spread=0.2, start="2026-10-20 00:00"):
    """Points (index, price) ke beech seedhi lakeer; high/low = close +/- spread."""
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    idx = np.arange(int(xs[-1]) + 1)
    close = np.interp(idx, xs, ys)
    times = pd.date_range(start, periods=len(idx), freq="5min")
    return pd.DataFrame({"open": close, "high": close + spread, "low": close - spread,
                         "close": close, "volume": 100.0}, index=times)


class HeadShouldersTests(unittest.TestCase):
    def test_bearish_head_and_shoulders_after_neckline_break(self):
        df = _path([(0, 100), (20, 110), (30, 100), (40, 115), (50, 100), (60, 110), (70, 98), (79, 93)])
        names = [n for n, _ in head_shoulders(df, atr_value=2.0)]
        self.assertIn("Head & Shoulders", names)

    def test_no_signal_before_neckline_break(self):
        df = _path([(0, 100), (20, 110), (30, 100), (40, 115), (50, 100), (60, 110), (70, 104), (79, 105)])
        self.assertEqual(head_shoulders(df, atr_value=2.0), [])

    def test_inverse_head_and_shoulders(self):
        df = _path([(0, 110), (20, 100), (30, 110), (40, 95), (50, 110), (60, 100), (70, 112), (79, 118)])
        names = [n for n, _ in head_shoulders(df, atr_value=2.0)]
        self.assertIn("Inverse Head & Shoulders", names)


class TriangleTests(unittest.TestCase):
    def test_ascending_triangle_breakout(self):
        df = _path([(0, 100), (10, 105), (25, 110), (30, 100), (45, 110), (55, 105), (70, 109), (79, 115)])
        names = [n for n, _ in triangles(df, atr_value=2.0)]
        self.assertIn("Ascending Triangle Breakout", names)

    def test_no_triangle_without_breakout(self):
        df = _path([(0, 100), (10, 105), (25, 110), (30, 100), (45, 110), (55, 105), (70, 109), (79, 109.5)])
        self.assertEqual(triangles(df, atr_value=2.0), [])


class ChartPatternWiringTests(unittest.TestCase):
    def test_chart_patterns_includes_new_patterns(self):
        df = _path([(0, 100), (20, 110), (30, 100), (40, 115), (50, 100), (60, 110), (70, 98), (79, 93)])
        names = [n for n, _ in chart_patterns(df, atr_value=2.0)]
        self.assertIn("Head & Shoulders", names)


class ShockMessageTests(unittest.TestCase):
    def test_format_shock_has_no_exness_and_disclaimer(self):
        text = formatter.format_shock("XAUUSD", {"dir": "down", "size_atr": 4.2})
        self.assertIn("XAUUSD", text)
        self.assertIn("4.2", text)
        self.assertNotIn("Exness", text)
        self.assertIn("financial advice", text)


if __name__ == "__main__":
    unittest.main()


class TripleTopTests(unittest.TestCase):
    def test_triple_top_breakdown(self):
        df = _path([(0, 100), (15, 110), (25, 100), (35, 110), (45, 100), (55, 110), (70, 98), (79, 93)])
        from analysis.patterns import triple_tops
        names = [n for n, _ in triple_tops(df, atr_value=2.0)]
        self.assertIn("Triple Top", names)

    def test_triple_top_no_signal_without_break(self):
        df = _path([(0, 100), (15, 110), (25, 100), (35, 110), (45, 100), (55, 110), (70, 104), (79, 105)])
        from analysis.patterns import triple_tops
        self.assertEqual(triple_tops(df, atr_value=2.0), [])
