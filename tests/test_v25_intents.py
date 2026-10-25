"""V2.5: chat triggers (analyze, watchlist, alerts) bina slash command ke."""
import unittest

from services.intents import route


class ChatTriggerTests(unittest.TestCase):
    def test_analyze_with_symbol(self):
        i = route("btc analyze karo")
        self.assertEqual(i.kind, "analyze")
        self.assertEqual(i.symbols, ("BTCUSD",))
        self.assertEqual(i.mode, "scalp")

    def test_analyze_intraday_word(self):
        i = route("xauusd intraday kaisa lag raha")
        self.assertEqual(i.kind, "analyze")
        self.assertEqual(i.mode, "intraday")

    def test_signal_still_wins_over_analyze(self):
        self.assertEqual(route("xauusd ka signal do").kind, "signal")

    def test_watchlist_trigger(self):
        self.assertEqual(route("watchlist dikhao").kind, "watchlist")

    def test_alerts_trigger(self):
        self.assertEqual(route("mere alerts").kind, "alerts")

    def test_plain_symbol_question_stays_chat(self):
        # bina analysis wale lafz ke symbol wali baat AI chat par hi jaye
        self.assertEqual(route("btc ke baare mein kuch batao").kind, "chat")


if __name__ == "__main__":
    unittest.main()


class TradeStatusFromDatabaseTests(unittest.TestCase):
    def test_pending_typo_goes_to_database_status(self):
        self.assertEqual(route("Panding").kind, "status")

    def test_pending_order_question(self):
        self.assertEqual(route("pending order kahan hai").kind, "status")

    def test_casual_word_stays_chat(self):
        self.assertEqual(route("Lol").kind, "chat")
