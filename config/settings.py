"""Settings environment variables se load hoti hain (Replit Secrets ya .env)."""
import os
import re
from dataclasses import dataclass, field
from typing import List

from config.markets import DEFAULT_WATCHLIST, SYMBOLS


def _bool(v: str, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    owner_id: int
    database_path: str = "data/bot.db"
    database_url: str = ""              # Supabase/Postgres ki connection string (sirf Replit Secrets mein)
    twelvedata_key: str = ""
    deepseek_key: str = ""
    deepseek_model: str = "deepseek-chat"
    watchlist: List[str] = field(default_factory=lambda: list(DEFAULT_WATCHLIST))
    # Scanner
    enable_scanner: bool = True
    forex_modes: List[str] = field(default_factory=lambda: ["scalp"])
    crypto_modes: List[str] = field(default_factory=lambda: ["scalp", "intraday"])
    forex_scan_minutes: int = 10
    crypto_scan_minutes: int = 5
    session_utc: str = "07-20"          # forex scan sirf in ghanton mein (UTC)
    min_score: float = 6.0
    counter_trend_extra: float = 1.0    # higher TF ke khilaf signal ke liye min_score se itna zyada score chahiye
    signal_cooldown_minutes: int = 60   # same symbol par naya signal itni der baad
    # AI
    ai_veto: bool = False               # True: AI "skip" kahe to signal na bheja jaye
    # Twelve Data free plan
    td_per_minute: int = 8
    td_per_day: int = 800
    td_monitor_reserve: int = 250       # in credits ko sirf open signals ki monitoring use karegi


def mask_db_url(url: str) -> str:
    """Log ke liye: password chhupa do. postgresql://user:PASSWORD@host/db -> postgresql://user:***@host/db"""
    return re.sub(r"(://[^:/@]+:).*@", r"\1***@", url or "")


def _check_database_url(url: str) -> str:
    if not url:
        return ""
    if "[YOUR-PASSWORD]" in url or "[PASSWORD]" in url.upper():
        raise RuntimeError("DATABASE_URL mein password ka placeholder baqi hai, apna asli database password daalein.")
    if not url.lower().startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL 'postgresql://' se shuru honi chahiye (Supabase -> Connect -> Session pooler "
                           "wali string). Project ka https:// wala URL yahan nahi chalta.")
    return url


def _csv(v: str, default: list) -> list:
    items = [x.strip() for x in (v or "").split(",") if x.strip()]
    return items or default


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    owner = env.get("OWNER_ID", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN set nahi hai (Replit Secrets mein daalein).")
    if not owner.isdigit():
        raise RuntimeError("OWNER_ID set nahi hai ya number nahi hai (@userinfobot se apni ID lein).")

    watch = [s.upper() for s in _csv(env.get("WATCHLIST"), list(DEFAULT_WATCHLIST))]
    watch = [s for s in watch if s in SYMBOLS]

    def num(name, default, cast=int):
        try:
            return cast(env.get(name, "").strip() or default)
        except ValueError:
            raise RuntimeError(f"{name} number hona chahiye.")

    return Settings(
        telegram_token=token,
        owner_id=int(owner),
        database_path=env.get("DATABASE_PATH", "data/bot.db").strip() or "data/bot.db",
        database_url=_check_database_url(env.get("DATABASE_URL", "").strip()),
        twelvedata_key=env.get("TWELVEDATA_API_KEY", "").strip(),
        deepseek_key=env.get("DEEPSEEK_API_KEY", "").strip(),
        deepseek_model=env.get("DEEPSEEK_MODEL", "").strip() or "deepseek-chat",
        watchlist=watch or list(DEFAULT_WATCHLIST),
        enable_scanner=_bool(env.get("ENABLE_SCANNER"), True),
        forex_modes=_csv(env.get("FOREX_MODES"), ["scalp"]),
        crypto_modes=_csv(env.get("CRYPTO_MODES"), ["scalp", "intraday"]),
        forex_scan_minutes=num("FOREX_SCAN_MINUTES", 10),
        crypto_scan_minutes=num("CRYPTO_SCAN_MINUTES", 5),
        session_utc=env.get("SESSION_UTC", "").strip() or "07-20",
        min_score=num("MIN_SCORE", 6.0, float),
        counter_trend_extra=num("COUNTER_TREND_EXTRA", 1.0, float),
        signal_cooldown_minutes=num("SIGNAL_COOLDOWN_MINUTES", 60),
        ai_veto=_bool(env.get("AI_VETO"), False),
        td_per_minute=num("TD_PER_MINUTE", 8),
        td_per_day=num("TD_PER_DAY", 800),
        td_monitor_reserve=num("TD_MONITOR_RESERVE", 250),
    )
