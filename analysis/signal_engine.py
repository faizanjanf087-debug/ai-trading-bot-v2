"""Sab indicators ko jod kar score aur trade setup (entry/SL/TP) banata hai.

Yeh market ki peshgoi nahi karta; yeh rule-based confluence score hai. Isko backtest se parkhein.
"""
from typing import List, Optional

import pandas as pd

from analysis import indicators as ind
from analysis.divergence import rsi_divergence
from analysis.levels import fibonacci, nearest_level, support_resistance
from analysis.patterns import candlestick, chart_patterns
from config.markets import MODES

MIN_BARS = 80


def analyze(df: pd.DataFrame, symbol: str, mode: str) -> Optional[dict]:
    """df: entry timeframe ki band candles. Data kam ho to None."""
    if df is None or len(df) < MIN_BARS:
        return None
    m = MODES[mode]
    close = df["close"]
    price = float(close.iloc[-1])

    atr_s = ind.atr(df)
    atr_v = float(atr_s.iloc[-1])
    if not atr_v or atr_v != atr_v:
        return None

    ema_fast, ema_slow = ind.ema(close, 20), ind.ema(close, 50)
    rsi_s = ind.rsi(close)
    macd_line, macd_sig, hist = ind.macd(close)

    htf = ind.resample(df, m["htf_factor"])
    htf_trend = "flat"
    if len(htf) >= 55:
        e20, e50 = ind.ema(htf["close"], 20).iloc[-1], ind.ema(htf["close"], 50).iloc[-1]
        last_h = htf["close"].iloc[-1]
        if e20 > e50 and last_h > e50:
            htf_trend = "up"
        elif e20 < e50 and last_h < e50:
            htf_trend = "down"

    levels = support_resistance(df, atr_v)
    fib = fibonacci(df)
    cs = candlestick(df)
    cp = chart_patterns(df, atr_v)
    div = rsi_divergence(df, rsi_s)
    vol = ind.volume_spike(df)

    a = {
        "symbol": symbol, "mode": mode, "tf": m["tf"], "price": price, "atr": atr_v,
        "ema_fast": float(ema_fast.iloc[-1]), "ema_slow": float(ema_slow.iloc[-1]),
        "htf_trend": htf_trend, "rsi": float(rsi_s.iloc[-1]),
        "macd_hist": float(hist.iloc[-1]), "macd_hist_prev": float(hist.iloc[-2]),
        "macd_cross": ("bullish" if macd_line.iloc[-1] > macd_sig.iloc[-1] and macd_line.iloc[-2] <= macd_sig.iloc[-2]
                       else "bearish" if macd_line.iloc[-1] < macd_sig.iloc[-1] and macd_line.iloc[-2] >= macd_sig.iloc[-2]
                       else None),
        "levels": levels, "fib": fib, "candles": cs, "chart_patterns": cp,
        "divergence": div, "volume_spike": vol,
        "last_candle_ts": int(df.index[-1].timestamp()),
    }
    _score(a)
    return a


def _score(a: dict) -> None:
    buy, sell = 0.0, 0.0
    rb: List[str] = []
    rs: List[str] = []
    price, atr_v = a["price"], a["atr"]

    # 1) Trend (entry TF + higher TF)
    if a["ema_fast"] > a["ema_slow"]:
        buy += 1; rb.append(f"{a['tf']} trend up (EMA20>EMA50)")
    elif a["ema_fast"] < a["ema_slow"]:
        sell += 1; rs.append(f"{a['tf']} trend down (EMA20<EMA50)")
    if a["htf_trend"] == "up":
        buy += 1.5; rb.append("Higher timeframe trend up")
    elif a["htf_trend"] == "down":
        sell += 1.5; rs.append("Higher timeframe trend down")

    # 2) RSI
    r = a["rsi"]
    if r < 35:
        buy += 1; rb.append(f"RSI oversold ({r:.0f})")
    elif r > 65:
        sell += 1; rs.append(f"RSI overbought ({r:.0f})")
    if a["divergence"] == "bullish":
        buy += 2; rb.append("Bullish RSI divergence")
    elif a["divergence"] == "bearish":
        sell += 2; rs.append("Bearish RSI divergence")

    # 3) MACD
    if a["macd_cross"] == "bullish":
        buy += 1.5; rb.append("MACD bullish cross")
    elif a["macd_cross"] == "bearish":
        sell += 1.5; rs.append("MACD bearish cross")
    elif a["macd_hist"] > 0 and a["macd_hist"] > a["macd_hist_prev"]:
        buy += 0.5; rb.append("MACD momentum rising")
    elif a["macd_hist"] < 0 and a["macd_hist"] < a["macd_hist_prev"]:
        sell += 0.5; rs.append("MACD momentum falling")

    # 4) Candlestick + chart patterns
    for name, bias in a["candles"]:
        if bias == "bullish":
            buy += 1; rb.append(name)
        elif bias == "bearish":
            sell += 1; rs.append(name)
    for name, bias in a["chart_patterns"]:
        w = 2 if "Breakout" not in name else 1.5
        if bias == "bullish":
            buy += w; rb.append(name)
        elif bias == "bearish":
            sell += w; rs.append(name)

    # 5) Support / Resistance ke paas
    sup = nearest_level(a["levels"], price, "support")
    res = nearest_level(a["levels"], price, "resistance")
    if sup and price - sup["price"] <= 0.8 * atr_v:
        buy += 1.5 + (0.5 if sup["touches"] >= 3 else 0); rb.append(f"Near support {sup['price']:.5g} ({sup['touches']} touches)")
    if res and res["price"] - price <= 0.8 * atr_v:
        sell += 1.5 + (0.5 if res["touches"] >= 3 else 0); rs.append(f"Near resistance {res['price']:.5g} ({res['touches']} touches)")

    # 6) Fibonacci: trend ke saath retracement zone (0.5 - 0.618)
    fib = a["fib"]
    if fib:
        lo, hi = sorted((fib["levels"][0.5], fib["levels"][0.618]))
        if lo - 0.2 * atr_v <= price <= hi + 0.2 * atr_v:
            if fib["direction"] == "up":
                buy += 1; rb.append("Fib 50-61.8% pullback in uptrend")
            else:
                sell += 1; rs.append("Fib 50-61.8% pullback in downtrend")

    # 7) Volume
    if a["volume_spike"]:
        last_up = a["macd_hist"] >= 0
        if last_up:
            buy += 0.5; rb.append("Volume spike")
        else:
            sell += 0.5; rs.append("Volume spike")

    a.update(score_buy=round(buy, 1), score_sell=round(sell, 1), reasons_buy=rb, reasons_sell=rs)


def build_setup(a: dict, min_score: float = 6.0, counter_trend_extra: float = 0.0) -> Optional[dict]:
    """Score kaafi ho to entry/SL/TP. Warna None (koi saaf setup nahi).

    counter_trend_extra: higher timeframe trend ke KHILAF signal ke liye score itna zyada chahiye."""
    if a is None:
        return None
    sb, ss = a["score_buy"], a["score_sell"]
    if max(sb, ss) < min_score or abs(sb - ss) < 2:
        return None
    side = "buy" if sb > ss else "sell"
    score = sb if side == "buy" else ss
    htf = a.get("htf_trend")
    if counter_trend_extra and htf in ("up", "down") and (side == "buy") != (htf == "up") \
            and score < min_score + counter_trend_extra:
        return None
    reasons = a["reasons_buy"] if side == "buy" else a["reasons_sell"]
    price, atr_v = a["price"], a["atr"]
    sgn = 1 if side == "buy" else -1

    near = nearest_level(a["levels"], price, "support" if side == "buy" else "resistance")
    against = nearest_level(a["levels"], price, "resistance" if side == "buy" else "support")

    # Entry: pullback par limit, agar level bahut qareeb ho to seedha market
    entry_type, entry, anchor = "MARKET", price, None
    cands = []
    if near and 0.25 * atr_v < abs(price - near["price"]) <= 1.5 * atr_v:
        cands.append(near["price"] + sgn * 0.1 * atr_v)   # level se zara pehle fill ho jaye
        anchor = near["price"]
    ema = a["ema_fast"]
    if 0.25 * atr_v < sgn * (price - ema) <= 1.2 * atr_v:
        cands.append(ema)
    if cands:
        entry = min(cands, key=lambda x: abs(price - x))
        entry_type = "LIMIT"

    # SL: kam az kam 1 ATR, ya level ke peeche
    risk = 1.0 * atr_v
    if anchor is not None:
        risk = max(risk, abs(entry - (anchor - sgn * 0.3 * atr_v)))
    if risk > 2.5 * atr_v:
        return None
    sl = entry - sgn * risk
    tp1 = entry + sgn * 1.5 * risk
    tp2 = entry + sgn * 2.5 * risk

    # Agar raaste mein koi mazboot opposite level TP1 se pehle hai (RR kharab) to setup chhod do
    if against and 0 < sgn * (against["price"] - entry) < 1.0 * risk:
        return None

    m = MODES[a["mode"]]
    return {
        "symbol": a["symbol"], "mode": a["mode"], "tf": a["tf"], "side": side,
        "entry_type": entry_type, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
        "rr1": 1.5, "rr2": 2.5, "score": score, "reasons": reasons, "atr": atr_v,
        "pending_bars": m["pending_bars"], "tf_seconds": m["tf_seconds"],
        "last_candle_ts": a["last_candle_ts"],
    }
