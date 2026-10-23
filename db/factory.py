"""DATABASE_URL ho to Supabase (Postgres), warna local SQLite."""
from config.settings import mask_db_url
from db.database import Database


def open_database(settings):
    url = getattr(settings, "database_url", "")
    if not url:
        return Database(settings.database_path)
    try:
        from db.postgres import PostgresDatabase
        return PostgresDatabase(url)
    except ImportError as e:
        raise RuntimeError("Postgres driver install nahi hai: `pip install -r requirements.txt` chalayein "
                           f"(psycopg[binary] chahiye). ({e})") from None
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        raise RuntimeError(f"Supabase database se connect nahi ho saka ({mask_db_url(first)}). DATABASE_URL, "
                           "password aur 'Session pooler' wali string check karein.") from None
