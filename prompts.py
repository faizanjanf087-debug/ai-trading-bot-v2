"""AI ko dene wale prompts. AI ko sirf diye gaye numbers par bharosa karna hai, khud prices nahi banani."""
import json

SYSTEM_PROMPT = """Aap ek trading assistant hain jo Forex (XAUUSD, EURUSD...) aur Crypto (BTC, ETH, SOL) \
par scalping/intraday analysis mein madad karta hai.
Qaidey:
- Sirf diye gaye data (indicators, levels, signals, news) par bharosa karein. Koi price ya fact khud mat banayein.
- Kabhi profit ki guarantee mat dein. Risk management (SL, chhota lot size) zaroor yaad dilayein.
- User jis zubaan mein likhe (Roman Urdu / English) usi mein jawab dein. Jawab chhota aur saaf rakhein.
- Agar data na ho to saaf kahein ke data abhi available nahi, aur user ko kahein ke asli signal ke liye \
/signal <pair> (jaise /signal XAUUSD) ya /analyze <pair> command use kare.
- Aap financial advisor nahi hain; yeh sirf analysis hai."""


def _compact(analysis: dict) -> dict:
    a = analysis
    return {
        "symbol": a["symbol"], "timeframe": a["tf"], "price": a["price"], "atr": a["atr"],
        "ema20_above_ema50": a["ema_fast"] > a["ema_slow"], "higher_tf_trend": a["htf_trend"],
        "rsi": round(a["rsi"], 1), "macd_hist": a["macd_hist"], "macd_cross": a["macd_cross"],
        "rsi_divergence": a["divergence"], "volume_spike": a["volume_spike"],
        "patterns": [n for n, _ in a["candles"] + a["chart_patterns"]],
        "levels": [{"price": round(l["price"], 5), "touches": l["touches"]} for l in a["levels"]],
        "score_buy": a["score_buy"], "score_sell": a["score_sell"],
    }


def signal_review_prompt(analysis: dict, setup: dict, news_text: str) -> list:
    payload = {
        "analysis": _compact(analysis),
        "proposed_setup": {k: setup[k] for k in ("side", "entry_type", "entry", "sl", "tp1", "tp2", "reasons")},
    }
    user = (
        "Is signal ka review karein. Sirf JSON mein jawab dein, is format mein:\n"
        '{"verdict": "take" ya "skip", "confidence": 0-100, "comment": "1-2 line, Roman Urdu mein"}\n\n'
        f"Data:\n{json.dumps(payload, default=str)}\n\n{news_text or 'News data available nahi.'}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def analysis_prompt(analysis: dict, setup, news_text: str) -> list:
    payload = {"analysis": _compact(analysis), "setup": setup}
    user = (
        "Is market ka chhota analysis dein (4-6 lines): trend, key levels, kya dekhna hai, risk. "
        f"Data:\n{json.dumps(payload, default=str)}\n\n{news_text or ''}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def summary_prompt(old_summary: str, messages: list) -> list:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    user = (
        "Is purani baat-cheet ka chhota summary banayein (max 8 lines): user ki pasand, pairs, "
        "faislay, zaroori baatein.\n"
        f"Pehle ka summary: {old_summary or 'koi nahi'}\n\nNayi baat-cheet:\n{convo}"
    )
    return [{"role": "system", "content": "Aap conversation summarizer hain."}, {"role": "user", "content": user}]
