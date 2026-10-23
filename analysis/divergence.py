"""RSI divergence: price aur RSI ke swings mein ikhtilaaf."""
from typing import Optional

import pandas as pd

from analysis.levels import pivots


def rsi_divergence(df: pd.DataFrame, rsi_series: pd.Series, n: int = 3, lookback: int = 80) -> Optional[str]:
    """'bullish': price ne lower low banaya lekin RSI ne higher low.
    'bearish': price ne higher high banaya lekin RSI ne lower high. Sirf taaza swings (aakhri 25 candles mein)."""
    d = df.iloc[-lookback:]
    r = rsi_series.iloc[-lookback:]
    highs, lows = pivots(d, n)
    recent = len(d) - 25
    if len(lows) >= 2 and lows[-1][0] >= recent:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p2 < p1 and r.iloc[i2] > r.iloc[i1] + 1:
            return "bullish"
    if len(highs) >= 2 and highs[-1][0] >= recent:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        if p2 > p1 and r.iloc[i2] < r.iloc[i1] - 1:
            return "bearish"
    return None
