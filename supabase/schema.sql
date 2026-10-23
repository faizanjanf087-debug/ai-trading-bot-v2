-- ai-trading-bot V2: Postgres (Supabase) schema.
-- Supabase Dashboard -> SQL Editor mein poora paste karke Run karein. Dobara chalane se koi nuqsan nahi (IF NOT EXISTS).
-- Column ke naam aur qisam SQLite wali schema se milte hain, taake code ka shift aasaan rahe.
-- Telegram IDs aur epoch seconds ke liye BIGINT, prices ke liye DOUBLE PRECISION.

CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'blocked')),
    muted       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'),
    updated_at  TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS signals (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    side           TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    entry_type     TEXT NOT NULL,
    entry          DOUBLE PRECISION NOT NULL,
    sl             DOUBLE PRECISION NOT NULL,
    sl_initial     DOUBLE PRECISION NOT NULL,
    tp1            DOUBLE PRECISION NOT NULL,
    tp2            DOUBLE PRECISION NOT NULL,
    status         TEXT NOT NULL,
    score          DOUBLE PRECISION,
    reason         TEXT,
    ai_note        TEXT,
    source         TEXT NOT NULL DEFAULT 'scan',
    owner_id       BIGINT,
    created_ts     BIGINT NOT NULL,
    expires_ts     BIGINT,
    activated_ts   BIGINT,
    closed_ts      BIGINT,
    result_r       DOUBLE PRECISION,
    last_candle_ts BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

CREATE TABLE IF NOT EXISTS signal_events (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    signal_id BIGINT NOT NULL,
    type      TEXT NOT NULL,
    price     DOUBLE PRECISION,
    ts        BIGINT NOT NULL,
    note      TEXT
);
CREATE INDEX IF NOT EXISTS idx_signal_events_signal ON signal_events(signal_id);

CREATE TABLE IF NOT EXISTS signal_deliveries (
    signal_id BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    PRIMARY KEY (signal_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_deliveries_user ON signal_deliveries(user_id);

CREATE TABLE IF NOT EXISTS alerts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    symbol       TEXT NOT NULL,
    price        DOUBLE PRECISION NOT NULL,
    direction    TEXT NOT NULL CHECK (direction IN ('above', 'below')),
    active       INTEGER NOT NULL DEFAULT 1,
    created_ts   BIGINT NOT NULL,
    triggered_ts BIGINT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    ts      BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);

CREATE TABLE IF NOT EXISTS chat_summary (
    user_id    BIGINT PRIMARY KEY,
    summary    TEXT NOT NULL,
    updated_ts BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_journal (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    signal_id      BIGINT NOT NULL UNIQUE,
    created_ts     BIGINT NOT NULL,
    symbol         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    tf             TEXT,
    side           TEXT NOT NULL,
    entry_type     TEXT,
    source         TEXT,
    price          DOUBLE PRECISION,
    atr            DOUBLE PRECISION,
    rsi            DOUBLE PRECISION,
    htf_trend      TEXT,
    htf_alignment  TEXT,
    macd_cross     TEXT,
    divergence     TEXT,
    score          DOUBLE PRECISION,
    score_buy      DOUBLE PRECISION,
    score_sell     DOUBLE PRECISION,
    factors        TEXT NOT NULL DEFAULT '[]',
    ai_verdict     TEXT,
    ai_confidence  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON analysis_journal(symbol);

-- Security: Row Level Security on, koi public policy nahi. Yaani Supabase ki anon/authenticated keys se
-- in tables ka data nahi khulega. Bot server-side connection string se jude ga (wo RLS se guzarta hai).
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals           ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_events     ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages     ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_summary      ENABLE ROW LEVEL SECURITY;
ALTER TABLE kv                ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_journal  ENABLE ROW LEVEL SECURITY;
