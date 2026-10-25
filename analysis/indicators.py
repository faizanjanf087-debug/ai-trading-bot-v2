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


def adx(df: pd.DataFrame, n: int = 14):
    """Wilder ADX, +DI, -DI. ADX trend ki taaqat batata hai (direction nahi): <15 range, >25 mazboot trend."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr_s = atr(df, n).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr_s
    total = (plus_di + minus_di).replace(0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / total).fillna(0.0)   # koi harkat nahi -> ADX 0 (range)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), plus_di, minus_di


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """Bollinger Bands: (middle, upper, lower)."""
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


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


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3):
    """Stochastic %K (smoothed) aur %D."""
    low_min = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    raw = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    kline = raw.rolling(smooth).mean()
    return kline, kline.rolling(d).mean()


def vwap_session(df: pd.DataFrame) -> pd.Series:
    """Har UTC din ke shuru se cumulative VWAP. Volume na ho to NaN (forex mein tick volume bharosemand nahi)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]
    day = df.index.floor("D")
    cum_pv = (typical * vol).groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def shock(df: pd.DataFrame, mult: float = 3.0, bars: int = 3, atr_n: int = 14) -> Optional[dict]:
    """Tez move (crash/spike): aakhri `bars` candles mein close ka farq ATR ke `mult` guna se zyada.
    Wapas: {'dir': 'up'|'down', 'size_atr': float} ya None."""
    if len(df) < atr_n + bars + 1:
        return None
    atr_v = float(atr(df, atr_n).iloc[-1])
    if not atr_v or atr_v != atr_v:
        return None
    move = float(df["close"].iloc[-1] - df["close"].iloc[-1 - bars])
    if abs(move) < mult * atr_v:
        return None
    return {"dir": "up" if move > 0 else "down", "size_atr": round(abs(move) / atr_v, 1)}
