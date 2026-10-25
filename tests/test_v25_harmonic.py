"""V2.8: Butterfly harmonic, Rising/Falling Wedge, Triple Bottom."""
import unittest

from tests.test_v25_patterns import _path
from analysis.patterns import butterfly, triple_tops, wedges


def _mirror(points):
    return [(i, 200 - p) for i, p in points]


class ButterflyTests(unittest.TestCase):
    BULL = [(0, 101), (10, 100), (25, 120), (35, 104.28), (45, 113.7), (55, 94.6), (62, 97)]

    def test_bullish_butterfly(self):
        df = _path(self.BULL)
        self.assertIn("Bullish Butterfly", [n for n, _ in butterfly(df, atr_value=1.5)])

    def test_bearish_butterfly_mirror(self):
        df = _path(_mirror(self.BULL))
        self.assertIn("Bearish Butterfly", [n for n, _ in butterfly(df, atr_value=1.5)])

    def test_no_butterfly_without_bounce(self):
        df = _path([(0, 101), (10, 100), (25, 120), (35, 104.28), (45, 113.7), (55, 94.6), (62, 94.1)])
        self.assertEqual(butterfly(df, atr_value=1.5), [])


class WedgeTests(unittest.TestCase):
    RISING = [(50, 101), (60, 100), (65, 112), (70, 102.6), (75, 112.8), (80, 104.9), (85, 113.4), (92, 104)]

    def test_rising_wedge_breakdown(self):
        df = _path(self.RISING)
        self.assertIn("Rising Wedge Breakdown", [n for n, _ in wedges(df, atr_value=2.0)])

    def test_falling_wedge_breakout_mirror(self):
        df = _path(_mirror(self.RISING))
        self.assertIn("Falling Wedge Breakout", [n for n, _ in wedges(df, atr_value=2.0)])

    def test_no_wedge_without_breakdown(self):
        df = _path(self.RISING[:-1] + [(92, 110)])
        self.assertEqual(wedges(df, atr_value=2.0), [])


class TripleBottomTests(unittest.TestCase):
    def test_triple_bottom_breakout(self):
        df = _path(_mirror([(0, 100), (15, 110), (25, 100), (35, 110), (45, 100), (55, 110), (70, 98), (79, 93)]))
        self.assertIn("Triple Bottom", [n for n, _ in triple_tops(df, atr_value=2.0)])

if __name__ == "__main__":
    unittest.main()
