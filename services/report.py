"""Band signals ke journal rows se hisaab: win-rate kis cheez ke saath kaisi rahi.

Yeh sirf ginti hai, peshgoi nahi. Kam trades par nateeja pakka nahi hota (MIN_RELIABLE).
"""
from typing import Dict, List

MIN_RELIABLE = 20      # is se kam faislay wali trades par report mein tanbeeh aati hai
TOP_FACTORS = 8


def _new() -> dict:
    return {"wins": 0, "losses": 0, "net_r": 0.0}


def _add(b: dict, r) -> None:
    r = r or 0.0
    if r > 0:
        b["wins"] += 1
    elif r < 0:
        b["losses"] += 1
    else:
        return
    b["net_r"] += r


def _finish(b: dict) -> dict:
    n = b["wins"] + b["losses"]
    return {"n": n, "wins": b["wins"], "losses": b["losses"], "net_r": round(b["net_r"], 2),
            "win_rate": round(100 * b["wins"] / n, 1) if n else None}


def build(rows: List[dict]) -> dict:
    overall = _new()
    groups: Dict[str, Dict[str, dict]] = {"htf": {}, "ai": {}, "symbol": {}, "mode": {}, "entry": {}}
    factors: Dict[str, dict] = {}
    missed = expired = limit_total = 0

    for r in rows:
        status, res = r["status"], r.get("result_r")
        if status == "CANCELLED":
            missed += 1
        elif status == "EXPIRED":
            expired += 1
        if r.get("entry_type") == "LIMIT":
            limit_total += 1
        _add(overall, res)
        keys = {
            "htf": r.get("htf_alignment") or "unknown",
            "ai": r.get("ai_verdict") or "none",
            "symbol": r["symbol"], "mode": r["mode"], "entry": r.get("entry_type") or "?",
        }
        for g, k in keys.items():
            _add(groups[g].setdefault(k, _new()), res)
        for f in r.get("factors", []):
            _add(factors.setdefault(f, _new()), res)

    fin = _finish(overall)
    fin.update(closed=len(rows), missed=missed, expired=expired, limit_total=limit_total,
               missed_rate=round(100 * missed / limit_total, 1) if limit_total else None)
    out_groups = {g: sorted(((k, _finish(b)) for k, b in d.items()), key=lambda kv: -kv[1]["n"])
                  for g, d in groups.items()}
    out_factors = sorted(((k, _finish(b)) for k, b in factors.items()), key=lambda kv: (-kv[1]["n"], kv[0]))
    out_factors = [kv for kv in out_factors if kv[1]["n"] >= 2][:TOP_FACTORS]
    return {"overall": fin, "groups": out_groups, "factors": out_factors,
            "reliable": fin["n"] >= MIN_RELIABLE}
