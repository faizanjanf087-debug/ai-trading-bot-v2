"""Common cheezein: errors, candles DataFrame banana, HTTP helper."""
import pandas as pd


class DataError(Exception):
    """Data provider ne error diya ya data theek nahi tha."""


class BudgetExhausted(DataError):
    """Twelve Data ke free credits (minute/day) khatam."""


COLUMNS = ["open", "high", "low", "close", "volume"]


def make_df(rows) -> pd.DataFrame:
    """rows: [(epoch_seconds, open, high, low, close, volume), ...] -> UTC-indexed DataFrame."""
    if not rows:
        raise DataError("Khali candles aayin.")
    df = pd.DataFrame(rows, columns=["ts"] + COLUMNS)
    df["ts"] = pd.to_numeric(df["ts"])
    for c in COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0.0)
    df = df.drop_duplicates("ts").sort_values("ts")
    df.index = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.drop(columns=["ts"])
    if df.empty:
        raise DataError("Candles parse nahi ho sakin.")
    return df


def default_http_get(url: str, params: dict):
    import requests

    resp = requests.get(url, params=params, timeout=20)
    if resp.status_code >= 400:
        raise DataError(f"HTTP {resp.status_code} from {url.split('?')[0]}")
    return resp.json()


def closed_only(df: pd.DataFrame, tf_seconds: int, now: float) -> pd.DataFrame:
    """Aakhri adhoori (abhi chal rahi) candle hata do."""
    if df.empty:
        return df
    last_open = df.index[-1].timestamp()
    if last_open + tf_seconds > now:
        return df.iloc[:-1]
    return df
