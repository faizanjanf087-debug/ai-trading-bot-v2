from dataclasses import dataclass
from typing import Any


@dataclass
class Container:
    """Sab services ek jagah (handlers isi se lete hain)."""
    settings: Any
    approval: Any
    users: Any
    signal_repo: Any
    signal_service: Any
    alerts: Any
    market: Any
    budget: Any
    analysis: Any
    ai: Any
    news: Any
    chat: Any
    memory: Any
    watchlist: Any
    scanner: Any
    watcher: Any
    notifier: Any
    db: Any
    journal: Any = None
    calendar: Any = None
    discipline: Any = None
    media: Any = None
    speech: Any = None
    vision: Any = None
