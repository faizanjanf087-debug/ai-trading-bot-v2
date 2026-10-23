"""Postgres (Supabase) backend. Interface SQLite wale Database jaisa hi hai: execute / query / close.

Repos (db/users.py, db/signals.py ...) wahi SQL likhte hain; yahan usay Postgres ke liye badla jata hai:
  ?                    -> %s
  INSERT OR IGNORE     -> INSERT ... ON CONFLICT DO NOTHING
  datetime('now')      -> UTC waqt ka text
  cursor.lastrowid     -> RETURNING id (jin tables mein id hai)
"""
import logging
import re
import threading
from decimal import Decimal
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "supabase" / "schema.sql"
TABLES = ["users", "signals", "signal_events", "signal_deliveries", "alerts", "chat_messages", "chat_summary",
          "kv", "analysis_journal"]
ID_TABLES = {"signals", "signal_events", "alerts", "chat_messages", "analysis_journal"}   # jin mein id column hai

_NOW_SQL = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"


def to_pg(sql: str) -> str:
    """SQLite wali SQL ko Postgres (psycopg) ke liye badlo."""
    s = sql.strip().rstrip(";").strip()
    if re.match(r"(?is)^INSERT\s+OR\s+REPLACE\b", s):
        raise ValueError("INSERT OR REPLACE support nahi, ON CONFLICT ... DO UPDATE use karein.")
    ignore = False
    if re.match(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", s):
        s = re.sub(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", s, count=1)
        ignore = True
    s = s.replace("datetime('now')", _NOW_SQL)
    s = s.replace("%", "%%").replace("?", "%s")     # SQL ke andar ka % escape, phir placeholders
    if ignore:
        s += " ON CONFLICT DO NOTHING"
    return s


def insert_table(sql: str):
    m = re.match(r"(?is)^\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", sql)
    return m.group(1).lower() if m else None


def _clean(row: dict) -> dict:
    """Postgres ka SUM/numeric Decimal deta hai; usay int/float bana do (SQLite wala behavior)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            v = int(v) if v == v.to_integral_value() else float(v)
        out[k] = v
    return out


class Result:
    """sqlite3 cursor ki tarah: lastrowid aur rowcount."""

    def __init__(self, lastrowid=None, rowcount=0):
        self.lastrowid = lastrowid
        self.rowcount = rowcount


class PostgresDatabase:
    is_postgres = True

    def __init__(self, url: str, connect=None, retry_on=None, init_schema: bool = True):
        if connect is None:
            import psycopg                      # sirf Postgres chalane par chahiye
            from psycopg.rows import dict_row

            def connect():
                return psycopg.connect(url, autocommit=True, row_factory=dict_row,
                                       prepare_threshold=None, connect_timeout=10)

            retry_on = (psycopg.OperationalError, psycopg.InterfaceError)
        self._connect_fn = connect
        self._retry_on = tuple(retry_on or ())
        self._lock = threading.RLock()
        self._conn = self._connect_fn()
        if init_schema:
            self._ensure_schema()

    def _ensure_schema(self):
        """schema.sql idempotent hai (IF NOT EXISTS), is liye har start par chalana theek hai."""
        if not SCHEMA_FILE.exists():
            log.warning("supabase/schema.sql nahi mili, tables ka bana hona farz kar raha hoon.")
            return
        with self._lock:
            self._conn.execute(SCHEMA_FILE.read_text())

    def _reconnect(self):
        try:
            self._conn.close()
        except Exception:
            pass
        self._conn = self._connect_fn()

    def _exec(self, pg_sql: str, params: tuple):
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(pg_sql, params)
                        rows = cur.fetchall() if cur.description else []
                        return rows, cur.rowcount
                except self._retry_on:
                    if attempt == 2:
                        raise
                    log.warning("Database connection toot gayi, dobara jor raha hoon.")
                    self._reconnect()

    def execute(self, sql: str, params: tuple = ()) -> Result:
        pg = to_pg(sql)
        returning = insert_table(sql) in ID_TABLES
        if returning:
            pg += " RETURNING id"
        rows, rowcount = self._exec(pg, tuple(params))
        return Result(rows[0]["id"] if returning and rows else None, rowcount)

    def query(self, sql: str, params: tuple = ()):
        rows, _ = self._exec(to_pg(sql), tuple(params))
        return [_clean(r) for r in rows]

    def export_all(self) -> dict:
        """Poora data (backup ke liye): {table: [rows]}."""
        return {t: self.query(f"SELECT * FROM {t} ORDER BY 1") for t in TABLES}

    def close(self):
        with self._lock:
            self._conn.close()
