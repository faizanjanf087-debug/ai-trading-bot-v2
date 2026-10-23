"""Supabase connection ki jaanch: `python -m db.check` (Replit Shell mein, DATABASE_URL Secrets mein ho)."""
import os
import sys

from config.settings import _check_database_url, mask_db_url


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL set nahi hai (Replit Secrets mein daalein).")
        return 1
    try:
        _check_database_url(url)
        from db.kv import KV
        from db.postgres import TABLES, PostgresDatabase
        db = PostgresDatabase(url)
    except Exception as e:
        print("Connect nahi hua:", mask_db_url(str(e)).splitlines()[0] if str(e) else type(e).__name__)
        return 1
    print("Connect ho gaya:", mask_db_url(url))
    print(db.query("SELECT version() AS v")[0]["v"].split(",")[0])
    for t in TABLES:
        print(f"  {t}: {db.query(f'SELECT COUNT(*) AS c FROM {t}')[0]['c']} rows")
    kv = KV(db)                                   # likhne/parhne/mitane ki chhoti jaanch
    kv.set("_check", "ok")
    ok = kv.get("_check") == "ok"
    kv.delete_prefix("_check")
    print("Likhna/parhna:", "theek" if ok else "KHARAB")
    db.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
