"""Purane candles par signal engine ko chala kar dekhna ke strategy ne kaisa kaam kiya.

Istemal:  python -m backtest.runner XAUUSD scalp     (data fetch hota hai, Twelve Data ke credits lagte hain)
Nateeja sirf andaza hai: spread, slippage aur commissions shamil nahi.
"""
import sys
from typing import List

import pandas as pd

from analysis.signal_engine import MIN_BARS, analyze, build_setup
from config.markets import MODES
from services import lifecycle


def backtest(df: pd.DataFrame, symbol: str, mode: str, min_score: float = 6.0, step: int = 1,
             counter_trend_extra: float = 0.0) -> dict:
    tf = MODES[mode]["tf_seconds"]
    pending_bars = MODES[mode]["pending_bars"]
    rows = [(int(ts.timestamp()), float(r.open), float(r.high), float(r.low), float(r.close))
            for ts, r in zip(df.index, df.itertuples())]
    trades: List[dict] = []
    i = MIN_BARS
    while i < len(df) - 1:
        window = df.iloc[: i + 1]
        a = analyze(window, symbol, mode)
        setup = build_setup(a, min_score, counter_trend_extra) if a else None
        if not setup:
            i += step
            continue
        t0 = rows[i][0]
        sig = {
            "side": setup["side"], "entry": setup["entry"], "sl": setup["sl"], "sl_initial": setup["sl"],
            "tp1": setup["tp1"], "tp2": setup["tp2"], "status": "ACTIVE" if setup["entry_type"] == "MARKET" else "PENDING",
            "expires_ts": t0 + pending_bars * tf, "last_candle_ts": t0 + tf,
            "activated_ts": t0 if setup["entry_type"] == "MARKET" else None,
        }
        j = i + 1
        while j < len(rows) and sig["status"] in lifecycle.OPEN:
            sig, _ = lifecycle.evaluate(sig, [rows[j]], rows[j][0])
            j += 1
        if sig["status"] not in lifecycle.OPEN:
            trades.append({"symbol": symbol, "side": setup["side"], "status": sig["status"],
                           "r": sig.get("result_r") or 0.0, "ts": t0})
        i = max(j, i + step)   # trade chalte waqt naya signal nahi
    return summarize(trades)


def summarize(trades: List[dict]) -> dict:
    taken = [t for t in trades if t["status"] in ("TP2", "SL", "BE")]
    wins = [t for t in taken if t["r"] > 0]
    losses = [t for t in taken if t["r"] < 0]
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in taken:
        equity += t["r"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "signals": len(trades), "trades": len(taken), "wins": len(wins), "losses": len(losses),
        "win_rate": round(100 * len(wins) / len(taken), 1) if taken else None,
        "net_r": round(sum(t["r"] for t in taken), 2),
        "avg_r": round(sum(t["r"] for t in taken) / len(taken), 3) if taken else None,
        "max_drawdown_r": round(max_dd, 2),
        "skipped": len(trades) - len(taken),
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    from config.markets import resolve_symbol
    from config.settings import load_settings
    from data.budget import CreditBudget
    from data.market_data import MarketData
    from data.providers import KrakenClient, TwelveDataClient
    from db.database import Database
    from db.kv import KV

    symbol, mode = resolve_symbol(argv[1]), argv[2]
    if not symbol or mode not in MODES:
        print("Galat symbol ya mode")
        return 1
    s = load_settings()
    db = Database(s.database_path)
    market = MarketData(TwelveDataClient(s.twelvedata_key), KrakenClient(),
                        CreditBudget(KV(db), s.td_per_minute, s.td_per_day, s.td_monitor_reserve))
    df = market.get_candles(symbol, mode, priority="monitor", max_age=0)
    print(f"{symbol} {mode}: {len(df)} candles")
    print(backtest(df, symbol, mode, s.min_score))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
