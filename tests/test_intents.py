import unittest

from db.chat import ChatRepo
from services.chat_service import ChatService
from ai.memory import ChatMemory
from services.intents import EMOTION_HINT, classify, route
from tests.test_services import FakeAI, FakeAnalysis, env


class RouteTests(unittest.TestCase):
    def kinds(self, cases, is_owner=False):
        for text, want in cases.items():
            self.assertEqual(route(text, is_owner).kind, want, text)

    def test_stats_questions_get_database_answer(self):
        self.kinds({
            "Total status batao": "stats",
            "mera record batao": "stats",
            "kitne win aur loss hue": "stats",
            "win rate kya hai": "stats",
            "performance kaisi hai": "stats",
            "hisaab batao": "stats",
            "total kitne signals aaye": "stats",
        })

    def test_market_question_with_symbol_is_not_stats(self):
        self.assertEqual(route("btc ka record high kab tha").kind, "chat")

    def test_status_and_signal_unchanged(self):
        self.kinds({
            "Koi signal hai": "signal",
            "Xausd ka signal do": "signal",
            "gold signal chahiye intraday": "signal",
            "Tp hit howa": "status",
            "signal ka status batao": "status",
            "jo signal diya wo cancel kyun hua": "status",
            "sl hit hua kya": "status",
        })

    def test_signal_symbol_and_mode(self):
        i = route("gold signal chahiye intraday")
        self.assertEqual((i.kind, i.symbols, i.mode), ("signal", ("XAUUSD",), "intraday"))
        i = route("koi signal do")
        self.assertEqual((i.symbols, i.mode), ((), "scalp"))

    def test_emotion_gets_hint(self):
        for text in ("bohat loss ho gaya yaar", "main bohat pareshan hun", "😭", "loss recover karna hai"):
            i = route(text)
            self.assertEqual(i.kind, "emotion", text)
            self.assertEqual(i.hint, EMOTION_HINT)

    def test_plain_chat_has_no_hint(self):
        for text in ("gold ka kya scene hai", "hello", "", "RSI kya hota hai"):
            i = route(text)
            self.assertEqual((i.kind, i.hint), ("chat", ""), text)

    def test_help_only_for_short_messages(self):
        self.kinds({"help": "help", "kaise use karun": "help", "madad chahiye": "help"})
        self.assertEqual(route("help chahiye ye trade samjhao aur batao kya karun abhi").kind, "chat")

    def test_pending_only_for_owner(self):
        self.assertEqual(route("koi naya user aya?", is_owner=True).kind, "pending")
        self.assertEqual(route("koi naya user aya?", is_owner=False).kind, "chat")

    def test_strong_emotion_beats_signal_request(self):
        i = route("signal do, loss recover karna hai")
        self.assertEqual((i.kind, i.hint), ("emotion", EMOTION_HINT))

    def test_emoji_alone_does_not_override_status_question(self):
        self.assertEqual(route("sl hit hua kya 😭").kind, "status")
        self.assertEqual(route("😭").kind, "emotion")

    def test_classify_wrapper(self):
        self.assertEqual(classify("Tp hit howa"), "status")
        self.assertEqual(classify(""), "chat")


class ChatHintTests(unittest.TestCase):
    def build(self):
        db, clock, users, approval, repo, svc = env()
        ai = FakeAI("Jawab")
        mem = ChatMemory(ChatRepo(db), ai, clock=clock)
        return ai, ChatService(ai, mem, FakeAnalysis(None), None, repo)

    def test_hint_reaches_ai_as_system_message(self):
        ai, chat = self.build()
        chat.reply_blocking(2, "bohat loss ho gaya", hint=EMOTION_HINT)
        systems = [m["content"] for m in ai.calls[0] if m["role"] == "system"]
        self.assertEqual(len(systems), 3)               # prompt + context + hint
        self.assertEqual(systems[-1], EMOTION_HINT)

    def test_no_hint_no_extra_message(self):
        ai, chat = self.build()
        chat.reply_blocking(2, "hello")
        self.assertEqual(sum(1 for m in ai.calls[0] if m["role"] == "system"), 2)


if __name__ == "__main__":
    unittest.main()
