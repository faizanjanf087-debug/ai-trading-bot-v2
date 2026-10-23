# AI Trading Bot (Telegram)

Forex (XAUUSD, EURUSD, GBPUSD, USDJPY...) aur Crypto (BTC, ETH, SOL) ke liye Telegram signals bot.
Scalping aur intraday. DeepSeek AI, signal tracking, alerts aur memory ke saath.

**Sirf signals** - bot khud trade nahi lagata. Yeh financial advice nahi hai, aur koi strategy munafa
guarantee nahi karti. Pehle `backtest` aur chhote risk se parkhein.

## Kya karta hai
- **User approval:** naya user `/start` kare -> owner ko Approve/Reject buttons.
- **Analysis:** RSI, MACD, EMA, ATR, volume, Support/Resistance, Fibonacci, RSI divergence,
  candlestick patterns (Hammer, Engulfing, Morning/Evening Star, Doji...), chart patterns
  (Double Top/Bottom, Range Breakout), higher-timeframe trend. Sab ka confluence **score**.
- **Signals:** LIMIT ya MARKET entry, SL, TP1, TP2 (ATR par based). Scanner khud watchlist scan karta hai.
- **Signal tracking:** `PENDING -> ACTIVE -> TP1 -> TP2 / SL / BE`, ya `EXPIRED / CANCELLED`.
  Har badlaav par alert: **entry hit, TP1, TP2, SL**. Har signal ka status aur result (R mein) database mein.
- **Price alerts:** `/alert XAUUSD 2650`.
- **AI (DeepSeek):** free chat (memory ke saath), `/analyze` par raay, aur scanner ke signals ka review
  (optional veto). AI ko sirf numbers/news text jata hai (chart image nahi).
- **Memory:** chat history + summary, user ke open signals aur performance AI ko context mein milte hain.
- **News/sentiment:** RSS headlines + Crypto Fear & Greed (fail-safe; na chalein to bot chalta rehta hai).
- **Backtest:** `python -m backtest.runner XAUUSD scalp`

## Setup (Replit)
1. GitHub se **Import from GitHub**.
2. **Tools -> Secrets** mein daalein (kabhi GitHub/chat mein nahi):

   | Secret | Kahan se |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | @BotFather -> /newbot |
   | `OWNER_ID` | @userinfobot |
   | `TWELVEDATA_API_KEY` | twelvedata.com (forex/gold ke liye) |
   | `DEEPSEEK_API_KEY` | platform.deepseek.com |

   Baqi optional settings `.env.example` mein hain.
3. Replit par Run button / `.replit` ka `uv run python main.py` istemal karein; dependencies project environment mein resolve hongi. System Python par global `pip install` ya `pip uninstall` na chalayein.
4. 24/7 chalane ke liye Replit **Deployment** (Reserved VM / background worker) chahiye; sirf Run button
   band hone par bot ruk jata hai. Hosting ke credits Agent credits se alag hain.

## Twelve Data free plan (8/minute, 800/din)
Bot credits ka hisaab rakhta hai (`data/budget.py`):
- Candles cache hoti hain; entry timeframe ki sirf nayi candle band hone par dobara fetch.
- Higher timeframe alag fetch nahi hota, entry candles se banta hai (credit bachta hai).
- Forex scan sirf `SESSION_UTC` (default 07-20 UTC) mein, `FOREX_SCAN_MINUTES` (default 10) ke waqfe se.
- `TD_MONITOR_RESERVE` (250) credits sirf open signals/alerts ki monitoring ke liye bachte hain.
- Monitoring 1-minute candles (aakhri 15) check karti hai, is liye poll ke beech ki touch miss nahi hoti,
  lekin forex mein **alert 5 se 14 minute tak late** aa sakta hai (credits ke hisaab se). Crypto ~30 second.
  Scalping mein tez alert chahiye to Twelve Data ka paid plan lein.
- Crypto (BTC/ETH/SOL) Kraken ke free public API se aata hai, is par credits nahi lagte.

## Commands
**Sab approved users:** `/signal <pair> [scalp|intraday]`, `/analyze <pair>`, `/signals`, `/history`, `/stats`, `/report`,
`/alert <pair> <price>`, `/alerts`, `/delalert <id>`, `/watchlist`, `/mute`, `/unmute`, `/forget`, `/ping`.
Seedha sawal likhne par AI jawab deta hai.
**Owner:** `/users`, `/approve <id>`, `/block <id>`, `/watch add|remove <pair>`, `/status`, `/backup`.

## Signal ke usool (lifecycle)
- Ek candle mein SL aur TP dono touch hon to **SL pehle** maana jata hai (ehtiyat).
- Entry wali candle mein sirf SL dekha jata hai.
- TP1 hit par SL entry par (breakeven) aa jata hai. Result: 50% TP1 + 50% TP2 maan kar R mein.
- Entry se pehle price TP1 tak chali jaye to signal CANCELLED; `pending_bars` ke baad EXPIRED.

## Database
Abhi SQLite (`data/bot.db`). **Replit Deployment mein local file redeploy par mit sakti hai**, is liye
owner `/backup` se waqfe waqfe copy le. Aage chal kar Postgres par shift karna hai to sirf `db/` badlega.

## Structure
```
main.py            wiring + Telegram app
config/            settings (env), markets (symbols, modes)
bot/               Telegram handlers, notifier
services/          approval, signal lifecycle, signal service, chat, formatter, watchlist
analysis/          indicators, levels (S/R, Fib), patterns, divergence, signal engine
data/              Twelve Data, Kraken, credit budget, cache, news, sessions
ai/                DeepSeek client, prompts, memory
monitor/           price watcher (entry/TP/SL/alerts), scanner
backtest/          backtest runner
db/                SQLite schema aur repositories
tests/             python -m unittest discover -s tests
```

## Maloom hadood
- Rule-based score peshgoi nahi hai; backtest karke `MIN_SCORE` aur strategy tune karein.
- Backtest mein spread/slippage shamil nahi.
- Twelve Data par XAU/USD free plan mein chalta hai ya nahi, pehle apni key se `/analyze XAUUSD` se check karein.
- Telegram handlers asli `python-telegram-bot` ke saath pehli baar Replit par chalenge; baqi logic tests se verify hai.


## V2.0 (pehla hissa)

- **Analysis journal:** har signal ke waqt ka snapshot (score, wajhein, higher TF, RSI/ATR, AI ki raay) `analysis_journal`
  table mein save hota hai. Nateeja (win/loss/cancel) `signals` table se join hota hai.
- **`/report`:** owner ko sab signals ka, baqi users ko apna hisaab: higher TF ke saath/khilaf, AI TAKE/SKIP, pair, mode,
  entry type, har wajah (factor) ki win-rate, aur "missed" signals (price entry par aaye baghair TP1 tak chali gayi).
  20 se kam trades par report khud tanbeeh deti hai ke natija pakka nahi.
- **Counter-trend rule:** higher timeframe ke KHILAF signal ke liye `MIN_SCORE` se `COUNTER_TREND_EXTRA` (default 1.0)
  zyada score chahiye. `0` karne par purana behavior wapas.
- **Alert fix:** entry aur usi candle ka SL ab ek message mein aate hain; "Result" sirf aakhri event par dikhta hai.
- Naya environment variable: `COUNTER_TREND_EXTRA` (optional).

### Database (Supabase)

- Supabase mein tables banane ke liye `supabase/schema.sql` SQL Editor mein chalayein (9 tables, Row Level Security on).
- `DATABASE_URL` Replit Secrets mein daalein (format `.env.example` mein). Code ab ise parhta hai aur galat format par
  saaf error deta hai; log mein password hamesha `***` dikhta hai.
- `DATABASE_URL` set ho to bot Supabase (Postgres) use karta hai, khali ho to purani SQLite. Start par `schema.sql`
  khud chal jati hai (dobara chalane se koi nuqsan nahi). Connection na bane to bot saaf error de kar rukta hai,
  chup chaap SQLite par nahi girta.
- Jaanch: Replit Shell mein `python -m db.check` (connect, 9 tables ki ginti, likhna/parhna).
- `/backup` Supabase par poora data JSON file mein bhejta hai (SQLite par database file).

### Sawal samajhna (intent router, `services/intents.py`)

Har text message pehle pehchana jata hai ke user kya chahta hai:

| Kisam | Misal | Bot kya karta hai |
|---|---|---|
| stats | "total status batao", "mera record", "win rate" | database se asli report (AI ka andaza nahi) |
| status | "tp hit howa?", "jo signal diya uska kya hua" | database se signals ka haal |
| signal | "gold ka signal do", "koi signal do intraday" | asli, tracked signal |
| emotion | "bohat loss ho gaya", "pareshan hun", "loss recover karna hai" | AI se baat, narmi aur risk ki yaad-dehani ke hint ke saath, naya signal nahi |
| help | "help", "kaise use karun" (chhote message) | commands ki list |
| pending | owner: "koi naya user aya?" | pending users ki list |
| chat | baqi sab | AI se baat (memory, signals aur live analysis ke saath) |

Faisla lafzon (keywords) par hota hai, sirf Roman Urdu/English mein. Koi message galat jagah jaye to uski misal
`tests/test_intents.py` mein daal kar rule theek kar sakte hain.

## V2.1 (multi-timeframe aur zyada technical analysis)

- **Teen timeframes:** entry TF + do higher TF, sab entry candles se bante hain (koi extra fetch ya credit nahi).
  Scalp: 5m -> 15m -> 1h. Intraday: 15m -> 1h -> 4h. Ab zyada candles li jati hain (scalp 700, intraday 720; Kraken ki
  hadd 720 hai), kyunke Twelve Data credit request par lagta hai, candles ki ginti par nahi.
- **Top timeframe trend:** 1h/4h ka trend (EMA9/EMA21, kam az kam 30 candles) score mein +1 deta hai. Teeno TF ek taraf
  hon to "Multi-timeframe aligned" ka +0.5. Data kam ho to top TF "flat" rehta hai.
- **ADX (trend ki taaqat):** 25 se upar mazboot trend (+0.5, +DI/-DI ki taraf). 15 se neeche market "range" maani jati hai
  aur signal ke liye `MIN_SCORE` se 0.5 zyada score chahiye (`RANGING_EXTRA`, `analysis/signal_engine.py`).
- **Market structure:** aakhri do swing highs/lows se HH/HL (bullish) ya LH/LL (bearish), +1.
- **Bollinger Bands:** band ke kinare par RSI ki tasdeeq ke saath +0.5. Squeeze (band tang) sirf `/analyze` mein dikhta hai.
- `/analyze` mein ab "Multi-TF", ADX, Structure aur squeeze ki line aati hai, aur AI ko bhi yeh fields milte hain.
- Naye factors (jaise `top_timeframe_trend_up`, `market_structure_bullish`) khud-ba-khud `/report` ke factor win-rate
  mein ginay jayenge; database mein koi change nahi.

**Zaroori:** yeh sab naye rules abhi backtest/live data par parkhe nahi gaye. Thresholds (15, 25, 0.5) shuruaati andaze hain;
pehle `python -m backtest.runner XAUUSD scalp` aur `/report` se dekhein ke inse nateeje behtar hue ya nahi.
Higher timeframe candles clock ke hisaab se nahi, entry ki aakhri N candles jor kar bante hain (purana tareeqa).

## V2.2 (fundamental: khabrein)

- **Economic calendar** (`data/calendar.py`): bari (high-impact) khabrein, currency ke hisaab se (XAUUSD/BTC -> USD,
  EURUSD -> EUR+USD...). Source ek free weekly JSON feed hai; `CALENDAR_URL` se badal sakte hain. Cache 1 ghanta; source
  band ho to purana data chalta hai aur bot nahi rukta.
- **News blackout:** bari khabar se `NEWS_BLACKOUT_BEFORE_MIN` (30) pehle aur `NEWS_BLACKOUT_AFTER_MIN` (15) baad tak
  **scanner auto signal nahi banata** (credit bhi bachta hai). Aap khud `/signal` maangein to signal milta hai, saath mein
  khabar ki tanbeeh.
- **`/news [pair]`** (ya "news batao", "btc news", "nfp kab hai"): agle 48 ghante ki bari khabrein, headlines, headlines
  ka mota mood (lafzon se, sirf ishara) aur crypto ke liye Fear & Greed. Koi AI nahi, sab data source se.
- **Owner `/event add 2026-10-29 18:00 USD FOMC rate decision`** (waqt UTC), `/event list`, `/event clear`: agar free feed
  na chale ya koi khabar usme na ho, to khud daal dein. Yeh bhi blackout mein ginti hai.
- AI ko chat/analysis/signal review mein upcoming khabrein aur headline mood bhi milte hain.

## V2.3 (psychology aur discipline)

`services/discipline.py` aap ke **apne signals ke record** se (database, AI ka andaza nahi) dekhta hai:
- lagatar loss (`LOSS_STREAK_WARN`, default 3), pichle 24 ghante ka R (`DAILY_LOSS_LIMIT_R`, default 3),
  pichle 24 ghante ke signals (`MAX_SIGNALS_PER_DAY`, default 6), aur loss ke 30 minute ke andar naya signal (revenge-trade).
- `/signal` se pehle yeh tanbeehein aati hain; **bot signal rokta nahi**, faisla aap ka hai.
- `/discipline` (ya "mera discipline kaisa hai") poori halat dikhata hai.
- Jazbati baat par AI ko aap ki asli halat (streak, 24h ka R) milti hai, taake tasalli hisaab ke saath ho.
- Aap ke khud ke signals se ginta hai; aap broker par jo trade lete hain, bot unhein nahi dekhta.

## V2.4 (sticker, voice, image)

- **Sticker:** Telegram har sticker ke saath uska emoji bhejta hai; bot usi se mood samajhta hai (koi AI ya download nahi).
  Udaas/ghussa: narmi + risk ki yaad-dehani. Khush/jashn: chhota jawab + overconfidence se ehtiyat. Na-maloom sticker par khamoshi.
- **Voice:** voice note -> text (`STT_API_KEY`, default Groq Whisper, koi bhi OpenAI-compatible service chalti hai) -> wahi
  intent router. Bot pehle likh kar dikhata hai ke usne kya suna. `VOICE_MAX_SECONDS` (60) se lambi voice nahi leta.
  Urdu likhai mein aaya text keywords se nahi pehchana jata (router Roman Urdu/English ke liye hai), wo seedha AI chat ko jata hai.
- **Image:** chart ka screenshot (photo ya file) -> Claude vision (`ANTHROPIC_API_KEY`, `VISION_MODEL`, default Haiku) ->
  observations AI chat ko extra hint ki tarah milte hain. Tasveer se parhe levels andaze hain aur galat ho sakte hain;
  bot ke apne indicators zyada bharosemand hain.
- **Kharcha/hifazat:** `MEDIA_DAILY_LIMIT` (20) har user ki roz ki voice+image hadd (memory mein, restart par reset).
  Awaaz aur tasveer sirf parhne ke liye teesri party service par jati hai; bot unhein save nahi karta, sirf text yaad rakhta hai.
  Pehli baar user ko yeh bata diya jata hai. Key khali ho to wo feature band rehta hai aur user ko saaf bata diya jata hai.

### Abhi tak parkha nahi gaya
Calendar feed ka URL aur Groq/Anthropic ke endpoints yahan se (bina internet) chala kar dekhe nahi ja sake; unka format
mere tests mein nakli jawab se check hua hai. Telegram handlers nakli `telegram` module ke saath test hue hain, asli
`python-telegram-bot` ke saath nahi. Pehli baar Replit par har cheez ek ek karke try karein: `/news`, `/discipline`,
ek sticker, ek voice note, ek chart screenshot.
