"""Bot ke aam sawalon ke pakke jawab (AI se nahi). Trade ka haal database se, aur bot ke usool yahan se.

Har entry: (lafz ke set, jawab). Jumle mein kam az kam ek 'group' ke lafz hon to match. Group ke andar
koi bhi lafz kaafi hai. Pehla match jeetta hai, is liye zyada khaas sawal oopar rakhe gaye hain.
"""
import re
from typing import List, Optional, Sequence, Set, Tuple

# (groups, jawab). Har group: lafzon ka set; group mein se ek lafz mil jaye to group match.
# Sab groups match hon tab entry match hoti hai.
_RAW: List[Tuple[List[Set[str]], str]] = [
    ([{"signal"}, {"kya", "kia", "kyun", "kya", "kaise", "kese", "matlab"}],
     "Signal ek tayyar trade plan hai: entry, stop-loss (SL) aur do take-profit (TP1, TP2). Bot ye score aur "
     "technical analysis (trend, levels, patterns, indicators) ke base par banata hai. Ye financial advice nahi, "
     "aur profit ki guarantee nahi."),
    ([{"limit", "pending"}, {"kya", "kia", "matlab", "kaise"}],
     "LIMIT entry ka matlab hai: price aap ki entry tak wapas aaye tab trade khule. Bot pullback par entry deta hai, "
     "is liye ye abhi fill nahi hota. Agar price pehle hi TP tak chali jaye to setup chhod diya jata hai."),
    ([{"sl", "stoploss", "stop"}, {"kya", "kia", "matlab", "kyun", "kitna", "kitni", "kaise", "rakhna", "rakhein"}],
     "Stop-loss (SL) woh level hai jahan trade khud band ho jata hai taake nuqsan limit mein rahe. Har signal ke "
     "saath SL hota hai. SL ko door kar ke ya hata ke trade na lein. Lot size chhota rakhein."),
    ([{"tp", "tp1", "tp2", "target", "take"}, {"kya", "kia", "matlab", "kab", "kaise"}],
     "TP1 pehla target hai (lagbhag 1.5R), TP2 doosra (lagbhag 2.5R). TP1 par aksar SL ko entry (breakeven) par le "
     "jaate hain. R ka matlab hai aap ka risk, jaise SL 10 pips ho to 1R = 10 pips."),
    ([{"scalp", "scalping"}, {"kya", "kia", "matlab", "kaise", "kab", "kitna", "time", "timeframe"}],
     "Scalp mode 5 minute ke candles par chalta hai aur chhote, tez trades dhoondta hai. Forex ke liye scan har "
     "{forex} minute par session ke andar hota hai, crypto ke liye har {crypto} minute par."),
    ([{"intraday"}, {"kya", "kia", "matlab", "kaise", "kab", "time", "timeframe"}],
     "Intraday mode 15 minute ke candles par chalta hai, aur 1 ghanta aur 4 ghante ka trend (15m ko resample karke) "
     "dekhta hai. Ye scalp se dheere, lekin zyada sochay samjhay trades deta hai."),
    ([{"pairs", "pair", "symbols", "coins", "watchlist", "kaun", "konse", "kaunse", "kitne", "list"}],
     "Bot ke pairs ye hain: {pairs}."),
    ([{"forex", "gold", "xauusd"}, {"band", "closed", "khula", "khulta", "nahi", "kab"}],
     "Forex aur gold ka market hafte mein sirf kuch ghanton ke liye khula hota hai (weekend par band). Session ke "
     "bahar (UTC {session}) forex par signal nahi bante."),
    ([{"signal", "signals"}, {"nahi", "aaya", "aya", "kyun", "kyon", "koi"}],
     "Signal tabhi banta hai jab score kaafi ho, risk-reward theek ho aur market khula ho. Bina saaf setup ke bot "
     "chup rehta hai, aur ye behtar hai. Chahein to /signal ya 'XAUUSD ka signal do' likhein."),
    ([{"guarantee", "pakka", "sure", "profit", "kamayi", "kamaun", "paisa", "risk"}],
     "Kisi signal ka profit pakka nahi hota. Ye financial advice nahi hai. Har trade par SL lagayein, lot size chhota "
     "rakhein, aur jitna paisa khona afford kar sakte hain utna hi lagayein."),
    ([{"approve", "approval", "access", "request", "kaise"}],
     "Access ke liye /start bhejein. Owner ki approval ke baad aap signals aur updates lena shuru kar sakte hain."),
    ([{"command", "commands", "help", "madad", "guide"}],
     "Commands: /signal <pair>, /analyze <pair> [scalp|intraday], /signals (open trades), /history, /stats, /alert, "
     "/alerts, /watchlist, /news, /discipline, /help. Seedha likh kar bhi poochh sakte hain, jaise 'btc analyze karo'."),
]


def _words(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def answer(text: str, pairs: Sequence[str] = (), session: str = "07-20",
           forex_min: int = 10, crypto_min: int = 5) -> Optional[str]:
    """Pakka jawab, ya None (taake baat AI ya fallback tak jaye)."""
    words = _words(text)
    if not words:
        return None
    for groups, reply in _RAW:
        if all(words & g for g in groups):
            return reply.format(
                pairs=", ".join(pairs) if pairs else "watchlist mein",
                session=session, forex=forex_min, crypto=crypto_min,
            )
    return None
