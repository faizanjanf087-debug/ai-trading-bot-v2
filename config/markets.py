"""Symbols aur trading modes. Naya pair add karna ho to bas SYMBOLS mein ek line jodein."""
from typing import Optional

SYMBOLS = {
    # Forex / Gold: Twelve Data
    "XAUUSD": dict(provider="twelvedata", code="XAU/USD", kind="forex", digits=2),
    "EURUSD": dict(provider="twelvedata", code="EUR/USD", kind="forex", digits=5),
    "GBPUSD": dict(provider="twelvedata", code="GBP/USD", kind="forex", digits=5),
    "USDJPY": dict(provider="twelvedata", code="USD/JPY", kind="forex", digits=3),
    "GBPJPY": dict(provider="twelvedata", code="GBP/JPY", kind="forex", digits=3),
    "AUDUSD": dict(provider="twelvedata", code="AUD/USD", kind="forex", digits=5),
    "USDCAD": dict(provider="twelvedata", code="USD/CAD", kind="forex", digits=5),
    # Crypto: Kraken (free, US servers se bhi chalta hai)
    "BTCUSD": dict(provider="kraken", code="XBTUSD", kind="crypto", digits=2),
    "ETHUSD": dict(provider="kraken", code="ETHUSD", kind="crypto", digits=2),
    "SOLUSD": dict(provider="kraken", code="SOLUSD", kind="crypto", digits=3),
}

DEFAULT_WATCHLIST = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "ETHUSD", "SOLUSD"]

ALIASES = {
    "gold": "XAUUSD", "xau": "XAUUSD", "sona": "XAUUSD",
    "btc": "BTCUSD", "bitcoin": "BTCUSD", "btcusdt": "BTCUSD",
    "eth": "ETHUSD", "ethereum": "ETHUSD", "ethusdt": "ETHUSD",
    "sol": "SOLUSD", "solana": "SOLUSD", "solusdt": "SOLUSD",
    "euro": "EURUSD", "eur": "EURUSD", "cable": "GBPUSD", "gbp": "GBPUSD",
    "yen": "USDJPY", "jpy": "USDJPY",
    "xauusdt": "XAUUSD", "goldusd": "XAUUSD", "xausd": "XAUUSD", "xaus": "XAUUSD",
}

# tf: entry timeframe. htf_factor / htf2_factor: entry candles ko jod kar do higher timeframes banti hain
# (alag fetch nahi hota, is liye Twelve Data ka credit bachta hai; credit request par lagta hai, candles ki
# ginti par nahi, is liye zyada candles lene ka koi extra kharcha nahi).
#   scalp:    5m entry -> 15m (x3) -> 1h (x12)
#   intraday: 15m entry -> 1h (x4) -> 4h (x16)
# core_bars: S/R levels sirf itni aakhri candles se (purane levels bekaar na hon). Kraken ek baar mein max 720 deta hai.
MODES = {
    "scalp": dict(tf="5m", tf_seconds=300, htf_factor=3, htf2_factor=12, pending_bars=24,
                  td_interval="5min", kraken_interval=5, outputsize=700, core_bars=250),
    "intraday": dict(tf="15m", tf_seconds=900, htf_factor=4, htf2_factor=16, pending_bars=24,
                     td_interval="15min", kraken_interval=15, outputsize=720, core_bars=300),
}


def _within_one_edit(a: str, b: str) -> bool:
    """Kya a aur b mein sirf ek harf ka farq hai (ghalat/kam/zyada harf)?"""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def resolve_symbol(text: str) -> Optional[str]:
    """'xauusd', 'XAU/USD', 'gold', 'btc' aur chhoti galtiyan (jaise 'Xausd') pehchanta hai."""
    if not text:
        return None
    t = text.strip().lower().replace("/", "").replace("-", "").replace("_", "")
    if t.upper() in SYMBOLS:
        return t.upper()
    if t in ALIASES:
        return ALIASES[t]
    if len(t) >= 6:   # chhote alfaaz par fuzzy nahi, warna aam lafz galat pair ban jayenge
        close = [sym for sym in SYMBOLS if _within_one_edit(t.upper(), sym)]
        if len(close) == 1:
            return close[0]
    return None


def find_symbols_in_text(text: str, limit: int = 2) -> list:
    """Free chat mein se symbols dhoondna (jaise 'gold ka kya scene hai')."""
    import re

    found = []
    for word in re.findall(r"[A-Za-z/_-]+", text or ""):
        sym = resolve_symbol(word)
        if sym and sym not in found:
            found.append(sym)
        if len(found) >= limit:
            break
    return found
