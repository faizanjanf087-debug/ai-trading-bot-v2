"""V2.10: pattern weights ek jagah se; naam aur weight ka mel."""
import unittest

from analysis.patterns import DEFAULT_PATTERN_WEIGHT, PATTERN_WEIGHTS, pattern_weight


class PatternWeightTests(unittest.TestCase):
    def test_reversals_weigh_more_than_breakouts(self):
        self.assertGreater(pattern_weight("Head & Shoulders"), pattern_weight("Ascending Triangle Breakout"))
        self.assertGreater(pattern_weight("Triple Top"), pattern_weight("Range Breakout Up"))

    def test_unknown_pattern_gets_default(self):
        self.assertEqual(pattern_weight("Some Future Pattern"), DEFAULT_PATTERN_WEIGHT)

    def test_all_known_names_have_positive_weight(self):
        for name, w in PATTERN_WEIGHTS.items():
            self.assertGreater(w, 0, name)


if __name__ == "__main__":
    unittest.main()
