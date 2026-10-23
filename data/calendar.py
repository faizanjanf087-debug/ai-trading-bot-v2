"""Economic calendar (high-impact khabrein) aur news blackout. Fail-safe: data na mile to bot chalta rehta hai.

Default source ek free weekly JSON hai (title, country, date, impact, forecast, previous). Is ka URL
CALENDAR_URL se badla ja sakta hai. Source band/rate-limit ho to purana data chalta rehta hai, aur owner
`/event add` se khud bhi bari khabrein (FOMC, NFP...) daal sakta hai.
"""
import json
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

DEFAULT_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
IMPACT_RANK = {"low": 1, "medium": 2, "high": 3}
NON_FX = {"XAU", "XAG", "BTC", "ETH", "SOL"}
CACHE_SECONDS = 3600
MANUAL_KEY = "calendar:manual"


def currencies_for(symbol: str) -> set:
    """XAUUSD -> {USD}, EURUSD -> {EUR, USD}, BTCUSD -> {USD}."""
    s = (symbol or "").upper()
    cur = {c for c in (s[:3], s[3:6]) if len(c) == 3 and c not in NON_FX}
    return cur or {"USD"}


def parse_events(data) -> List[dict]:
    """Source ke JSON se events. Kharab/adhoori entries chhor di jati hain."""
    out: List[dict] = []
    if not isinstance(data, list):
        return out
    for e in data:
        try:
            impact = str(e.get("impact", "")).strip().lower()
            if impact not in IMPACT_RANK:
                continue                      # Holiday waghera
            dt = datetime.fromisoformat(str(e["date"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out.append({
                "ts": int(dt.timestamp()), "currency": str(e.get("country", "")).strip().upper(),
                "impact": impact, "title": str(e.get("title", "")).strip(),
                "forecast": str(e.get("forecast", "") or "").strip(),
                "previous": str(e.get("previous", "") or "").strip(), "manual": False,
            })
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return sorted(out, key=lambda x: x["ts"])


class CalendarClient:
    def __init__(self, kv=None, json_get=None, url: str = DEFAULT_URL, clock=time.time, enabled: bool = True):
        self.kv = kv
        self.json_get = json_get
        self.url = url or DEFAULT_URL
        self.clock = clock
        self.enabled = enabled
        self._feed: List[dict] = []
        self._loaded_at = 0.0
        self.last_error: Optional[str] = None

    # ---- feed ----
    def _fetch(self) -> List[dict]:
        if self.json_get is None:
            from data.base import default_http_get

            return parse_events(default_http_get(self.url, {}))
        return parse_events(self.json_get(self.url, {}))

    def _feed_events(self) -> List[dict]:
        if not self.enabled:
            return []
        now = self.clock()
        if self._loaded_at and now - self._loaded_at < CACHE_SECONDS:
            return self._feed
        self._loaded_at = now            # fail ho tab bhi ghante bhar dobara na pukaren (rate limit)
        try:
            self._feed = self._fetch()
            self.last_error = None
        except Exception as e:           # purana feed rakho
            self.last_error = str(e)[:150]
        return self._feed

    # ---- owner ki daali hui khabrein ----
    def manual(self) -> List[dict]:
        if self.kv is None:
            return []
        try:
            items = json.loads(self.kv.get(MANUAL_KEY, "[]") or "[]")
        except ValueError:
            return []
        return [dict(i, manual=True) for i in items if isinstance(i, dict) and "ts" in i]

    def add_manual(self, ts: int, currency: str, title: str, impact: str = "high") -> None:
        if self.kv is None:
            raise RuntimeError("Manual events ke liye database chahiye.")
        keep = [i for i in self.manual() if i["ts"] >= self.clock() - 86400]
        keep.append({"ts": int(ts), "currency": currency.upper(), "title": title.strip()[:80], "impact": impact})
        self.kv.set(MANUAL_KEY, json.dumps(sorted(keep, key=lambda x: x["ts"])))

    def clear_manual(self) -> None:
        if self.kv is not None:
            self.kv.set(MANUAL_KEY, "[]")

    # ---- sawal ----
    def events(self) -> List[dict]:
        return sorted(self._feed_events() + self.manual(), key=lambda x: x["ts"])

    def upcoming(self, currencies: Optional[Iterable[str]] = None, hours: float = 24, min_impact: str = "high",
                 now: Optional[float] = None) -> List[dict]:
        now = self.clock() if now is None else now
        cur = {c.upper() for c in currencies} if currencies else None
        floor = IMPACT_RANK.get(min_impact, 3)
        return [e for e in self.events()
                if now - 900 <= e["ts"] <= now + hours * 3600
                and IMPACT_RANK.get(e["impact"], 0) >= floor
                and (cur is None or e["currency"] in cur or e["currency"] == "ALL")]

    def blackout(self, symbol: str, now: Optional[float] = None, before_min: int = 30,
                 after_min: int = 15) -> Optional[dict]:
        """Bari khabar se pehle/baad ki khidki mein ho to wo event, warna None."""
        now = self.clock() if now is None else now
        hits = [e for e in self.events()
                if e["impact"] == "high" and (e["currency"] in currencies_for(symbol) or e["currency"] == "ALL")
                and e["ts"] - before_min * 60 <= now <= e["ts"] + after_min * 60]
        return min(hits, key=lambda e: abs(e["ts"] - now)) if hits else None

    def context(self, symbol: Optional[str] = None, hours: float = 24) -> str:
        """AI prompt ke liye chhota text."""
        ev = self.upcoming(currencies_for(symbol) if symbol else None, hours)[:5]
        if not ev:
            return ""
        lines = [f"- {datetime.fromtimestamp(e['ts'], timezone.utc):%a %d %b %H:%M} UTC {e['currency']}: {e['title']}"
                 + (f" (forecast {e['forecast']}, previous {e['previous']})" if e.get("forecast") or e.get("previous") else "")
                 for e in ev]
        return f"Upcoming high-impact economic events (next {int(hours)}h):\n" + "\n".join(lines)
