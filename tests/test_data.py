import unittest

from data import budget as bm
from data.base import BudgetExhausted, DataError, closed_only, make_df
from data.market_data import MarketData
from data.news import NewsClient, parse_rss
from data.providers import KrakenClient, TwelveDataClient
from data.sessions import forex_open, in_session
from db.database import Database
from db.kv import KV


class Clock:
    def __init__(self, t=1_800_000_000):  # ~ Jan 2027
        self.t = t

    def __call__(self):
        return self.t


TD_OK = {"status": "ok", "values": [
    {"datetime": "2026-01-05 10:00:00", "open": "1.0", "high": "1.2", "low": "0.9", "close": "1.1"},
    {"datetime": "2026-01-05 10:05:00", "open": "1.1", "high": "1.3", "low": "1.0", "close": "1.2"},
]}
KRAKEN_OK = {"error": [], "result": {"XXBTZUSD": [
    [1767600000, "100", "102", "99", "101", "100.5", "5.0", 10],
    [1767600300, "101", "103", "100", "102", "101.5", "6.0", 11],
], "last": 1767600300}}


class ProviderTests(unittest.TestCase):
    def test_twelvedata_parse(self):
        calls = []
        c = TwelveDataClient("KEY", lambda url, p: calls.append(p) or TD_OK)
        df = c.fetch("XAU/USD", "5min", 100)
        self.assertEqual(len(df), 2)
        self.assertEqual(calls[0]["symbol"], "XAU/USD")
        self.assertEqual(df["volume"].iloc[0], 0.0)
        self.assertEqual(df.index[0].hour, 10)

    def test_twelvedata_error_and_missing_key(self):
        with self.assertRaises(DataError):
            TwelveDataClient("KEY", lambda u, p: {"status": "error", "message": "limit"}).fetch("X", "5min", 1)
        with self.assertRaises(DataError):
            TwelveDataClient("", lambda u, p: TD_OK).fetch("X", "5min", 1)

    def test_kraken_parse(self):
        df = KrakenClient(lambda u, p: KRAKEN_OK).fetch("XBTUSD", 5, 300)
        self.assertEqual(list(df["close"]), [101.0, 102.0])
        self.assertEqual(df["volume"].iloc[1], 6.0)

    def test_kraken_error(self):
        with self.assertRaises(DataError):
            KrakenClient(lambda u, p: {"error": ["EQuery:Unknown asset pair"], "result": {}}).fetch("X", 5)

    def test_make_df_empty(self):
        with self.assertRaises(DataError):
            make_df([])

    def test_closed_only_drops_forming_candle(self):
        df = make_df([(1000, 1, 1, 1, 1, 0), (1300, 1, 1, 1, 1, 0)])
        self.assertEqual(len(closed_only(df, 300, 1400)), 1)   # 1300 candle abhi band nahi
        self.assertEqual(len(closed_only(df, 300, 1700)), 2)


class BudgetTests(unittest.TestCase):
    def make(self, **kw):
        clock = Clock()
        return bm.CreditBudget(KV(Database(":memory:")), clock=clock, **kw), clock

    def test_per_minute_limit_and_reset(self):
        b, clock = self.make(per_minute=3, per_day=100, monitor_reserve=0)
        self.assertTrue(all(b.try_spend() for _ in range(3)))
        self.assertFalse(b.try_spend())
        clock.t += 61
        self.assertTrue(b.try_spend())

    def test_reserve_for_monitor(self):
        b, clock = self.make(per_minute=1000, per_day=10, monitor_reserve=4)
        self.assertTrue(all(b.try_spend() for _ in range(6)))
        self.assertFalse(b.try_spend())                       # normal ko reserve nahi milta
        self.assertTrue(all(b.try_spend(1, "monitor") for _ in range(4)))
        self.assertFalse(b.try_spend(1, "monitor"))
        self.assertEqual(b.remaining_today(), 0)

    def test_day_rollover(self):
        b, clock = self.make(per_minute=1000, per_day=2, monitor_reserve=0)
        b.try_spend(); b.try_spend()
        self.assertFalse(b.try_spend())
        clock.t += 86400
        self.assertTrue(b.try_spend())

    def test_persisted_in_db(self):
        db = Database(":memory:")
        clock = Clock()
        bm.CreditBudget(KV(db), 100, 100, 0, clock).try_spend(5)
        self.assertEqual(bm.CreditBudget(KV(db), 100, 100, 0, clock).used_today(), 5)


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.budget = bm.CreditBudget(KV(Database(":memory:")), 8, 800, 0, self.clock)
        self.td_calls = 0
        now = self.clock.t - self.clock.t % 300

        def td_fetch(code, interval, size):
            self.td_calls += 1
            return make_df([(now - 900, 1, 2, 0.5, 1.5, 0), (now - 600, 1, 2, 0.5, 1.5, 0),
                            (now - 300, 1, 2, 0.5, 1.5, 0), (now, 1, 2, 0.5, 1.5, 0)])

        class TD:  # noqa
            fetch = staticmethod(td_fetch)

        class KR:
            @staticmethod
            def fetch(code, interval, size):
                return make_df([(self.clock.t - 600, 1, 2, 0.5, 1.5, 1)])

        self.md = MarketData(TD, KR, self.budget, self.clock)

    def test_cache_saves_credits_and_drops_forming_candle(self):
        df = self.md.get_candles("XAUUSD", "scalp")
        self.assertEqual(len(df), 3)          # aakhri adhoori candle hata di
        self.md.get_candles("XAUUSD", "scalp")
        self.assertEqual(self.td_calls, 1)
        self.assertEqual(self.budget.used_today(), 1)

    def test_crypto_does_not_use_credits(self):
        self.md.get_candles("BTCUSD", "scalp")
        self.assertEqual(self.budget.used_today(), 0)

    def test_budget_exhausted(self):
        b = bm.CreditBudget(KV(Database(":memory:")), 0, 800, 0, self.clock)
        md = MarketData(self.md.td, self.md.kraken, b, self.clock)
        with self.assertRaises(BudgetExhausted):
            md.get_candles("XAUUSD", "scalp")

    def test_unknown_symbol(self):
        with self.assertRaises(DataError):
            self.md.get_candles("FOO", "scalp")


RSS = """<rss><channel><item><title>Gold rallies</title></item><item><title> Fed holds </title></item></channel></rss>"""


class NewsTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_rss(RSS), ["Gold rallies", "Fed holds"])

    def test_context_and_failsafe(self):
        n = NewsClient(text_get=lambda u: RSS, json_get=lambda u, p: {"data": [{"value": "25", "value_classification": "Extreme Fear"}]},
                       feeds={"crypto": ["x"], "forex": ["y"]})
        ctx = n.context("crypto")
        self.assertIn("Gold rallies", ctx)
        self.assertIn("Extreme Fear", ctx)

        def boom(u):
            raise RuntimeError("down")

        bad = NewsClient(text_get=boom, json_get=lambda u, p: (_ for _ in ()).throw(RuntimeError("x")),
                         feeds={"crypto": ["x"]})
        self.assertEqual(bad.context("crypto"), "")


class SessionTests(unittest.TestCase):
    def test_forex_open_hours(self):
        # 2026-01-05 Monday 12:00 UTC
        mon = 1767614400
        self.assertTrue(forex_open(mon))
        sat = mon + 5 * 86400
        self.assertFalse(forex_open(sat))
        fri_night = mon + 4 * 86400 + 11 * 3600          # Friday 23:00
        self.assertFalse(forex_open(fri_night))
        sun_late = mon + 6 * 86400 + 11 * 3600           # Sunday 23:00
        self.assertTrue(forex_open(sun_late))

    def test_in_session(self):
        t = 1767614400  # 12:00 UTC
        self.assertTrue(in_session(t, "07-20"))
        self.assertFalse(in_session(t, "13-20"))
        self.assertTrue(in_session(t, "22-14"))   # raat ke paar wali window


if __name__ == "__main__":
    unittest.main()


class SymbolTests(unittest.TestCase):
    def test_resolve_typos_and_aliases(self):
        from config.markets import find_symbols_in_text, resolve_symbol
        for word, want in [("Xausd", "XAUUSD"), ("xau/usd", "XAUUSD"), ("gold", "XAUUSD"), ("XAUSD", "XAUUSD"),
                           ("EURUSDD", "EURUSD"), ("btc", "BTCUSD"), ("bitcoin", "BTCUSD"), ("sol", "SOLUSD")]:
            self.assertEqual(resolve_symbol(word), want, word)
        for word in ("signal", "hello", "trading", "users", "setup", "", None):
            self.assertIsNone(resolve_symbol(word), word)
        self.assertEqual(find_symbols_in_text("Xausd ka signal do"), ["XAUUSD"])
        self.assertEqual(find_symbols_in_text("Koi signal do"), [])
        self.assertEqual(find_symbols_in_text("btc aur eth ka scene"), ["BTCUSD", "ETHUSD"])
