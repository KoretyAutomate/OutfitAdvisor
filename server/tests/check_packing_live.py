"""
check_packing_live.py — T1 verification for POST /packing against the LIVE server.

Not a unit test, and deliberately NOT named test_*: it exercises the real endpoint,
the real Open-Meteo calls and the real vLLM, because "ran without error" is not
verification (workspace rule). Under a test_* name pytest imported it during
collection, ran ~55s of live network, then died on its module-level sys.exit() —
which took the whole suite down with it.

Run:  python3 server/tests/check_packing_live.py   (server must be up on the tailnet IP)
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_http import request_json

BASE = "http://100.112.171.54:8787"
TODAY = dt.date.today()

# A small but realistic closet, spanning every category, with a multi-count item.
CLOSET: list[dict] = [
    {
        "id": "itm-inner-airism",
        "label": "grey airism undershirt",
        "category": "inner",
        "colors": ["grey"],
        "warmth": 1,
        "formality": ["casual", "smart"],
        "waterproof": False,
        "availableCount": 5,
    },
    {
        "id": "itm-base-white-tee",
        "label": "white v-neck tee",
        "category": "base",
        "colors": ["white"],
        "warmth": 1,
        "formality": ["casual"],
        "waterproof": False,
        "availableCount": 4,
    },
    {
        "id": "itm-base-oxford",
        "label": "blue oxford shirt",
        "category": "base",
        "colors": ["blue"],
        "warmth": 2,
        "formality": ["smart", "casual"],
        "waterproof": False,
        "availableCount": 2,
    },
    {
        "id": "itm-mid-merino",
        "label": "navy merino crew-neck",
        "category": "mid",
        "colors": ["navy"],
        "warmth": 3,
        "formality": ["smart", "casual"],
        "waterproof": False,
        "availableCount": 1,
    },
    {
        "id": "itm-outer-shell",
        "label": "black rain shell",
        "category": "outer",
        "colors": ["black"],
        "warmth": 2,
        "formality": ["casual", "active"],
        "waterproof": True,
        "availableCount": 1,
    },
    {
        "id": "itm-outer-blazer",
        "label": "charcoal wool blazer",
        "category": "outer",
        "colors": ["charcoal"],
        "warmth": 3,
        "formality": ["smart"],
        "waterproof": False,
        "availableCount": 1,
    },
    {
        "id": "itm-bot-chinos",
        "label": "grey chinos",
        "category": "bottoms",
        "colors": ["grey"],
        "warmth": 2,
        "formality": ["smart", "casual"],
        "waterproof": False,
        "availableCount": 2,
    },
    {
        "id": "itm-foot-derbies",
        "label": "brown leather derbies",
        "category": "footwear",
        "colors": ["brown"],
        "warmth": 2,
        "formality": ["smart"],
        "waterproof": False,
        "availableCount": 1,
    },
    {
        "id": "itm-foot-sneakers",
        "label": "white sneakers",
        "category": "footwear",
        "colors": ["white"],
        "warmth": 2,
        "formality": ["casual"],
        "waterproof": False,
        "availableCount": 1,
    },
]
IDS = {i["id"] for i in CLOSET}
AVAIL = {i["id"]: i["availableCount"] for i in CLOSET}

# Osaka
LAT, LON = 34.69379, 135.50107

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def post(path, body, expect=200):
    return request_json(BASE + path, body, timeout=120)


def trip(start_in, days, **kw):
    s = TODAY + dt.timedelta(days=start_in)
    body = {
        "lat": LAT,
        "lon": LON,
        "start": s.isoformat(),
        "end": (s + dt.timedelta(days=days - 1)).isoformat(),
        "type": "vacation",
        "gender": "man",
        "styles": ["casual"],
    }
    body.update(kw)
    return body


print(f"=== /packing live verification — {dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
print(f"server: {BASE}   today: {TODAY}\n")

# ---------------------------------------------------------------- health
print("[health]")
_, h = request_json(BASE + "/health", timeout=10)
check("health ok", h.get("ok") is True, h)
check("vLLM reachable", h.get("vllm") is True, h)

# ------------------------------------------------- 1. forecast + closet
print("\n[1] 4-day business trip in 3 days, closet, smart+casual  (forecast path)")
st, d = post("/packing", trip(3, 4, type="business", styles=["smart", "casual"], closet=CLOSET))
check("HTTP 200", st == 200, d)
if st == 200:
    check("mode=forecast", d["forecast"]["mode"] == "forecast", d["forecast"]["mode"])
    check("4 days returned", len(d["forecast"]["days"]) == 4, len(d["forecast"]["days"]))
    check("closetUsed=true", d["closetUsed"] is True)
    check("packed something", len(d["pack"]) > 0)
    bad = [p["id"] for p in d["pack"] if p["id"] not in IDS]
    check("every packed id is real", not bad, bad)
    over = [(p["id"], p["qty"], AVAIL.get(p["id"])) for p in d["pack"] if p["qty"] > AVAIL.get(p["id"], 0)]
    check("no qty exceeds availableCount", not over, over)
    percat: dict[str, int] = {}
    for p in d["pack"]:
        percat[p["category"]] = percat.get(p["category"], 0) + 1
    check("<=2 pack entries per category", all(v <= 2 for v in percat.values()), percat)
    check("packing_text non-empty", bool(d["packing_text"].strip()))
    check("text has bullets", "•" in d["packing_text"])
    check("NOT truncated mid-JSON (tip or >=4 bullets)", d["packing_text"].count("•") >= 4, d["packing_text"][:120])
    # a smart+casual business trip should pack from BOTH registers
    packed_forms = {f for p in d["pack"] for i in CLOSET if i["id"] == p["id"] for f in i["formality"]}
    check("packs across both registers", {"smart", "casual"} <= packed_forms, packed_forms)
    print("\n--- packing_text ---")
    print(d["packing_text"])
    print("--- pack ---")
    for p in d["pack"]:
        print(f"   {p['qty']}x {p['label']:28s} ({p['category']:11s}) {p['why']}")
    print(f"--- gaps: {d['gaps']}")

# ---------------------------------------------------- 2. normals path
print("\n[2] 4-day trip 60 days out  (normals path — beyond the 15-day horizon)")
st, d = post("/packing", trip(60, 4, closet=CLOSET))
check("HTTP 200", st == 200, d)
if st == 200:
    s = d["forecast"]["summary"]
    check("mode=normals", s["mode"] == "normals", s["mode"])
    # Was >=5 and it silently passed a normal built from HALF the years, because
    # Open-Meteo 429'd the concurrent fan-out. Demand the full 10.
    check("all 10 archive years used (no silent 429 degradation)", s.get("yearsUsed", 0) == 10, s.get("yearsUsed"))
    check("carries the extremes, not just means", "loMinEver" in s and "hiMaxEver" in s, list(s))
    check("4 days returned", len(d["forecast"]["days"]) == 4)
    check("closetUsed=true", d["closetUsed"] is True)
    print(
        f"   typical {s['loMin']}-{s['hiMax']}C, "
        f"ever {s['loMinEver']}..{s['hiMaxEver']}C, "
        f"{s['rainDays']}/{s['nDays']} wet, {s['yearsUsed']} yrs"
    )

# ------------------------------------------- 3. no closet -> honest generic
print("\n[3] trip with NO closet  (generic fallback must be honest)")
st, d = post("/packing", trip(3, 3))
check("HTTP 200", st == 200, d)
if st == 200:
    check("closetUsed=false", d["closetUsed"] is False)
    check("pack empty", d["pack"] == [])
    check("still returns advice", bool(d["packing_text"].strip()))

# --------------------------------- 4. capacity shortfall must be surfaced
print("\n[4] 12-day trip, only 2 base items  (shortfall must surface as a gap)")
tiny = [i for i in CLOSET if i["category"] in ("base", "bottoms", "footwear")]
tiny = [dict(i, availableCount=1) for i in tiny]
st, d = post("/packing", trip(2, 12, closet=tiny))
check("HTTP 200", st == 200, d)
if st == 200:
    check("closetUsed=true", d["closetUsed"] is True)
    laundry = [g for g in d["gaps"] if "laundry" in g["need"].lower()]
    check("shortfall surfaced as a gap (not silently truncated)", bool(laundry), d["gaps"])
    # This closet has ZERO inner items: the gap must say buy/register, never
    # "plan a laundry day" (laundry can't produce items you don't own).
    inner_gaps = [g for g in d["gaps"] if g["category"] == "inner"]
    check("inner-less closet surfaces an inner gap", bool(inner_gaps), d["gaps"])
    check("zero-have gap does not say laundry", all("laundry" not in g["need"].lower() for g in inner_gaps), inner_gaps)
    print(f"   gaps: {d['gaps']}")

# ----------------------------------------------- 5. validation gates
print("\n[5] input validation gates")
st, _ = post("/packing", trip(-3, 2))
check("past trip rejected (422)", st == 422, st)
bad = trip(3, 2)
bad["end"] = (TODAY + dt.timedelta(days=1)).isoformat()
st, _ = post("/packing", bad)
check("end-before-start rejected (422)", st == 422, st)
st, _ = post("/packing", trip(3, 40))
check("trip >30 days rejected (422)", st == 422, st)
bad = trip(3, 2)
bad["styles"] = ["formal"]
st, _ = post("/packing", bad)
check("unknown style rejected (422)", st == 422, st)
bad = trip(3, 2)
bad["type"] = "honeymoon"
st, _ = post("/packing", bad)
check("unknown trip type rejected (422)", st == 422, st)

# ------------------------------------------------- 6. straddling horizon
print("\n[6] trip starting in 13 days, 10 days long  (straddles the horizon)")
st, d = post("/packing", trip(13, 10, closet=CLOSET))
check("HTTP 200 (clamped, not 400)", st == 200, d)
if st == 200:
    check("marked truncated", d["trip"]["truncated"] is True, d["trip"])
    check("clamped to the horizon", len(d["forecast"]["days"]) < 10, len(d["forecast"]["days"]))

print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)
