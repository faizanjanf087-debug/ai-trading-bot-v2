"""Swing points, Support/Resistance, Fibonacci."""
from typing import List, Tuple

import pandas as pd


def pivots(df: pd.DataFrame, n: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Swing highs/lows: wo candle jis ka high (low) aas-paas ki n-n candles se zyada (kam) ho.
    Aakhri n candles mein pivot confirm nahi hota, is liye wahan nahi milta."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    for i in range(n, len(df) - n):
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - 1]:
            highs.append((i, float(h[i])))
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - 1]:
            lows.append((i, float(l[i])))
    return highs, lows


def support_resistance(df: pd.DataFrame, atr_value: float, n: int = 3, max_levels: int = 8) -> List[dict]:
    """Pivots ko paas-paas cluster karke levels. Zyada touches = mazboot level."""
    highs, lows = pivots(df, n)
    pts = sorted([p for _, p in highs] + [p for _, p in lows])
    if not pts or atr_value <= 0:
        return []
    tol = 0.35 * atr_value
    clusters: List[List[float]] = [[pts[0]]]
    for p in pts[1:]:
        if p - clusters[-1][-1] <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    last = float(df["close"].iloc[-1])
    levels = [
        {"price": sum(c) / len(c), "touches": len(c), "kind": "support" if sum(c) / len(c) < last else "resistance"}
        for c in clusters
    ]
    levels.sort(key=lambda x: (-x["touches"], abs(x["price"] - last)))
    return sorted(levels[:max_levels], key=lambda x: x["price"])


def nearest_level(levels: List[dict], price: float, kind: str):
    """Price ke sab se qareeb 'support' (neeche) ya 'resistance' (upar)."""
    if kind == "support":
        c = [l for l in levels if l["price"] < price]
        return max(c, key=lambda l: l["price"]) if c else None
    c = [l for l in levels if l["price"] > price]
    return min(c, key=lambda l: l["price"]) if c else None


def fibonacci(df: pd.DataFrame, n: int = 3, lookback: int = 120):
    """Bade swing par retracement levels. Aakhri 3 swings (legs) mein se sab se bada leg chunte hain,
    taake chhota pullback asal move ko na chhupa de."""
    d = df.iloc[-lookback:]
    highs, lows = pivots(d, n)
    pts = sorted([(i, p, "H") for i, p in highs] + [(i, p, "L") for i, p in lows])
    # lagatar ek hi type ke pivots mein se sab se extreme rakho
    merged = []
    for pt in pts:
        if merged and merged[-1][2] == pt[2]:
            keep_new = pt[1] > merged[-1][1] if pt[2] == "H" else pt[1] < merged[-1][1]
            if keep_new:
                merged[-1] = pt
        else:
            merged.append(pt)
    if len(merged) < 2:
        return None
    legs = list(zip(merged[:-1], merged[1:]))[-3:]
    a, b = max(legs, key=lambda leg: abs(leg[1][1] - leg[0][1]))
    if a[1] == b[1]:
        return None
    direction = "up" if b[2] == "H" else "down"
    start, end = a[1], b[1]
    rng = abs(end - start)
    sign = -1 if direction == "up" else 1  # up-move ka retracement neeche aata hai
    levels = {r: end + sign * rng * r for r in (0.382, 0.5, 0.618, 0.786)}
    return {"direction": direction, "start": start, "end": end, "levels": levels}


def market_structure(df: pd.DataFrame, n: int = 3, lookback: int = 150):
    """Aakhri do swing highs/lows se structure: HH+HL = 'bullish', LH+LL = 'bearish', warna None."""
    highs, lows = pivots(df.iloc[-lookback:], n)
    if len(highs) < 2 or len(lows) < 2:
        return None
    hh, hl = highs[-1][1] > highs[-2][1], lows[-1][1] > lows[-2][1]
    if hh and hl:
        return "bullish"
    if not hh and not hl:
        return "bearish"
    return None
