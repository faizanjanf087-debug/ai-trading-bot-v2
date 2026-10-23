import json
from typing import List

from config.markets import SYMBOLS
from db.kv import KV


class Watchlist:
    """Scanner kin pairs ko dekhega. Owner /watch se badal sakta hai; database mein save rehta hai."""

    def __init__(self, kv: KV, default: List[str]):
        self.kv = kv
        self.default = [s for s in default if s in SYMBOLS]

    def get(self) -> List[str]:
        raw = self.kv.get("watchlist")
        if raw:
            try:
                return [s for s in json.loads(raw) if s in SYMBOLS]
            except ValueError:
                pass
        return list(self.default)

    def _save(self, items: List[str]) -> None:
        self.kv.set("watchlist", json.dumps(items))

    def add(self, symbol: str) -> bool:
        items = self.get()
        if symbol not in SYMBOLS or symbol in items:
            return False
        self._save(items + [symbol])
        return True

    def remove(self, symbol: str) -> bool:
        items = self.get()
        if symbol not in items:
            return False
        self._save([s for s in items if s != symbol])
        return True
