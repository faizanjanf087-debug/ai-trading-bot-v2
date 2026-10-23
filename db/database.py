"""SQLite connection aur schema. Baad mein Postgres par shift karna ho to sirf db/ layer badlegi."""
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'blocked')),
    muted       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    mode          TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    entry_type    TEXT NOT NULL,
    entry         REAL NOT NULL,
    sl            REAL NOT NULL,
    sl_initial    REAL NOT NULL,
    tp1           REAL NOT NULL,
    tp2           REAL NOT NULL,
    status        TEXT NOT NULL,
    score         REAL,
    reason        TEXT,
    ai_note       TEXT,
    source        TEXT NOT NULL DEFAULT 'scan',
    owner_id      INTEGER,
    created_ts    INTEGER NOT NULL,
    expires_ts    INTEGER,
    activated_ts  INTEGER,
    closed_ts     INTEGER,
    result_r      REAL,
    last_candle_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

CREATE TABLE IF NOT EXISTS signal_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    type      TEXT NOT NULL,
    price     REAL,
    ts        INTEGER NOT NULL,
    note      TEXT
);

CREATE TABLE IF NOT EXISTS signal_deliveries (
    signal_id INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    PRIMARY KEY (signal_id, user_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    price        REAL NOT NULL,
    direction    TEXT NOT NULL CHECK (direction IN ('above', 'below')),
    active       INTEGER NOT NULL DEFAULT 1,
    created_ts   INTEGER NOT NULL,
    triggered_ts INTEGER
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    ts      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);

CREATE TABLE IF NOT EXISTS chat_summary (
    user_id    INTEGER PRIMARY KEY,
    summary    TEXT NOT NULL,
    updated_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_journal (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id      INTEGER NOT NULL UNIQUE,
    created_ts     INTEGER NOT NULL,
    symbol         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    tf             TEXT,
    side           TEXT NOT NULL,
    entry_type     TEXT,
    source         TEXT,
    price          REAL,
    atr            REAL,
    rsi            REAL,
    htf_trend      TEXT,
    htf_alignment  TEXT,
    macd_cross     TEXT,
    divergence     TEXT,
    score          REAL,
    score_buy      REAL,
    score_sell     REAL,
    factors        TEXT NOT NULL DEFAULT '[]',
    ai_verdict     TEXT,
    ai_confidence  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON analysis_journal(symbol);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self):
        # Phase 1 wali purani database mein 'muted' column nahi tha
        cols = [r["name"] for r in self._conn.execute("PRAGMA table_info(users)").fetchall()]
        if "muted" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN muted INTEGER NOT NULL DEFAULT 0")

    def execute(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self):
        with self._lock:
            self._conn.close()
