"""Signal ki wajahon (reasons) ko stable naam dena, taake journal mein ginti ho sake.

"5m trend up (EMA20>EMA50)" aur "15m trend up (EMA20>EMA50)" dono ek hi factor "ltf_trend_up" ban jate hain.
"Near support 4068.4 (2 touches)" -> "near_support" (numbers hata diye jate hain).
"""
import re


def factor_key(reason: str) -> str:
    s = (reason or "").lower().strip()
    s = re.sub(r"^\d+\s*[mh]\s+", "ltf ", s)               # "5m trend up" -> "ltf trend up"
    s = re.sub(r"\(.*?\)", " ", s)                         # (brackets) hatao
    s = re.sub(r"\d+(\.\d+)?(-\d+(\.\d+)?)?%?", " ", s)   # numbers aur ranges hatao
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "_")


def factor_keys(reasons) -> list:
    """Reasons ki list -> sorted, duplicate-free factor keys."""
    return sorted({k for k in (factor_key(r) for r in (reasons or [])) if k})


def htf_alignment(side: str, htf_trend) -> str:
    """Signal higher timeframe trend ke 'with', 'against' hai, ya trend 'flat' hai."""
    if htf_trend not in ("up", "down"):
        return "flat"
    return "with" if (side == "buy") == (htf_trend == "up") else "against"
