"""Signal ki zindagi: PENDING -> ACTIVE -> TP1 -> TP2 / SL / BE, ya EXPIRED / CANCELLED.

Yeh pure function hai (database ya Telegram nahi), isliye aasani se test aur backtest hota hai.

Ehtiyat ke usool (jab ek hi candle mein kai cheezein touch hon):
- Entry wali candle mein sirf SL check hota hai (TP agle candle se).
- Ek candle mein SL aur TP dono touch hon to SL pehle maana jata hai.
"""
from typing import List, Tuple

OPEN = ("PENDING", "ACTIVE", "TP1")


def _r(sig: dict, price: float) -> float:
    """price ko R (risk ke multiple) mein badlo."""
    risk = abs(sig["entry"] - sig["sl_initial"])
    sgn = 1 if sig["side"] == "buy" else -1
    return sgn * (price - sig["entry"]) / risk if risk else 0.0


def result_r(sig: dict, outcome: str) -> float:
    """50% TP1 par, 50% TP2 par band hone ka andaza."""
    r1 = _r(sig, sig["tp1"])
    r2 = _r(sig, sig["tp2"])
    if outcome == "TP2":
        return round(0.5 * r1 + 0.5 * r2, 2)
    if outcome == "BE":      # TP1 ke baad SL entry par laga tha
        return round(0.5 * r1, 2)
    if outcome == "SL":
        return -1.0
    return 0.0


def evaluate(sig: dict, candles: List[Tuple[int, float, float, float, float]], now: int,
             breakeven_after_tp1: bool = True):
    """candles: [(open_ts, o, h, l, c)] purane se naye. Wapas: (updates dict, events list).

    sig mein yeh chahiye: side, entry, sl, sl_initial, tp1, tp2, status, expires_ts, last_candle_ts.
    """
    s = dict(sig)
    events: List[dict] = []
    if s["status"] not in OPEN:
        return s, events
    buy = s["side"] == "buy"
    last_ts = s["last_candle_ts"]

    def ev(type_, price, ts, note=""):
        events.append({"type": type_, "price": price, "ts": ts, "note": note})

    def close(status, outcome, price, ts):
        s["status"] = status
        s["closed_ts"] = ts
        s["result_r"] = result_r(s, outcome) if outcome else 0.0
        ev(status if status != "TP2" else "TP2_HIT", price, ts)

    for ts, o, h, l, c in candles:
        if ts < last_ts:
            continue                    # purani candle pehle hi dekh chuke
        last_ts = max(last_ts, ts)

        if s["status"] == "PENDING":
            if s.get("expires_ts") and ts >= s["expires_ts"]:
                s["status"], s["closed_ts"], s["result_r"] = "EXPIRED", ts, 0.0
                ev("EXPIRED", None, ts, "Entry hui hi nahi, waqt khatam.")
                break
            touched = l <= s["entry"] if buy else h >= s["entry"]
            if touched:
                s["status"], s["activated_ts"] = "ACTIVE", ts
                ev("ENTRY_HIT", s["entry"], ts)
                # entry wali candle mein sirf SL
                if (l <= s["sl"]) if buy else (h >= s["sl"]):
                    s["status"], s["closed_ts"], s["result_r"] = "SL", ts, -1.0
                    ev("SL_HIT", s["sl"], ts)
                    break
                continue
            ran_away = h >= s["tp1"] if buy else l <= s["tp1"]
            if ran_away:
                s["status"], s["closed_ts"], s["result_r"] = "CANCELLED", ts, 0.0
                ev("CANCELLED", None, ts, "Price entry par aaye baghair TP1 tak chali gayi.")
                break
            continue

        # ACTIVE ya TP1
        sl_hit = (l <= s["sl"]) if buy else (h >= s["sl"])
        if sl_hit:
            if s["status"] == "TP1" and abs(s["sl"] - s["entry"]) < 1e-12:
                close("BE", "BE", s["sl"], ts)
                events[-1]["type"] = "BE_HIT"
            else:
                close("SL", "SL", s["sl"], ts)
                events[-1]["type"] = "SL_HIT"
            break
        entry_candle = s.get("activated_ts") == ts   # entry wali candle mein TP nahi dekhte
        if entry_candle:
            continue
        if s["status"] == "ACTIVE" and ((h >= s["tp1"]) if buy else (l <= s["tp1"])):
            s["status"] = "TP1"
            ev("TP1_HIT", s["tp1"], ts)
            if breakeven_after_tp1:
                s["sl"] = s["entry"]
                ev("SL_TO_BE", s["entry"], ts, "SL entry par move kar diya.")
        if s["status"] == "TP1" and ((h >= s["tp2"]) if buy else (l <= s["tp2"])):
            close("TP2", "TP2", s["tp2"], ts)
            break

    # Koi candle na aaye tab bhi pending signal expire ho sakta hai
    if s["status"] == "PENDING" and s.get("expires_ts") and now >= s["expires_ts"]:
        s["status"], s["closed_ts"], s["result_r"] = "EXPIRED", now, 0.0
        ev("EXPIRED", None, now, "Entry hui hi nahi, waqt khatam.")

    s["last_candle_ts"] = last_ts
    return s, events
