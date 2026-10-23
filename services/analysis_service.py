"""Candles lo -> analysis -> setup. Scanner, /signal, /analyze aur chat sab yahi use karte hain."""
from typing import Optional, Tuple

import logging

from analysis.signal_engine import analyze, build_setup
from data.base import DataError
from data.market_data import MarketData
from services import lifecycle

log = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, market: MarketData, min_score: float = 6.0, counter_trend_extra: float = 0.0):
        self.market = market
        self.min_score = min_score
        self.counter_trend_extra = counter_trend_extra

    def run(self, symbol: str, mode: str, priority: str = "normal") -> Tuple[Optional[dict], Optional[dict]]:
        """Blocking hai (HTTP). Async code mein asyncio.to_thread ke saath chalayein."""
        df = self.market.get_candles(symbol, mode, priority=priority)
        a = analyze(df, symbol, mode)
        return a, build_setup(a, self.min_score, self.counter_trend_extra)

    def run_fresh(self, symbol: str, mode: str, priority: str = "normal"):
        """run() + taaza price se check. Analysis band candles par hoti hai, is liye signal banne tak
        price 5-10 minute aage nikal chuki hoti hai. Yahan us gap ko dekhte hain:
        - LIMIT: gap mein entry touch ho gayi / price TP1 tak chali gayi -> setup purana, None
        - MARKET: entry ko taaza price par le aate hain (SL/TP ka fasla wahi)"""
        a, setup = self.run(symbol, mode, priority)
        if not setup:
            return a, setup
        try:
            df = self.market.get_recent_1m(symbol, 25, priority)
        except DataError as e:   # BudgetExhausted bhi yahi hai
            log.info("%s: taaza price nahi mili (%s), setup jaisa tha waisa", symbol, e)
            return a, setup
        gap_start = setup["last_candle_ts"] + setup["tf_seconds"]
        rows = [(int(ts.timestamp()), float(r.open), float(r.high), float(r.low), float(r.close))
                for ts, r in zip(df.index, df.itertuples()) if int(ts.timestamp()) >= gap_start]
        if not rows:
            return a, setup
        live = rows[-1][4]
        if setup["entry_type"] == "MARKET":
            delta = live - setup["entry"]
            setup = dict(setup, entry=live, sl=setup["sl"] + delta, tp1=setup["tp1"] + delta, tp2=setup["tp2"] + delta)
            return a, setup
        probe = {"side": setup["side"], "entry": setup["entry"], "sl": setup["sl"], "sl_initial": setup["sl"],
                 "tp1": setup["tp1"], "tp2": setup["tp2"], "status": "PENDING", "expires_ts": None,
                 "last_candle_ts": gap_start, "activated_ts": None}
        out, _ = lifecycle.evaluate(probe, rows, rows[-1][0])
        if out["status"] != "PENDING":
            log.info("%s %s setup purana (gap mein %s), chhod diya", symbol, setup["side"], out["status"])
            return a, None
        return a, setup
