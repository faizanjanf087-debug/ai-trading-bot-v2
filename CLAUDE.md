# CLAUDE.md — ai-trading-bot-v2

Yeh file Claude ke liye project ki hidayat hai. Pehle yeh parhein, phir kaam shuru karein.
Pehli baat: `README.md` mein V2.0 se V2.4 tak ki tafseel hai. Yahan sirf kaam ke usool aur ahem jagahen hain.

## Project kya hai
Telegram signals bot (v2). Forex (XAUUSD, EURUSD, GBPUSD, USDJPY...) aur crypto (BTCUSD, ETHUSD, SOLUSD).
Scalping aur intraday. **Sirf signals aur analysis.** Bot khud trade nahi lagata.
Owner ek Telegram user hai (`OWNER_ID`). Naye users owner ki approval se access paate hain.
Database: SQLite (local) ya Supabase/Postgres (`DATABASE_URL`). Replit par chalta hai (free plan), code GitHub par.

## Zaruri usool
- **Financial advice nahi.** Har signal ke saath disclaimer. Profit ki guarantee kabhi nahi.
- **Secrets code/Git mein kabhi nahi.** Sirf Replit Secrets / env. `.env` gitignore hai. `DATABASE_URL` ka password logs mein `mask_db_url` se chhupta hai, us ko mat todein.
- **Bot token logs mein na aaye.** httpx/httpcore logging `WARNING` par hai. Isay mat badlain.
- **TLS verification band na karein.** Telegram requests `certifi` ka CA bundle use karti hain (`main.py`).
- **Lifecycle badlne se pehle tests chalayein.** Ek candle mein SL aur TP dono aayein to SL pehle maana jata hai.
- **Twelve Data free plan (8 credits/minute, 800/day).** Forex candle fetch = 1 credit. `data/budget.py` ka hisaab na todein. Crypto (Kraken) par credits nahi.
- Scanner aur monitor ek hi `MarketData` cache use karte hain. Cache ke bina loop mein fetch na karein.
- **Supabase tables par RLS on hai** (`supabase/schema.sql`). Public policy na banayein.
- **Owner-only aur approved-only guards** (`require_owner`, `require_approved` in `bot/handlers.py`) har naye command par lagayein. Naya handler bina guard ke na ho.
- Voice aur chart image ki roz ki hadd `MediaService` mein hai. Is ko bypass na karein.
- Voice/image handlers `ENABLE_MEDIA` (default `false`) ke peeche hain. Abhi API keys nahi, is liye band hain.

## Folder structure
```
main.py            wiring: container, handlers register, background tasks (watcher, scanner)
config/            settings.py (env), markets.py (SYMBOLS, MODES, aliases, typo matching)
bot/               handlers.py (Telegram commands + media), notifier.py
services/          approval, lifecycle (pure state machine), signal_service, chat_service,
                   analysis_service (run / run_fresh), discipline, media, report, formatter,
                   intents (text ka matlab), watchlist, container
analysis/          indicators, levels, patterns, divergence, factors, signal_engine
data/              providers (Twelve Data / Kraken), market_data (cache), budget, sessions,
                   news, calendar, base
monitor/           price_watcher (open signals + alerts), scanner (signal dhoondna + AI review)
ai/                deepseek_client, prompts, memory, speech (STT), vision (chart image)
db/                sqlite + postgres backends (factory.py), repos: users, signals, alerts, chat,
                   kv, journal; check.py (diagnostic)
supabase/          schema.sql (Supabase par ek dafa chalana)
backtest/          runner.py
tests/             unittest (200+ tests); helpers.py mein synthetic data
```

## Ahem files aur kaam
- `services/lifecycle.py`: PENDING → ACTIVE → TP1 → TP2/SL/BE, EXPIRED, CANCELLED. Pure function.
- `analysis/signal_engine.py`: `analyze()` score; `build_setup()` entry/SL/TP (ATR, RR 1.5/2.5); higher-TF filter; counter-trend ke liye extra score (`COUNTER_TREND_EXTRA`).
- `services/analysis_service.py`: `run()` band candles par; `run_fresh()` signal bhejne se pehle taaza 1m price check karta hai.
- `services/discipline.py`: loss streak, roz ka loss limit, roz ke max signals.
- `services/report.py` aur `db/journal.py`: analysis journal aur `/report` (win-rate by factor).
- `services/intents.py`: `classify()` — "signal" (naya), "status" (purane ka haal), "chat" (AI).
- `data/calendar.py`: economic events (`/event`), `ENABLE_CALENDAR` se on/off.
- `db/factory.py`: `DATABASE_URL` ho to Postgres, warna SQLite.

## Commands (Telegram)
Sab approved: `/signal`, `/analyze`, `/signals`, `/history`, `/stats`, `/report`, `/alert`, `/alerts`, `/delalert`,
`/watchlist`, `/news`, `/discipline`, `/mute`, `/unmute`, `/forget`, `/ping`, `/help`.
Owner: `/users`, `/pending`, `/approve`, `/block`, `/watch add|remove`, `/status`, `/backup`, `/event`.
Seedha text: "signal" → naya signal; "tp hit howa" → database se asli status; chart ki tasveer → vision; voice → STT; baaki → AI chat.

## Commands (development)
```
python -m unittest discover -s tests -v     # tests
python main.py                              # chalana (Replit Shell mein)
python -m backtest.runner XAUUSD scalp      # backtest (credits lagte hain)
python -m db.check                          # database ki halat (Supabase)
```
Dependencies: sirf `requirements.txt`. `pyproject.toml` ab nahi hai.
Replit par sirf **ek** instance. Do chal gaye to Telegram `Conflict` error deta hai. Restart: `pkill -f "[m]ain.py"; python main.py`

## Kaam ka tareeqa
1. Pehle samjhein, phir chhoti tabdeeli. Har change ke saath test.
2. `python -m unittest discover -s tests` pass hona zaroori hai push se pehle.
3. Commit message ke neeche attribution lines rakhein (Claude-Session wali).
4. Replit Agent ko kaam na dein jab tak user na kahe, credits lagte hain. Changes Git pull se aayein.
5. `git reset --hard` tabhi, jab user kahe. Replit ki `.replit` aur deps Replit khud badal deta hai.
6. GitHub Actions workflows nahi hain. Naya workflow user ki manzoori ke baghair na banayein (purana `organize-project` workflow hata diya gaya tha, kyunke woh poora root mita sakta tha).

## Jo abhi khule hain
- V2 ke Postgres, calendar ka asli API par test abhi tak nahi hua. Voice (STT) aur chart vision band hain (`ENABLE_MEDIA=false`), API keys aane par test hogi (README: "abhi tak parkha nahi gaya").
- Intraday: 15m entry + 4-candle HTF join. 1H/4H fresh data nahi. Aage ka faisla user ke saath.
- AI jawab mein Markdown (`**`) Telegram par raw dikh sakta hai.
- Free Twelve Data plan par forex alerts 5–14 minute late ho sakte hain.
- Telegram par `/analyze` aur `/signal` ka argument order sakht hai (`/analyze XAUUSD intraday`).

## Bot ke user se baat karne ka andaz
Roman Urdu / English. Chhota aur saaf. Signal ke saath SL aur chhota lot size yaad dilayein.
