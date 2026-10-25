import asyncio
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest import mock

from ai.memory import ChatMemory
from ai.speech import SpeechError, Transcriber
from ai.vision import ChartReader, VisionError
from config.settings import load_settings
from data.calendar import CalendarClient, currencies_for, parse_events
from data.news import NewsClient, headline_sentiment
from db.chat import ChatRepo
from db.kv import KV
from services import formatter
from services.chat_service import ChatService
from services.discipline import DisciplineService
from services.intents import route, route_sticker
from services.media import MediaService
from tests.test_services import NOW, FakeAI, FakeAnalysis, Clock, env


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def feed(*items):
    return [{"title": t, "country": c, "date": iso(ts), "impact": i, "forecast": "1.0", "previous": "0.5"}
            for t, c, ts, i in items]


class CalendarTests(unittest.TestCase):
    def client(self, data, **kw):
        calls = []

        def get(url, params):
            calls.append(url)
            if isinstance(data, Exception):
                raise data
            return data

        db = env()[0]
        c = CalendarClient(KV(db), json_get=get, clock=Clock(), **kw)
        c.calls = calls
        return c

    def test_currencies(self):
        self.assertEqual(currencies_for("XAUUSD"), {"USD"})
        self.assertEqual(currencies_for("EURUSD"), {"EUR", "USD"})
        self.assertEqual(currencies_for("BTCUSD"), {"USD"})
        self.assertEqual(currencies_for("GBPJPY"), {"GBP", "JPY"})

    def test_parse_skips_bad_rows_and_holidays(self):
        data = feed(("NFP", "USD", NOW + 3600, "High")) + [{"title": "x"}, "junk", {"title": "H", "country": "USD",
                    "date": iso(NOW), "impact": "Holiday"}]
        ev = parse_events(data)
        self.assertEqual([e["title"] for e in ev], ["NFP"])
        self.assertEqual(ev[0]["impact"], "high")
        self.assertEqual(parse_events({"not": "a list"}), [])

    def test_upcoming_filters_currency_impact_and_window(self):
        c = self.client(feed(("NFP", "USD", NOW + 3600, "High"), ("ECB", "EUR", NOW + 7200, "High"),
                             ("PMI", "USD", NOW + 1800, "Medium"), ("Far", "USD", NOW + 90 * 3600, "High")))
        self.assertEqual([e["title"] for e in c.upcoming({"USD"}, 24)], ["NFP"])
        self.assertEqual([e["title"] for e in c.upcoming(None, 24)], ["NFP", "ECB"])
        self.assertEqual(len(c.upcoming({"USD"}, 24, min_impact="medium")), 2)

    def test_blackout_window(self):
        c = self.client(feed(("FOMC", "USD", NOW + 20 * 60, "High")))
        self.assertEqual(c.blackout("XAUUSD", NOW)["title"], "FOMC")           # 20 min pehle: andar
        self.assertIsNone(c.blackout("XAUUSD", NOW - 20 * 60))                  # 40 min pehle: bahar
        self.assertIsNotNone(c.blackout("XAUUSD", NOW + 20 * 60 + 600))         # 10 min baad: andar
        self.assertIsNone(c.blackout("XAUUSD", NOW + 20 * 60 + 1200))           # 20 min baad: bahar
        self.assertIsNone(c.blackout("EURGBP", NOW))                            # USD khabar, EUR/GBP par nahi

    def test_failsafe_and_caching(self):
        c = self.client(RuntimeError("down"))
        self.assertEqual(c.events(), [])
        self.assertIn("down", c.last_error)
        c.events()
        self.assertEqual(len(c.calls), 1)          # fail par bhi ghante bhar dobara nahi pukara
        ok = self.client(feed(("NFP", "USD", NOW + 60, "High")))
        ok.events(); ok.events()
        self.assertEqual(len(ok.calls), 1)
        self.assertEqual(self.client(feed(("NFP", "USD", NOW + 60, "High")), enabled=False).events(), [])

    def test_manual_events_survive_feed_failure(self):
        c = self.client(RuntimeError("down"))
        c.add_manual(NOW + 600, "usd", "FOMC rate decision")
        self.assertEqual(c.events()[0]["title"], "FOMC rate decision")
        self.assertTrue(c.events()[0]["manual"])
        self.assertIsNotNone(c.blackout("XAUUSD", NOW))
        c.clear_manual()
        self.assertEqual(c.events(), [])

    def test_context_text(self):
        c = self.client(feed(("NFP", "USD", NOW + 3600, "High")))
        self.assertIn("NFP", c.context("XAUUSD"))
        self.assertEqual(c.context("EURGBP"), "")

    def test_format_calendar_events(self):
        self.assertIn("nahi mili", formatter.format_calendar_events([], NOW))
        ev = parse_events(feed(("NFP", "USD", NOW + 3600, "High")))
        text = formatter.format_calendar_events(ev, NOW)
        self.assertIn("NFP", text)
        self.assertIn("1h 0m mein", text)


class SentimentTests(unittest.TestCase):
    def test_sentiment(self):
        self.assertEqual(headline_sentiment(["Bitcoin surges to record", "ETH rallies"])[0], "bullish")
        self.assertEqual(headline_sentiment(["Exchange hacked", "Market crash fears"])[0], "bearish")
        self.assertEqual(headline_sentiment(["Fed meets Tuesday"])[0], "neutral")
        self.assertEqual(headline_sentiment([]), ("neutral", 0))

    def test_context_has_sentiment_only_with_headlines(self):
        xml = "<rss><channel><item><title>Bitcoin surges to record high</title></item></channel></rss>"
        n = NewsClient(text_get=lambda u: xml, json_get=lambda u, p: {"data": [{"value": "70", "value_classification": "Greed"}]},
                       feeds={"crypto": ["u"]})
        self.assertIn("sentiment", n.context("crypto"))
        self.assertEqual(NewsClient(text_get=lambda u: "<rss/>", feeds={"forex": ["u"]}).context("forex"), "")


class DisciplineTests(unittest.TestCase):
    def build(self, **kw):
        db, clock, users, approval, repo, svc = env()
        return DisciplineService(repo, clock, **kw), repo, clock

    def add(self, repo, clock, uid, status, r, closed_ago_min, created_ago_min=None):
        sid = repo.create(dict(symbol="BTCUSD", mode="scalp", side="buy", entry_type="LIMIT", entry=100, sl=99, tp1=101.5,
                               tp2=102.5, status="PENDING",
                               created_ts=int(clock() - (created_ago_min or closed_ago_min + 30) * 60)))
        repo.update(sid, status=status, result_r=r, closed_ts=int(clock() - closed_ago_min * 60))
        repo.add_delivery(sid, uid)
        return sid

    def test_clean_record_has_no_warnings(self):
        d, repo, clock = self.build()
        self.add(repo, clock, 2, "TP2", 2.0, 300)
        s = d.snapshot(2)
        self.assertEqual((s["loss_streak"], s["r_24h"]), (0, 2.0))
        self.assertEqual(d.warnings(2), [])
        self.assertIn("koi tanbeeh nahi", d.format_summary(2))

    def test_loss_streak_counts_from_newest_and_breaks_on_win(self):
        d, repo, clock = self.build()
        self.add(repo, clock, 2, "TP2", 2.0, 600)
        for i, ago in enumerate((300, 200, 100)):
            self.add(repo, clock, 2, "SL", -1.0, ago)
        s = d.snapshot(2)
        self.assertEqual(s["loss_streak"], 3)
        self.assertTrue(any("Lagatar 3 loss" in w for w in d.warnings(2)))

    def test_breakeven_breaks_the_streak(self):
        d, repo, clock = self.build()
        self.add(repo, clock, 2, "SL", -1.0, 600)
        self.add(repo, clock, 2, "BE", 0.0, 300)
        self.add(repo, clock, 2, "SL", -1.0, 100)
        self.assertEqual(d.snapshot(2)["loss_streak"], 1)

    def test_daily_limit_and_revenge_window(self):
        d, repo, clock = self.build(daily_loss_limit_r=2.0)
        self.add(repo, clock, 2, "SL", -1.0, 120)
        self.add(repo, clock, 2, "SL", -1.0, 10)
        w = " ".join(d.warnings(2))
        self.assertIn("limit", w)
        d2, repo2, clock2 = self.build()
        self.add(repo2, clock2, 2, "SL", -1.0, 10)
        self.assertTrue(any("revenge" in w for w in d2.warnings(2)))

    def test_overtrading_and_old_signals_ignored(self):
        d, repo, clock = self.build(max_signals_per_day=3)
        for ago in (50, 100, 150):
            self.add(repo, clock, 2, "TP2", 1.0, ago)
        self.assertTrue(any("24 ghante mein 3 signals" in w for w in d.warnings(2)))
        old = self.build()
        self.add(old[1], old[2], 2, "SL", -1.0, 3000)
        self.assertEqual(old[0].snapshot(2)["r_24h"], 0)

    def test_users_are_separate_and_cancelled_are_not_losses(self):
        d, repo, clock = self.build()
        self.add(repo, clock, 3, "SL", -1.0, 100)
        self.add(repo, clock, 2, "CANCELLED", None, 100)
        self.assertEqual(d.snapshot(2)["loss_streak"], 0)
        self.assertEqual(d.snapshot(3)["loss_streak"], 1)

    def test_context_text_reaches_ai(self):
        db, clock, users, approval, repo, svc = env()
        d = DisciplineService(repo, clock)
        ai = FakeAI("ok")
        chat = ChatService(ai, ChatMemory(ChatRepo(db), ai, clock=clock), FakeAnalysis(None), None, repo, discipline=d)
        chat.reply_blocking(2, "hello")
        ctx = [m["content"] for m in ai.calls[0] if m["role"] == "system"][1]
        self.assertIn("Discipline (database se)", ctx)


class IntentTests(unittest.TestCase):
    def test_news_and_discipline_routes(self):
        self.assertEqual(route("news batao").kind, "news")
        self.assertEqual(route("btc news").symbols, ("BTCUSD",))
        self.assertEqual(route("nfp kab hai").kind, "news")
        self.assertEqual(route("mera discipline kaisa hai").kind, "discipline")
        self.assertEqual(route("kya main overtrade kar raha hun").kind, "discipline")

    def test_long_news_question_goes_to_ai_and_signal_wins(self):
        self.assertEqual(route("gold news ke hisab se kya hoga aaj ka din mein").kind, "chat")
        self.assertEqual(route("news ka signal do").kind, "signal")

    def test_emotion_still_wins(self):
        self.assertEqual(route("bohat loss ho gaya news dekhni hai").kind, "emotion")

    def test_sticker_moods(self):
        self.assertEqual(route_sticker("😭").kind, "emotion")
        self.assertEqual(route_sticker("🔥").kind, "chat")
        self.assertIn("overconfidence", route_sticker("🎉").hint)
        self.assertIsNone(route_sticker("🐱"))
        self.assertIsNone(route_sticker(None))


class SpeechVisionTests(unittest.TestCase):
    def test_transcriber_request_and_errors(self):
        seen = {}

        def post(url, headers, files, data):
            seen.update(url=url, headers=headers, files=files, data=data)
            return {"text": "  gold ka signal do "}

        t = Transcriber("k", "https://x.test/v1/", "m", http_post=post)
        self.assertEqual(t.transcribe(b"abc"), "gold ka signal do")
        self.assertEqual(seen["url"], "https://x.test/v1/audio/transcriptions")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer k")
        self.assertEqual(seen["data"]["model"], "m")
        with self.assertRaises(SpeechError):
            Transcriber("").transcribe(b"abc")
        with self.assertRaises(SpeechError):
            t.transcribe(b"")
        with self.assertRaises(SpeechError):
            Transcriber("k", http_post=lambda *a, **k: {"oops": 1}).transcribe(b"abc")
        self.assertFalse(Transcriber("").enabled)

    def test_chart_reader_request_and_limits(self):
        seen = {}

        def post(url, headers, payload):
            seen.update(url=url, headers=headers, payload=payload)
            return {"content": [{"type": "text", "text": "Uptrend, resistance upar"}]}

        r = ChartReader("key", http_post=post)
        self.assertEqual(r.read(b"img", "image/png", "kya lagta hai"), "Uptrend, resistance upar")
        self.assertEqual(seen["headers"]["x-api-key"], "key")
        self.assertEqual(seen["payload"]["model"], "claude-haiku-5-5")
        block = seen["payload"]["messages"][0]["content"]
        self.assertEqual(block[0]["source"]["media_type"], "image/png")
        self.assertIn("kya lagta hai", block[1]["text"])
        self.assertIn("hukm nahi", seen["payload"]["system"])        # image ke andar ki hidayat par amal nahi
        for bad in ((b"", "image/jpeg"), (b"x" * 4_000_000, "image/jpeg"), (b"x", "application/pdf")):
            with self.assertRaises(VisionError):
                r.read(*bad)
        with self.assertRaises(VisionError):
            ChartReader("").read(b"x")
        with self.assertRaises(VisionError):
            ChartReader("k", http_post=lambda *a: {"content": []}).read(b"x")


class MediaServiceTests(unittest.TestCase):
    def test_daily_limit_per_user_and_resets_next_day(self):
        clock = Clock(86400 * 10)
        m = MediaService(None, None, None, daily_limit=2, clock=clock)
        self.assertTrue(m.allow(2) and m.allow(2))
        self.assertFalse(m.allow(2))
        self.assertTrue(m.allow(3))
        clock.t += 86400
        self.assertTrue(m.allow(2))

    def test_image_reply_passes_observations_as_context_not_memory(self):
        db, clock, users, approval, repo, svc = env()
        ai = FakeAI("Jawab")
        mem = ChatMemory(ChatRepo(db), ai, clock=clock)
        chat = ChatService(ai, mem, FakeAnalysis(None), None, repo)
        reader = ChartReader("k", http_post=lambda *a: {"content": [{"type": "text", "text": "SECRET-OBSERVATION"}]})
        m = MediaService(None, reader, chat)
        out = asyncio.run(m.image_reply(2, b"img", "image/jpeg", "yeh chart kaisa hai"))
        self.assertEqual(out, "Jawab")
        ctx = [x["content"] for x in ai.calls[0] if x["role"] == "system"][1]
        self.assertIn("SECRET-OBSERVATION", ctx)
        self.assertIn("andaza", ctx)
        stored = " ".join(x["content"] for x in mem.history_messages(2))
        self.assertIn("[chart image] yeh chart kaisa hai", stored)
        self.assertNotIn("SECRET-OBSERVATION", stored)

    def test_image_reply_vision_failure_is_friendly(self):
        reader = ChartReader("k", http_post=lambda *a: (_ for _ in ()).throw(VisionError("HTTP 500")))
        m = MediaService(None, reader, None)
        self.assertIn("parh nahi saka", asyncio.run(m.image_reply(2, b"img", "image/jpeg")))


# ---------- Telegram handlers (telegram library ke baghair, nakli modules ke saath) ----------

def _stub_telegram():
    tg = types.ModuleType("telegram")
    for n in ("InlineKeyboardButton", "InlineKeyboardMarkup", "Update"):
        setattr(tg, n, type(n, (), {"__init__": lambda self, *a, **k: None}))
    const = types.ModuleType("telegram.constants")
    const.ChatAction = types.SimpleNamespace(TYPING="typing")
    ext = types.ModuleType("telegram.ext")
    ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    tg.constants, tg.ext = const, ext
    return {"telegram": tg, "telegram.constants": const, "telegram.ext": ext}


class FakeFile:
    def __init__(self, data=b"bytes", size=1000, duration=5, mime=None):
        self.data, self.file_size, self.duration, self.mime_type = data, size, duration, mime

    async def get_file(self):
        outer = self

        class F:
            async def download_as_bytearray(self):
                return bytearray(outer.data)
        return F()


class FakeMessage:
    def __init__(self, **kw):
        self.replies = []
        self.text = kw.get("text")
        self.voice, self.audio, self.sticker, self.document = kw.get("voice"), None, kw.get("sticker"), kw.get("document")
        self.photo, self.caption = kw.get("photo"), kw.get("caption")

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, msg, uid=2):
        self.message = msg
        self.effective_user = types.SimpleNamespace(id=uid)
        self.effective_message = msg
        self.effective_chat = types.SimpleNamespace(send_action=self._noop)

    async def _noop(self, *a, **k):
        pass


class HandlerTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(sys.modules, _stub_telegram())
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("bot.handlers", None)
        self.addCleanup(lambda: sys.modules.pop("bot.handlers", None))
        import bot.handlers as h
        self.h = h
        db, clock, users, approval, repo, svc = env()
        self.ai = FakeAI("AI jawab")
        mem = ChatMemory(ChatRepo(db), self.ai, clock=clock)
        disc = DisciplineService(repo, clock)
        self.cal = CalendarClient(KV(db), json_get=lambda u, p: feed(("NFP", "USD", NOW + 600, "High")), clock=clock)
        self.chat = ChatService(self.ai, mem, FakeAnalysis(None), None, repo, calendar=self.cal, discipline=disc)
        self.settings = load_settings({"TELEGRAM_BOT_TOKEN": "x", "OWNER_ID": "1"})
        self.c = types.SimpleNamespace(
            approval=approval, chat=self.chat, signal_repo=repo, settings=self.settings, calendar=self.cal,
            discipline=disc, news=None, market=types.SimpleNamespace(clock=clock), media=None, speech=None, vision=None,
            journal=None)
        self.ctx = types.SimpleNamespace(application=types.SimpleNamespace(bot_data={"c": self.c}), args=[])

    def run_h(self, fn, msg, uid=2):
        asyncio.run(fn(FakeUpdate(msg, uid), self.ctx))
        return msg.replies

    def test_unapproved_user_is_blocked_everywhere(self):
        for fn, msg in ((self.h.sticker_message, FakeMessage(sticker=types.SimpleNamespace(emoji="😭"))),
                        (self.h.voice_message, FakeMessage(voice=FakeFile())),
                        (self.h.photo_message, FakeMessage(photo=[FakeFile()]))):
            self.assertIn("approved nahi", self.run_h(fn, msg, uid=99)[0])

    def test_sticker_ai_is_owner_only(self):
        # user (uid=2) ke liye AI nahi: khamosh
        self.assertEqual(self.run_h(self.h.sticker_message, FakeMessage(sticker=types.SimpleNamespace(emoji="😭")), uid=2), [])

    def test_sticker_sad_gets_ai_with_hint_unknown_is_silent(self):
        r = self.run_h(self.h.sticker_message, FakeMessage(sticker=types.SimpleNamespace(emoji="😭")), uid=1)
        self.assertEqual(r, ["AI jawab"])
        self.assertIn("Pehle narmi", " ".join(m["content"] for m in self.ai.calls[0] if m["role"] == "system"))
        self.assertEqual(self.run_h(self.h.sticker_message, FakeMessage(sticker=types.SimpleNamespace(emoji="🐱")), uid=1), [])
        self.assertEqual(self.run_h(self.h.sticker_message, FakeMessage(sticker=types.SimpleNamespace(emoji=None)), uid=1), [])

    def test_voice_disabled_toolong_and_success(self):
        self.assertIn("band hai", self.run_h(self.h.voice_message, FakeMessage(voice=FakeFile()))[0])
        self.c.speech = Transcriber("k", http_post=lambda *a, **k: {"text": "news batao"})
        self.c.vision = ChartReader("")
        self.c.media = MediaService(self.c.speech, self.c.vision, self.chat)
        self.assertIn("second se chhoti", self.run_h(self.h.voice_message, FakeMessage(voice=FakeFile(duration=500)))[0])
        self.h._NOTICED.clear()
        r = self.run_h(self.h.voice_message, FakeMessage(voice=FakeFile(duration=5)))
        self.assertTrue(any("Maine suna: news batao" in x for x in r))
        self.assertTrue(any("NFP" in x for x in r))                 # "news batao" -> calendar jawab
        self.assertTrue(any("teesri party" in x for x in r))        # pehli baar privacy note

    def test_voice_transcription_error_is_friendly(self):
        def boom(*a, **k):
            raise SpeechError("HTTP 500")
        self.c.speech = Transcriber("k", http_post=boom)
        self.c.media = MediaService(self.c.speech, ChartReader(""), self.chat)
        r = self.run_h(self.h.voice_message, FakeMessage(voice=FakeFile()))
        self.assertTrue(any("samajh nahi aayi" in x for x in r))

    def test_voice_daily_limit(self):
        self.c.speech = Transcriber("k", http_post=lambda *a, **k: {"text": "hello"})
        self.c.media = MediaService(self.c.speech, ChartReader(""), self.chat, daily_limit=0)
        self.assertIn("hadd poori", self.run_h(self.h.voice_message, FakeMessage(voice=FakeFile()))[0])

    def test_photo_picks_largest_allowed_and_replies(self):
        self.c.vision = ChartReader("k", http_post=lambda *a: {"content": [{"type": "text", "text": "uptrend"}]})
        self.c.media = MediaService(Transcriber(""), self.c.vision, self.chat)
        photos = [FakeFile(size=1000), FakeFile(size=900_000), FakeFile(size=9_000_000)]
        r = self.run_h(self.h.photo_message, FakeMessage(photo=photos, caption="kaisa hai"))
        self.assertEqual(r[-1], "AI jawab")
        self.assertIn("uptrend", " ".join(m["content"] for m in self.ai.calls[0] if m["role"] == "system"))
        self.assertIn("bahut bari", self.run_h(self.h.photo_message, FakeMessage(photo=[FakeFile(size=9_000_000)]))[0])

    def test_photo_without_key_and_bad_document(self):
        self.assertIn("ANTHROPIC_API_KEY", self.run_h(self.h.photo_message, FakeMessage(photo=[FakeFile()]))[0])
        doc = FakeFile(mime="application/pdf")
        self.assertIn("JPG", self.run_h(self.h.image_document_message, FakeMessage(document=doc))[0])

    def test_image_document_flow(self):
        self.c.vision = ChartReader("k", http_post=lambda *a: {"content": [{"type": "text", "text": "range"}]})
        self.c.media = MediaService(Transcriber(""), self.c.vision, self.chat)
        r = self.run_h(self.h.image_document_message, FakeMessage(document=FakeFile(mime="image/png", size=2000)))
        self.assertEqual(r[-1], "AI jawab")

    def test_news_and_discipline_via_text(self):
        r = self.run_h(self.h.chat_message, FakeMessage(text="news batao"))
        self.assertIn("NFP", r[0])
        r = self.run_h(self.h.chat_message, FakeMessage(text="mera discipline kaisa hai"))
        self.assertIn("discipline", r[0].lower())

    def test_event_command_owner_only_and_parsing(self):
        self.assertIn("sirf owner", self.run_h(self.h.event_cmd, FakeMessage(), uid=2)[0])
        self.ctx.args = ["add", "2026-01-05", "12:30", "usd", "FOMC", "rate", "decision"]
        r = self.run_h(self.h.event_cmd, FakeMessage(), uid=1)
        self.assertIn("✅", r[0])
        self.assertEqual(self.cal.manual()[0]["currency"], "USD")
        self.ctx.args = ["add", "bad-date", "12:30", "USD", "x"]
        self.assertIn("ghalat", self.run_h(self.h.event_cmd, FakeMessage(), uid=1)[0])
        self.ctx.args = ["list"]
        self.assertIn("FOMC", self.run_h(self.h.event_cmd, FakeMessage(), uid=1)[0])


if __name__ == "__main__":
    unittest.main()


class UserNoChatTests(HandlerTests):
    def test_user_free_text_gets_fixed_reply_not_ai(self):
        before = len(self.ai.calls)
        r = self.run_h(self.h.chat_message, FakeMessage(text="gold ka kya scene hai"), uid=2)
        self.assertIn("sirf signals aur updates", r[-1])
        self.assertEqual(len(self.ai.calls), before)

    def test_owner_free_text_still_uses_ai(self):
        r = self.run_h(self.h.chat_message, FakeMessage(text="gold ka kya scene hai"), uid=1)
        self.assertEqual(r[-1], "AI jawab")

    def test_user_forget_is_blocked(self):
        self.assertIn("sirf signals aur updates", self.run_h(self.h.forget_cmd, FakeMessage(), uid=2)[-1])
