"""Ek jagah se candles lena: cache + credit budget + closed candles."""
import time
from typing import Dict, Optional, Tuple

import pandas as pd

from config.markets import MODES, SYMBOLS
from data.base import BudgetExhausted, DataError, closed_only


class MarketData:
    def __init__(self, td_client, kraken_client, budget, clock=time.time):
        self.td = td_client
        self.kraken = kraken_client
        self.budget = budget
        self.clock = clock
        self._cache: Dict[Tuple[str, str], Tuple[float, pd.DataFrame]] = {}

    def _fetch(self, symbol: str, td_interval: str, kr_interval: int, size: int, priority: str):
        meta = SYMBOLS[symbol]
        if meta["provider"] == "twelvedata":
            if not self.budget.try_spend(1, priority):
                raise BudgetExhausted("Twelve Data ke credits abhi available nahi (limit).")
            return self.td.fetch(meta["code"], td_interval, size)
        return self.kraken.fetch(meta["code"], kr_interval, size)

    def get_candles(self, symbol: str, mode: str, priority: str = "normal",
                    max_age: Optional[float] = None) -> pd.DataFrame:
        """Entry timeframe ki *band* candles. Cache ka mqsad Twelve Data ke credits bachana hai."""
        if symbol not in SYMBOLS:
            raise DataError(f"Unknown symbol: {symbol}")
        m = MODES[mode]
        now = self.clock()
        if max_age is None:
            max_age = m["tf_seconds"] * 0.9 if SYMBOLS[symbol]["provider"] == "twelvedata" else 20
        hit = self._cache.get((symbol, mode))
        if hit and now - hit[0] < max_age:
            return hit[1]
        df = self._fetch(symbol, m["td_interval"], m["kraken_interval"], m["outputsize"], priority)
        df = closed_only(df, m["tf_seconds"], now)
        self._cache[(symbol, mode)] = (now, df)
        return df

    def get_recent_1m(self, symbol: str, count: int = 15, priority: str = "monitor") -> pd.DataFrame:
        """Monitoring ke liye: taaza 1-minute candles (adhoori candle bhi, uski high/low asli hain)."""
        df = self._fetch(symbol, "1min", 1, count, priority)
        return df.iloc[-count:]
