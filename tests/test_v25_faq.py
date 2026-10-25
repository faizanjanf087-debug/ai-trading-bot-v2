"""V2.13: pakke jawab (FAQ) ka matching."""
import unittest

from services.faq import answer


class FaqTests(unittest.TestCase):
    def test_signal_meaning(self):
        self.assertIn("entry, stop-loss", answer("signal kya hota hai"))

    def test_limit_question(self):
        self.assertIn("LIMIT entry", answer("limit entry kya hai"))

    def test_sl_question(self):
        self.assertIn("Stop-loss", answer("SL kya hai"))

    def test_pairs_filled_from_watchlist(self):
        out = answer("kaun kaun se pairs hain", pairs=["XAUUSD", "BTCUSD"])
        self.assertIn("XAUUSD, BTCUSD", out)

    def test_no_signal_reason(self):
        self.assertIn("score", answer("signal kyun nahi aaya"))

    def test_unknown_returns_none(self):
        self.assertIsNone(answer("mausam kaisa hai"))

    def test_empty_returns_none(self):
        self.assertIsNone(answer(""))

    def test_guarantee_disclaimer(self):
        self.assertIn("financial advice", answer("kya guarantee hai profit ki"))


if __name__ == "__main__":
    unittest.main()
