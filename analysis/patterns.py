"""Candlestick aur chart patterns. Har pattern (naam, bias) deta hai; bias: bullish/bearish/neutral."""
from typing import List, Tuple

import numpy as np
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
    """Sab chart patterns ek jagah: Double/Triple Top-Bottom, H&S, triangles, wedges, butterfly, Range Breakout."""
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
    out += triple_tops(df, atr_value, n)
    out += butterfly(df, atr_value, n)
    out += wedges(df, atr_value, n)
    out += head_shoulders(df, atr_value, n)
    out += triangles(df, atr_value, n)
    return out


# Har pattern ka score weight. Mukammal reversal (H&S, triple, harmonic) sabse bharosemand mana gaya hai;
# breakout (triangle, wedge, range) pehle confirm hota hai, is liye kam weight. Naam ki spelling yahan aur
# detection functions mein ek jaisi honi chahiye, warna default weight lagega.
PATTERN_WEIGHTS = {
    "Double Top": 2.0, "Double Bottom": 2.0,
    "Triple Top": 2.5, "Triple Bottom": 2.5,
    "Head & Shoulders": 2.5, "Inverse Head & Shoulders": 2.5,
    "Bullish Butterfly": 2.5, "Bearish Butterfly": 2.5,
    "Ascending Triangle Breakout": 1.5, "Descending Triangle Breakdown": 1.5,
    "Rising Wedge Breakdown": 1.5, "Falling Wedge Breakout": 1.5,
    "Range Breakout Up": 1.5, "Range Breakout Down": 1.5,
}
DEFAULT_PATTERN_WEIGHT = 1.5


def pattern_weight(name: str) -> float:
    return PATTERN_WEIGHTS.get(name, DEFAULT_PATTERN_WEIGHT)


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


def triple_tops(df: pd.DataFrame, atr_value: float, n: int = 3, recent: int = 60) -> List[Tuple[str, str]]:
    """Triple Top (bearish) aur Triple Bottom (bullish): teen barabar peaks/troughs, neckline ke neeche/upar confirm."""
    out: List[Tuple[str, str]] = []
    if len(df) < 60 or atr_value <= 0:
        return out
    sub = df.iloc[-120:].reset_index(drop=True)
    highs, lows = pivots(sub, n)
    tol = 0.5 * atr_value
    last = float(sub["close"].iloc[-1])
    cutoff = len(sub) - recent

    if len(highs) >= 3:
        pts = highs[-3:]
        (i1, a), (i2, b), (i3, c) = pts
        if i3 >= cutoff and i2 - i1 >= 4 and i3 - i2 >= 4 \
                and _near(a, b, tol) and _near(b, c, tol):
            neck = min(sub["low"].iloc[i1:i2 + 1].min(), sub["low"].iloc[i2:i3 + 1].min())
            if last < neck - 0.1 * atr_value:
                out.append(("Triple Top", "bearish"))
    if len(lows) >= 3:
        (i1, a), (i2, b), (i3, c) = lows[-3:]
        if i3 >= cutoff and i2 - i1 >= 4 and i3 - i2 >= 4 \
                and _near(a, b, tol) and _near(b, c, tol):
            neck = max(sub["high"].iloc[i1:i2 + 1].max(), sub["high"].iloc[i2:i3 + 1].max())
            if last > neck + 0.1 * atr_value:
                out.append(("Triple Bottom", "bullish"))
    return out


def _zigzag(highs, lows):
    """High/low pivots ko index ke hisaab se milata hai, aur H/L ko baari baari (alternate) rakhta hai.
    Do ek jaisi kism ke pivots aaye to zyada extreme wala rakhta hai. Wapas: [(index, price, 'H'|'L'), ...]"""
    pts = sorted([(i, p, "H") for i, p in highs] + [(i, p, "L") for i, p in lows])
    out = []
    for pt in pts:
        if out and out[-1][2] == pt[2]:
            keep = max if pt[2] == "H" else min
            if keep(pt[1], out[-1][1]) == pt[1]:
                out[-1] = pt
        else:
            out.append(pt)
    return out


def butterfly(df: pd.DataFrame, atr_value: float, n: int = 3, recent: int = 15) -> List[Tuple[str, str]]:
    """Butterfly harmonic (Fibonacci ratios): X-A-B-C-D. D (aakhri pivot) 1.27 XA extension par ho aur
    price wahan se palat rahi ho to reversal ka ishara. Bullish: D neeche (X ke neeche). Bearish: D upar."""
    out: List[Tuple[str, str]] = []
    if len(df) < 60 or atr_value <= 0:
        return out
    sub = df.iloc[-150:].reset_index(drop=True)
    highs, lows = pivots(sub, n)
    zz = _zigzag(highs, lows)
    if len(zz) < 5:
        return out
    (_, x, tx), (_, a, ta), (_, b, tb), (ic, c, tc), (idd, d, td) = zz[-5:]
    if idd < len(sub) - recent:
        return out
    last = float(sub["close"].iloc[-1])
    xa = abs(a - x)
    if xa <= 0.5 * atr_value:
        return out
    ab = abs(b - a) / xa
    bc = abs(c - b) / abs(b - a) if b != a else 0
    cd = abs(d - c) / abs(c - b) if c != b else 0
    ok = 0.7 <= ab <= 0.85 and 0.35 <= bc <= 0.9 and 1.5 <= cd <= 2.3
    if not ok:
        return out
    if tx == "L" and td == "L" and ta == "H":        # bullish: D X ke neeche
        target = a - 1.27 * (a - x)
        if abs(d - target) <= 0.15 * xa and last > d + 0.2 * atr_value:
            out.append(("Bullish Butterfly", "bullish"))
    elif tx == "H" and td == "H" and ta == "L":      # bearish: D X ke upar
        target = a + 1.27 * (x - a)
        if abs(d - target) <= 0.15 * xa and last < d - 0.2 * atr_value:
            out.append(("Bearish Butterfly", "bearish"))
    return out


def wedges(df: pd.DataFrame, atr_value: float, n: int = 3, recent: int = 60) -> List[Tuple[str, str]]:
    """Rising Wedge (bearish breakdown) aur Falling Wedge (bullish breakout).
    Upper aur lower trendlines aakhri 3-3 pivots par fit hoti hain; dono ek hi taraf jhuk kar converge karti hon."""
    out: List[Tuple[str, str]] = []
    if len(df) < 60 or atr_value <= 0:
        return out
    sub = df.iloc[-120:].reset_index(drop=True)
    highs, lows = pivots(sub, n)
    highs = [p for p in highs if p[0] >= len(sub) - recent][-3:]
    lows = [p for p in lows if p[0] >= len(sub) - recent][-3:]
    if len(highs) < 3 or len(lows) < 3:
        return out
    hx, hy = [p[0] for p in highs], [p[1] for p in highs]
    lx, ly = [p[0] for p in lows], [p[1] for p in lows]
    hs = np.polyfit(hx, hy, 1)
    ls = np.polyfit(lx, ly, 1)
    last_i = len(sub) - 1
    up_now = hs[0] * last_i + hs[1]
    lo_now = ls[0] * last_i + ls[1]
    if up_now - lo_now <= 0.5 * atr_value:          # band bahut tang ho gayi: wedge nahi
        return out
    last = float(sub["close"].iloc[-1])
    if hs[0] > 0 and ls[0] > 0 and ls[0] > hs[0]:    # dono upar, neeche wali tez: rising wedge
        if last < lo_now - 0.1 * atr_value:
            out.append(("Rising Wedge Breakdown", "bearish"))
    if hs[0] < 0 and ls[0] < 0 and hs[0] < ls[0]:    # dono neeche, upar wali tez: falling wedge
        if last > up_now + 0.1 * atr_value:
            out.append(("Falling Wedge Breakout", "bullish"))
    return out
