"""Seedhe text ka matlab: user kya chahta hai, aur bot ko kya karna hai.

Jahan database ka asli jawab mumkin hai (signals ka haal, apna record) wahan AI se nahi, database se jawab diya jata
hai, taake AI andaza na lagaye. Baqi baat AI se hoti hai, aur zaroorat par usay ek hint milta hai.
"""
import re
from dataclasses import dataclass
from typing import Tuple

from config.markets import find_symbols_in_text

STATUS_WORDS = {
    "hit", "tp", "tp1", "tp2", "sl", "stop", "status", "hua", "hui", "hoa", "howa", "result", "update",
    "kahan", "profit", "loss", "pending", "cancel", "cancelled", "expire", "expired",
}
# "jo tumne signal diya" jaisi baatein purane signal ke baare mein hoti hain
REFERENCE_WORDS = {"diya", "dea", "dia", "tumne", "aapne", "jo", "wala", "wale", "wali", "pehle", "purana"}

# Apna hisaab / record
STATS_WORDS = {"stats", "statistics", "record", "performance", "hisab", "hisaab", "winrate", "pnl", "report"}
STATS_WITH_TOTAL = {"status", "signals", "signal", "result", "results", "profit", "loss", "win", "wins", "trades"}
STATS_PHRASES = ("win rate", "kitne win", "kitni win", "kitne loss", "kitne signal", "kitni signal",
                 "kitne trade", "kitni trade", "kul signal", "my record", "mera record", "meri performance")

# Jazbati baat (loss ke baad pareshani waghera)
EMOTION_WORDS = {
    "pareshan", "pareshaan", "udaas", "udas", "ghussa", "gussa", "tension", "depressed", "depression", "rona",
    "barbad", "barbaad", "afsos", "dukh", "panic", "revenge", "badla", "recover", "recovery", "frustrated",
    "hopeless",
}
EMOTION_PHRASES = ("loss pe loss", "sab loss", "bohat loss", "bahut loss", "lagatar loss", "paisa doob",
                   "paise doob", "blow up", "account blow", "margin call", "sab khatam")
EMOTION_EMOJIS = "😭😢😡🤬😤😞😔😩😫💔"

HELP_WORDS = {"help", "madad", "guide", "commands", "command"}
PENDING_WORDS = ("aya", "aaya", "new", "naya", "pending", "request")

EMOTION_HINT = (
    "User abhi pareshan ya ghusse mein lag raha hai (shayad loss ki wajah se). Pehle narmi se tasalli do. Phir chhoti "
    "si yaad-dehani: ek trade mein risk chhota rakhein, loss wapas lene ki jaldi mein naya trade (revenge trade) na "
    "lein, aur zaroorat ho to thora break lein. Naya signal lene par zor mat do. Jawab chhota rakhein."
)


@dataclass(frozen=True)
class Intent:
    kind: str                     # pending | stats | status | signal | emotion | help | chat
    symbols: Tuple[str, ...] = ()
    mode: str = "scalp"
    hint: str = ""                # AI ko extra hidayat (sirf chat/emotion ke liye)


def _is_stats(low: str, words: set, symbols) -> bool:
    if symbols:                   # "btc ka record high" market ka sawal hai, apna record nahi
        return False
    if any(p in low for p in STATS_PHRASES):
        return True
    if words & STATS_WORDS:
        return True
    return "total" in words and bool(words & STATS_WITH_TOTAL)


def _strong_emotion(low: str, words: set) -> bool:
    """Saaf jazbati lafz/jumle. Ye signal/status ke sawal se bhi upar hain (pehle insaan, phir signal)."""
    return bool(words & EMOTION_WORDS) or any(p in low for p in EMOTION_PHRASES)


def _is_help(low: str, words: set) -> bool:
    if len(words) > 6:
        return False
    return bool(words & HELP_WORDS) or any(p in low for p in ("kaise use", "kya kya", "kya kar sakte"))


def route(text: str, is_owner: bool = False) -> Intent:
    raw = text or ""
    low = raw.lower()
    words = set(re.findall(r"[a-z0-9]+", low))
    symbols = tuple(find_symbols_in_text(raw, limit=2))
    mode = "intraday" if ("intraday" in low or "intra day" in low) else "scalp"

    if is_owner and "user" in low and any(w in low for w in PENDING_WORDS):
        return Intent("pending")
    if _is_stats(low, words, symbols):
        return Intent("stats")
    if _strong_emotion(low, words):
        return Intent("emotion", symbols, mode, EMOTION_HINT)
    if any(k in low for k in ("signal", "sigal", "singal")):
        if words & STATUS_WORDS or words & REFERENCE_WORDS:
            return Intent("status")
        return Intent("signal", symbols, mode)
    if words & {"tp", "tp1", "tp2", "sl", "hit"}:
        return Intent("status")
    if any(e in raw for e in EMOTION_EMOJIS):        # sirf emoji: baqi koi matlab na nikle tab
        return Intent("emotion", symbols, mode, EMOTION_HINT)
    if _is_help(low, words):
        return Intent("help")
    return Intent("chat", symbols, mode)


def classify(text: str) -> str:
    """Sirf kisam (owner ke khaas 'pending' sawal ke baghair)."""
    return route(text).kind
