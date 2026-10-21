from rapidfuzz import fuzz

def score_records(a: dict, b: dict) -> float:
    weights = {"name": .45, "phone": .25, "email": .15, "address": .15}
    total = 0.0; used = 0.0
    for key, weight in weights.items():
        av, bv = str(a.get(key) or "").strip().lower(), str(b.get(key) or "").strip().lower()
        if av and bv:
            total += (100 if av == bv else fuzz.token_set_ratio(av, bv)) * weight
            used += weight
    return round(total / used, 2) if used else 0.0

def should_compare(a: dict, b: dict) -> bool:
    for field in ("phone", "email", "gst_number"):
        if a.get(field) and b.get(field) and str(a[field]).lower() == str(b[field]).lower(): return True
    aa, bb = str(a.get("name") or "").lower(), str(b.get("name") or "").lower()
    return bool(aa and bb and aa[:1] == bb[:1])

def merge_records(a: dict, b: dict) -> dict:
    return {key: (a.get(key) if a.get(key) not in (None, "") else b.get(key)) for key in set(a) | set(b)}
