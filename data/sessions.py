"""Forex market kab khula hai aur kab scan karna hai."""
from datetime import datetime, timezone


def _utc(now: float) -> datetime:
    return datetime.fromtimestamp(now, tz=timezone.utc)


def forex_open(now: float) -> bool:
    """Forex: Sunday ~22:00 UTC se Friday ~22:00 UTC tak khula (taqreeban)."""
    d = _utc(now)
    wd, h = d.weekday(), d.hour  # Mon=0 ... Sun=6
    if wd == 5:                  # Saturday
        return False
    if wd == 4 and h >= 22:      # Friday raat
        return False
    if wd == 6 and h < 22:       # Sunday din
        return False
    return True


def in_session(now: float, session: str) -> bool:
    """session = '07-20' (UTC ghante). Start <= ghanta < end."""
    try:
        a, b = [int(x) for x in session.split("-")]
    except ValueError:
        return True
    h = _utc(now).hour
    return a <= h < b if a < b else (h >= a or h < b)
