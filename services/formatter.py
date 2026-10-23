"""Telegram messages ki shakal (plain text, taake escaping ka masla na ho)."""
import time
from datetime import datetime, timezone

from config.markets import SYMBOLS


def px(symbol: str, price) -> str:
    if price is None:
        return "-"
    return f"{price:.{SYMBOLS.get(symbol, {}).get('digits', 5)}f}"


def _pkt(ts: int) -> str:
    return datetime.fromtimestamp(ts + 5 * 3600, tz=timezone.utc).strftime("%d %b %H:%M PKT")


DISCLAIMER = "⚠️ Yeh financial advice nahi, sirf analysis hai. Apna risk khud manage karein."


def format_signal(s: dict) -> str:
    sym = s["symbol"]
    side = "BUY 🟢" if s["side"] == "buy" else "SELL 🔴"
    if s["entry_type"] == "LIMIT":
        kind = "LIMIT"
        entry_line = f"Entry (limit): {px(sym, s['entry'])}  (price is level par aaye to alert milega)"
    else:
        kind = "MARKET"
        entry_line = f"Entry (ab): {px(sym, s['entry'])}"
    lines = [
        f"📊 Signal #{s['id']}  {sym}  {kind} {side}  [{s['mode']}]",
        entry_line,
        f"SL: {px(sym, s['sl'])}",
        f"TP1: {px(sym, s['tp1'])}   TP2: {px(sym, s['tp2'])}",
        f"Score: {s['score']}   Status: {s['status']}",
    ]
    if s.get("reason"):
        lines.append("Wajah: " + s["reason"])
    if s.get("ai_note"):
        lines.append("🤖 AI: " + s["ai_note"])
    if s["status"] == "PENDING" and s.get("expires_ts"):
        lines.append("Valid till: " + _pkt(s["expires_ts"]))
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


EVENT_TEXT = {
    "ENTRY_HIT": "✅ Entry hit ho gayi",
    "TP1_HIT": "🎯 TP1 hit!",
    "SL_TO_BE": "🛡 SL ab entry par (breakeven)",
    "TP2_HIT": "🏆 TP2 hit! Trade band.",
    "SL_HIT": "🛑 SL hit. Trade band.",
    "BE_HIT": "➖ Breakeven par band (TP1 mil chuka tha).",
    "EXPIRED": "⌛ Signal expire (entry hui nahi).",
    "CANCELLED": "🚫 Signal cancel (price entry se door chali gayi).",
}


# Result sirf in events par dikhta hai (baqi events ke waqt signal shayad aage band ho chuka hota hai)
RESULT_EVENTS = ("TP2_HIT", "SL_HIT", "BE_HIT", "EXPIRED")


def format_event(s: dict, e: dict) -> str:
    if e["type"] == "CANCELLED":
        return (f"🚫 Signal #{s['id']} {s['symbol']} {s['side'].upper()} cancel\n"
                f"Entry {px(s['symbol'], s['entry'])} kabhi touch nahi hui, price seedha TP1 "
                f"({px(s['symbol'], s['tp1'])}) tak chali gayi.\n"
                f"Is signal mein koi trade nahi laga (na profit, na loss). Limit entry fill hone ka intezar tha.")
    text = EVENT_TEXT.get(e["type"], e["type"])
    price = f" @ {px(s['symbol'], e['price'])}" if e.get("price") is not None else ""
    out = f"{text}{price}\nSignal #{s['id']} {s['symbol']} {s['side'].upper()}"
    if e.get("note") and e["type"] in ("EXPIRED", "CANCELLED"):
        out += f"\n{e['note']}"
    if e["type"] in RESULT_EVENTS and s["status"] not in ("PENDING", "ACTIVE", "TP1") \
            and s.get("result_r") is not None:
        out += f"\nResult: {s['result_r']:+.2f}R"
    return out


def _format_entry_and_sl(s: dict, entry: dict, sl: dict) -> str:
    sym = s["symbol"]
    return (f"✅🛑 Entry hit hui @ {px(sym, entry['price'])} aur usi candle mein SL bhi hit @ {px(sym, sl['price'])}\n"
            f"Signal #{s['id']} {sym} {s['side'].upper()}\n"
            f"Result: {s['result_r']:+.2f}R")


def format_events(s: dict, events: list) -> list:
    """Ek hi batch ke events ke messages. Entry aur usi batch ka SL ek message ban jata hai."""
    out, i = [], 0
    while i < len(events):
        e = events[i]
        nxt = events[i + 1] if i + 1 < len(events) else None
        if e["type"] == "ENTRY_HIT" and nxt and nxt["type"] == "SL_HIT" and s.get("result_r") is not None:
            out.append(_format_entry_and_sl(s, e, nxt))
            i += 2
            continue
        out.append(format_event(s, e))
        i += 1
    return out


def format_signal_line(s: dict) -> str:
    res = f" | {s['result_r']:+.2f}R" if s.get("result_r") is not None and s["status"] not in ("PENDING", "ACTIVE", "TP1") else ""
    return (f"#{s['id']} {s['symbol']} {s['side'].upper()} {s['entry_type']} @ {px(s['symbol'], s['entry'])} "
            f"SL {px(s['symbol'], s['sl'])} TP1 {px(s['symbol'], s['tp1'])} | {s['status']}{res}")


def format_alert_hit(a: dict, price: float) -> str:
    return f"🔔 Alert #{a['id']}: {a['symbol']} ne {px(a['symbol'], a['price'])} {'upar cross kiya' if a['direction'] == 'above' else 'neeche cross kiya'} (price ~{px(a['symbol'], price)})"


MTF_TEXT = {"aligned_up": "teeno up", "aligned_down": "teeno down", "mixed": "mila-jula"}


def format_analysis(a: dict, setup=None) -> str:
    sym = a["symbol"]
    lines = [
        f"📈 {sym} [{a['mode']} / {a['tf']}]  Price: {px(sym, a['price'])}",
        f"Trend: {a['tf']} {'up' if a['ema_fast'] > a['ema_slow'] else 'down'} | Higher TF: {a['htf_trend']}",
        f"RSI: {a['rsi']:.0f} | MACD hist: {a['macd_hist']:+.5g} | ATR: {px(sym, a['atr'])}",
    ]
    if a.get("htf2_tf"):
        lines.append(f"Multi-TF: {a['tf']} {a.get('ltf_trend', '-')} | {a['htf_tf']} {a['htf_trend']} | "
                     f"{a['htf2_tf']} {a.get('htf2_trend', '-')} ({MTF_TEXT.get(a.get('mtf_alignment'), 'mixed')})")
    extra = []
    if a.get("adx") is not None:
        extra.append(f"ADX {a['adx']:.0f}" + (" (range)" if a.get("ranging") else " (mazboot trend)" if a["adx"] >= 25 else ""))
    if a.get("structure"):
        extra.append("Structure " + ("HH/HL" if a["structure"] == "bullish" else "LH/LL"))
    if a.get("bb_squeeze"):
        extra.append("Bollinger squeeze (breakout ka imkaan)")
    if extra:
        lines.append(" | ".join(extra))
    sup = [l for l in a["levels"] if l["price"] < a["price"]][-2:]
    res = [l for l in a["levels"] if l["price"] > a["price"]][:2]
    if sup:
        lines.append("Support: " + ", ".join(px(sym, l["price"]) for l in reversed(sup)))
    if res:
        lines.append("Resistance: " + ", ".join(px(sym, l["price"]) for l in res))
    pats = [n for n, _ in a["candles"] + a["chart_patterns"]]
    if pats:
        lines.append("Patterns: " + ", ".join(pats))
    if a["divergence"]:
        lines.append(f"RSI divergence: {a['divergence']}")
    lines.append(f"Score  Buy: {a['score_buy']}  Sell: {a['score_sell']}")
    if setup:
        lines.append(f"✅ Setup mil gaya: {setup['side'].upper()} {setup['entry_type']} @ {px(sym, setup['entry'])}")
    else:
        lines.append("Abhi koi saaf setup nahi (score kam ya RR kharab).")
    return "\n".join(lines)


def format_stats(st: dict, title: str = "Aap ke signals") -> str:
    wr = f"{st['win_rate']}%" if st["win_rate"] is not None else "-"
    return (f"📊 {title}\nBand: {st['closed']} | Wins: {st['wins']} | Losses: {st['losses']} | "
            f"Flat: {st['flat']}\nWin rate: {wr} | Net: {st['net_r']:+.2f}R")


def _grp_line(key: str, g: dict) -> str:
    wr = f"{g['win_rate']}%" if g["win_rate"] is not None else "-"
    return f"  {key}: {g['wins']}W/{g['losses']}L ({wr})  {g['net_r']:+.2f}R"


HTF_TEXT = {"with": "higher TF ke saath", "against": "higher TF ke khilaf", "flat": "higher TF flat",
            "unknown": "purane signals (journal nahi)"}
AI_TEXT = {"take": "AI ne TAKE kaha", "skip": "AI ne SKIP kaha", "none": "AI raay nahi"}


def format_report(rep: dict, title: str = "Sab signals") -> str:
    o = rep["overall"]
    if not o["closed"]:
        return f"📈 Report ({title})\nAbhi koi band signal nahi, report ke liye thora intezar karein."
    wr = f"{o['win_rate']}%" if o["win_rate"] is not None else "-"
    lines = [
        f"📈 Report ({title})",
        f"Band: {o['closed']} | Trade hui: {o['n']} | Wins: {o['wins']} | Losses: {o['losses']}",
        f"Win rate: {wr} | Net: {o['net_r']:+.2f}R",
    ]
    if o["limit_total"]:
        lines.append(f"Missed (price entry par aaye baghair TP1 tak chali gayi): {o['missed']} "
                     f"({o['missed_rate']}% limit signals)")
    if o["expired"]:
        lines.append(f"Expire (entry hui hi nahi): {o['expired']}")
    g = rep["groups"]
    for key, label, names in (("htf", "Higher timeframe", HTF_TEXT), ("ai", "AI ki raay", AI_TEXT)):
        rows = [(k, v) for k, v in g[key] if v["n"]]
        if rows:
            lines += ["", f"{label}:"] + [_grp_line(names.get(k, k), v) for k, v in rows]
    for key, label in (("symbol", "Pair"), ("mode", "Mode"), ("entry", "Entry type")):
        rows = [(k, v) for k, v in g[key] if v["n"]]
        if len(rows) > 1:
            lines += ["", f"{label}:"] + [_grp_line(k, v) for k, v in rows]
    if rep["factors"]:
        lines += ["", "Wajhein (kam az kam 2 trades):"] + [_grp_line(k, v) for k, v in rep["factors"]]
    if not rep["reliable"]:
        lines += ["", f"⚠️ Abhi sirf {o['n']} trades hain. 20 se kam par koi natija pakka nahi, isay sirf andaza samjhein."]
    return "\n".join(lines)


EVENT_SHORT = {
    "ENTRY_HIT": "Entry hit", "TP1_HIT": "TP1 hit", "SL_TO_BE": "SL -> entry", "TP2_HIT": "TP2 hit",
    "SL_HIT": "SL hit", "BE_HIT": "Breakeven", "EXPIRED": "Expire", "CANCELLED": "Cancel",
}


def format_my_signals(signals: list, events_by_id: dict) -> str:
    """Database se asli haal (open + aakhri band signals), events ke waqt ke saath."""
    if not signals:
        return "Aap ka abhi koi signal nahi. /signal likh kar naya lein."
    out = ["📋 Aap ke signals ka asli haal (database se):"]
    for s in signals:
        out.append("")
        out.append(format_signal_line(s))
        evs = events_by_id.get(s["id"], [])
        if evs:
            out.append("  " + " → ".join(f"{EVENT_SHORT.get(e['type'], e['type'])} ({_pkt(e['ts'])})" for e in evs[-4:]))
        else:
            out.append("  Abhi entry hit nahi hui (PENDING)." if s["status"] == "PENDING" else "  Koi event nahi.")
    if any(s["status"] in ("PENDING", "ACTIVE", "TP1") and SYMBOLS.get(s["symbol"], {}).get("kind") == "forex" for s in signals):
        out.append("\nNote: forex ke alerts free plan par 5-14 minute late aa sakte hain.")
    return "\n".join(out)


def _eta(seconds: float) -> str:
    if seconds < -60:
        return f"{int(-seconds // 60)} min pehle"
    if seconds < 60:
        return "abhi"
    h, m = divmod(int(seconds // 60), 60)
    return f"{h}h {m}m mein" if h else f"{m} min mein"


def format_calendar_events(events: list, now: float) -> str:
    """Bari khabrein, UTC mein. Khali list par saaf jawab."""
    from datetime import datetime, timezone

    if not events:
        return "Agle waqt mein koi bari (high-impact) khabar nahi mili."
    lines = []
    for e in events:
        when = datetime.fromtimestamp(e["ts"], timezone.utc)
        extra = ""
        if e.get("forecast") or e.get("previous"):
            extra = f" (forecast {e.get('forecast') or '-'}, pehle {e.get('previous') or '-'})"
        lines.append(f"🔴 {when:%a %d %b %H:%M} UTC | {e['currency']} | {e['title']}{extra} - {_eta(e['ts'] - now)}")
    return "\n".join(lines)


def format_news(events: list, headlines: list, sentiment, fear_greed, now: float, title: str = "News") -> str:
    parts = [f"📰 {title}", "", "Bari khabrein (agle 48 ghante):", format_calendar_events(events, now)]
    if headlines:
        parts += ["", "Headlines:"] + [f"- {h}" for h in headlines[:5]]
        if sentiment:
            parts.append(f"Headlines ka mood (lafzon se mota andaza): {sentiment[0]}")
    if fear_greed:
        parts.append(f"Crypto Fear & Greed: {fear_greed[0]} ({fear_greed[1]})")
    parts.append("\nBari khabar ke waqt spread aur slippage barh jate hain; us waqt naya trade na lena behtar hai.")
    return "\n".join(parts)
