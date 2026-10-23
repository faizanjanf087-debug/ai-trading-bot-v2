import numpy as np
import pandas as pd


def synth(n=300, seed=1, freq="5min", start="2026-01-05", base=100.0, drift=0.0, vol=0.5, volume=True):
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, n).cumsum() + np.sin(np.arange(n) / 12) * 3 + base
    o = steps
    c = np.r_[steps[1:], steps[-1] + rng.normal(0, 0.3)]
    h = np.maximum(o, c) + rng.random(n) * 0.3
    l = np.minimum(o, c) - rng.random(n) * 0.3
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": rng.random(n) * 100 if volume else 0.0}, index=idx)
