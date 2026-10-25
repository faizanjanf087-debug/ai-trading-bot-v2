"""Error ko samajh kar ek saaf hint dena, taake logs mein wajah aur hal dono nazar aayein.

Bot ke bahar se aane wale common errors (Telegram token, do instances, network, SSL, library) ke liye
ek chhoti Roman Urdu hint. Pehchan na ho to None, aur asli error log mein hi rehta hai.
"""
from typing import Optional

HINTS = {
    "conflict": (
        "Do bot instances ek sath chal rahe hain (Telegram Conflict). Ek band karein: "
        "pkill -f \"[m]ain.py\"; sleep 2; python main.py"
    ),
    "token": (
        "TELEGRAM_BOT_TOKEN galat hai ya revoke ho chuka hai. @BotFather se naya token lein aur "
        "Replit Secrets mein TELEGRAM_BOT_TOKEN update karein."
    ),
    "ssl": (
        "SSL certificate ka masla. certifi install hona chahiye: "
        "python -m pip install -r requirements.txt --break-system-packages"
    ),
    "network": (
        "Telegram tak network nahi pohanch raha (timeout/connection). Thori der baad dobara; "
        "agar baar baar ho to Replit ka internet ya Telegram ki reachability check karein."
    ),
    "library": (
        "Library missing hai. Ye chalayein: python -m pip install -r requirements.txt --break-system-packages"
    ),
    "unauthorized": (
        "Telegram ne request reject ki (Unauthorized). Bot token check karein."
    ),
}


def hint_for(exc: Optional[BaseException]) -> Optional[str]:
    """Exception ke liye hint ka matn, ya None."""
    if exc is None:
        return None
    # Naam se pehchan: telegram library ke error classes (Conflict, InvalidToken...) ka naam
    name = type(exc).__name__
    if name == "Conflict":
        return HINTS["conflict"]
    if name == "InvalidToken":
        return HINTS["token"]
    if name == "Unauthorized":
        return HINTS["unauthorized"]
    if name in ("NetworkError", "TimedOut"):
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text:
            return HINTS["ssl"]
        return HINTS["network"]
    if isinstance(exc, ImportError):
        return HINTS["library"]
    if "CERTIFICATE_VERIFY_FAILED" in str(exc):
        return HINTS["ssl"]
    return None


def describe(exc: Optional[BaseException]) -> str:
    """Log line: 'ErrorType: message' + hint (agar ho)."""
    if exc is None:
        return "unknown error"
    base = f"{type(exc).__name__}: {exc}"
    h = hint_for(exc)
    return f"{base} | HINT: {h}" if h else base
