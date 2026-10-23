"""News headlines (RSS) aur Fear & Greed. Sab fail-safe: kuch na chale to bot chalta rehta hai."""
import time
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from data.base import DataError

DEFAULT_FEEDS = {
    "crypto": ["https://www.coindesk.com/arc/outboundfeeds/rss/",
               "https://cointelegraph.com/rss"],
    "forex": ["https://www.fxstreet.com/rss/news"],
}
FNG_URL = "https://api.alternative.me/fng/"


def _text_get(url: str) -> str:
    import requests

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 trading-bot"})
    if resp.status_code >= 400:
        raise DataError(f"HTTP {resp.status_code}")
    return resp.text


def parse_rss(xml_text: str, limit: int = 8) -> List[str]:
    root = ET.fromstring(xml_text)
    titles = []
    for item in root.iter("item"):
        t = item.findtext("title")
        if t and t.strip():
            titles.append(t.strip())
        if len(titles) >= limit:
            break
    return titles


BULLISH_WORDS = {"surge", "surges", "rally", "rallies", "soar", "soars", "jump", "jumps", "gain", "gains", "rise", "rises",
                 "record", "bullish", "breakout", "upgrade", "approval", "approved", "adoption", "inflows", "recovers"}
BEARISH_WORDS = {"plunge", "plunges", "crash", "crashes", "slump", "slumps", "drop", "drops", "fall", "falls", "fell",
                 "bearish", "selloff", "sell-off", "ban", "hack", "hacked", "lawsuit", "outflows", "fear", "recession",
                 "tumble", "tumbles", "decline", "declines"}


def headline_sentiment(headlines: List[str]) -> Tuple[str, int]:
    """Lafzon ki ginti se mota andaza: ('bullish'|'bearish'|'neutral', score). Sirf ishara, peshgoi nahi."""
    import re

    score = 0
    for h in headlines or []:
        words = set(re.findall(r"[a-z\-]+", h.lower()))
        score += len(words & BULLISH_WORDS) - len(words & BEARISH_WORDS)
    label = "bullish" if score >= 2 else "bearish" if score <= -2 else "neutral"
    return label, score


class NewsClient:
    def __init__(self, text_get=_text_get, json_get=None, feeds=None, clock=time.time):
        self.text_get = text_get
        self.json_get = json_get
        self.feeds = feeds or DEFAULT_FEEDS
        self.clock = clock
        self._cache = {}

    def _cached(self, key: str, ttl: int, fn):
        hit = self._cache.get(key)
        if hit and self.clock() - hit[0] < ttl:
            return hit[1]
        try:
            val = fn()
        except Exception:
            val = hit[1] if hit else None
        self._cache[key] = (self.clock(), val)
        return val

    def headlines(self, kind: str, limit: int = 6) -> List[str]:
        def load():
            out: List[str] = []
            for url in self.feeds.get(kind, []):
                try:
                    out += parse_rss(self.text_get(url), limit)
                except Exception:
                    continue
            return out[:limit]

        return self._cached("news:" + kind, 600, load) or []

    def fear_greed(self) -> Optional[Tuple[int, str]]:
        def load():
            if self.json_get is None:
                from data.base import default_http_get

                data = default_http_get(FNG_URL, {"limit": 1})
            else:
                data = self.json_get(FNG_URL, {"limit": 1})
            d = data["data"][0]
            return int(d["value"]), d["value_classification"]

        return self._cached("fng", 1800, load)

    def context(self, kind: str) -> str:
        """AI prompt ke liye chhota text."""
        parts = []
        heads = self.headlines(kind)
        if heads:
            parts.append("Recent headlines:\n" + "\n".join(f"- {h}" for h in heads))
            label, score = headline_sentiment(heads)
            parts.append(f"Headline sentiment (lafzon se mota andaza): {label} ({score:+d})")
        if kind == "crypto":
            fg = self.fear_greed()
            if fg:
                parts.append(f"Crypto Fear & Greed Index: {fg[0]} ({fg[1]})")
        return "\n".join(parts)
