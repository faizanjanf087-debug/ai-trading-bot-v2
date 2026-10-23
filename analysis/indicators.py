"""Technical indicators (pandas/numpy se, koi extra library nahi)."""
from typing import Optional

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(~((loss == 0) & (gain > 0)), 100.0)   # sirf upar gayi
    out = out.where(~((loss == 0) & (gain == 0)), 50.0)   # bilkul flat
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def volume_spike(df: pd.DataFrame, n: int = 20, factor: float = 1.8) -> Optional[bool]:
    """Aakhri candle ka volume average se kitna zyada hai. Forex mein volume na ho to None."""
    vol = df["volume"]
    if len(vol) < n + 1 or vol.iloc[-n - 1:].sum() == 0:
        return None
    avg = vol.iloc[-n - 1:-1].mean()
    return bool(avg > 0 and vol.iloc[-1] >= factor * avg)


def resample(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    """N candles ko jod kar higher timeframe (e.g. 5m x3 = 15m). Aakhir se gin kar, taake taaza data poora rahe."""
    if factor <= 1:
        return df
    usable = (len(df) // factor) * factor
    d = df.iloc[len(df) - usable:]
    groups = np.arange(usable) // factor
    g = d.groupby(groups)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
    })
    out.index = g.apply(lambda x: x.index[0]).values
    return out
