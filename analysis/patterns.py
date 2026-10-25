"""Candlestick aur chart patterns. Har pattern (naam, bias) deta hai; bias: bullish/bearish/neutral."""
from typing import List, Tuple

import pandas as pd

from analysis.levels import pivots


def _parts(c):
    o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
    body = abs(cl - o)
    rng = max(h - l, 1e-12)
    upper = h - max(o, cl)
    lower = min(o, cl) - l
    return o, h, l, cl, body, rng, upper, lower


def candlestick(df: pd.DataFrame) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if len(df) < 4:
        return out
    c0, c1, c2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    o, h, l, cl, body, rng, upper, lower = _parts(c0)
    po, ph, pl, pcl, pbody, prng, _, _ = _parts(c1)

    if body <= 0.1 * rng:
        out.append(("Doji", "neutral"))
    # Hammer: chhoti body upar, lambi neeche wali shadow, pehle girawat
    downtrend = df["close"].iloc[-6:-1].iloc[0] > df["close"].iloc[-2] if len(df) >= 7 else False
    uptrend = df["close"].iloc[-6:-1].iloc[0] < df["close"].iloc[-2] if len(df) >= 7 else False
    if lower >= 2 * body and upper <= 0.35 * rng and body > 0 and downtrend:
        out.append(("Hammer", "bullish"))
    if upper >= 2 * body and lower <= 0.35 * rng and body > 0 and uptrend:
        out.append(("Shooting Star", "bearish"))
    # Engulfing
    if pcl < po and cl > o and cl >= po and o <= pcl and body > pbody:
        out.append(("Bullish Engulfing", "bullish"))
    if pcl > po and cl < o and cl <= po and o >= pcl and body > pbody:
        out.append(("Bearish Engulfing", "bearish"))
    # Morning / Evening star (3 candles)
    o2, _, _, cl2, body2, rng2, _, _ = _parts(c2)
    if cl2 < o2 and body2 > 0.5 * rng2 and pbody <= 0.3 * prng and cl > o and cl > (o2 + cl2) / 2:
        out.append(("Morning Star", "bullish"))
    if cl2 > o2 and body2 > 0.5 * rng2 and pbody <= 0.3 * prng and cl < o and cl < (o2 + cl2) / 2:
        out.append(("Evening Star", "bearish"))
    return out


def chart_patterns(df: pd.DataFrame, atr_value: float, n: int = 3) -> List[Tuple[str, str]]:
    """Double Top/Bottom aur Range Breakout (simple, rule-based)."""
    out: List[Tuple[str, str]] = []
    if len(df) < 40 or atr_value <= 0:
        return out
    highs, lows = pivots(df.iloc[-100:], n)
    tol = 0.4 * atr_value
    last = float(df["close"].iloc[-1])

    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        valley = df.iloc[-100:]["low"].iloc[i1:i2 + 1].min()
        if abs(p1 - p2) <= tol and i2 - i1 >= 5 and last < valley + 0.3 * (p2 - valley):
            out.append(("Double Top", "bearish"))
    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        peak = df.iloc[-100:]["high"].iloc[i1:i2 + 1].max()
        if abs(p1 - p2) <= tol and i2 - i1 >= 5 and last > peak - 0.3 * (peak - p2):
            out.append(("Double Bottom", "bullish"))

    # Range breakout: pichli 20 candles tang range, phir aakhri candle range se bahar band
    box = df.iloc[-22:-2]
    if len(box) >= 15:
        top, bot = box["high"].max(), box["low"].min()
        if (top - bot) <= 3.5 * atr_value:
            if last > top + 0.1 * atr_value:
                out.append(("Range Breakout Up", "bullish"))
            elif last < bot - 0.1 * atr_value:
                out.append(("Range Breakout Down", "bearish"))
    out += head_shoulders(df, atr_value, n)
    out += triangles(df, atr_value, n)
    return out


def _near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def head_shoulders(df: pd.DataFrame, atr_value: float, n: int = 3, recent: int = 40) -> List[Tuple[str, str]]:
    """Head & Shoulders (bearish) aur Inverse H&S (bullish), neckline toot kar confirm hone par.
    Teen swing highs (ya lows): beech wala sabse bada/chhota, do shoulders lagbhag barabar, aakhri pivot recent."""
    out: List[Tuple[str, str]] = []
    if len(df) < 60 or atr_value <= 0:
        return out
    sub = df.iloc[-100:].reset_index(drop=True)
    highs, lows = pivots(sub, n)
    tol = 0.6 * atr_value
    last = float(sub["close"].iloc[-1])
    cutoff = len(sub) - recent

    if len(highs) >= 3:
        (i1, a), (i2, b), (i3, c) = highs[-3:]
        if i3 >= cutoff and b > a and b > c and _near(a, c, tol):
            neck = (sub["low"].iloc[i1:i2 + 1].min() + sub["low"].iloc[i2:i3 + 1].min()) / 2
            if last < neck - 0.1 * atr_value:
                out.append(("Head & Shoulders", "bearish"))
    if len(lows) >= 3:
        (i1, a), (i2, b), (i3, c) = lows[-3:]
        if i3 >= cutoff and b < a and b < c and _near(a, c, tol):
            neck = (sub["high"].iloc[i1:i2 + 1].max() + sub["high"].iloc[i2:i3 + 1].max()) / 2
            if last > neck + 0.1 * atr_value:
                out.append(("Inverse Head & Shoulders", "bullish"))
    return out


def triangles(df: pd.DataFrame, atr_value: float, n: int = 3, recent: int = 60) -> List[Tuple[str, str]]:
    """Ascending (flat top, rising lows) aur Descending (flat bottom, falling highs) triangle.
    Sirf breakout par signal: upar toota to bullish, neeche toota to bearish."""
    out: List[Tuple[str, str]] = []
    if len(df) < 40 or atr_value <= 0:
        return out
    sub = df.iloc[-120:].reset_index(drop=True)
    highs, lows = pivots(sub, n)
    highs = [p for p in highs if p[0] >= len(sub) - recent]
    lows = [p for p in lows if p[0] >= len(sub) - recent]
    if len(highs) < 2 or len(lows) < 2:
        return out
    tol = 0.4 * atr_value
    last = float(sub["close"].iloc[-1])
    (_, h1), (_, h2) = highs[-2], highs[-1]
    (_, l1), (_, l2) = lows[-2], lows[-1]
    top = max(h1, h2)
    bot = min(l1, l2)

    if _near(h1, h2, tol) and l2 > l1 + 0.2 * atr_value and last > top + 0.1 * atr_value:
        out.append(("Ascending Triangle Breakout", "bullish"))
    if _near(l1, l2, tol) and h2 < h1 - 0.2 * atr_value and last < bot - 0.1 * atr_value:
        out.append(("Descending Triangle Breakdown", "bearish"))
    return out
