"""Regenerate golden_engine.json from the CURRENT behaviour of engine.py.

Run only when an engine change is DELIBERATE:
    python3 server/tests/gen_engine_golden.py
then review the golden diff — it is the exact blast radius of the change, and
the JS twin in app/www/index.html must be moved to match.

The grid is boundary-driven: every threshold in recommend() appears with its
value, value-1 and value+1, crossed with all genders and styles, plus a set of
weather shapes that drive the isSnow / isRain / rain / wind / code / swing
branches. Deterministic and ordered, so a regeneration diff is readable.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402

GENDERS = ("man", "woman", "other")
STYLES = ("casual", "smart", "active")

# Every threshold recommend() branches on, with neighbours on each side.
THRESHOLDS = (5, 6, 7, 8, 10, 15, 16, 18, 22, 24, 26)
TEMPS = sorted({t + d for t in THRESHOLDS for d in (-1, 0, 1)} | {-10, 0, 35})


def w_of(morning, *, hi=None, lo=None, midday=None, rain=0, wind=0, code=0, snow=False, is_rain=False, swing=None):
    hi = morning + 4 if hi is None else hi
    lo = morning if lo is None else lo
    return {
        "lo": lo, "hi": hi,
        "feelsLo": lo, "feelsHi": hi,
        "morning": morning, "midday": morning + 2 if midday is None else midday, "evening": morning + 1,
        "rain": rain, "wind": wind, "code": code,
        "isRain": is_rain, "isSnow": snow,
        "swing": (hi - lo) if swing is None else swing,
    }


# Weather shapes chosen to hit each non-temperature branch, including the
# precedence between them (snow beats rain beats temperature for outer/footwear).
SHAPES: dict[str, dict] = {
    "calm":        dict(),
    "snow":        dict(snow=True),
    "rain_flag":   dict(is_rain=True, rain=80),
    "rain_50":     dict(rain=50),
    "rain_40":     dict(rain=40),           # umbrella but not waterproof outer
    "windy":       dict(wind=8),
    "windy_rain":  dict(wind=12, rain=60),  # windproof suffix must NOT double up
    "swing":       dict(hi=30, lo=5),
    "swing_nomid": dict(hi=30, lo=5, midday=None),
    "cloudy_hot":  dict(hi=30, code=3),     # hi>=24 but code not in (0,1,2): no sunglasses
    "sunny_hot":   dict(hi=30, code=1),
}

cases = []
for t in TEMPS:
    for g in GENDERS:
        for st in STYLES:
            w = w_of(t)
            cases.append({"id": f"t{t}-{g}-{st}", "w": w, "gender": g, "style": st,
                          "want": engine.recommend(w, g, st)})

for name, kw in SHAPES.items():
    for t in (-2, 12, 20, 27):
        for g in GENDERS:
            w = w_of(t, **kw)
            cases.append({"id": f"{name}-t{t}-{g}", "w": w, "gender": g, "style": "casual",
                          "want": engine.recommend(w, g, "casual")})

# morning=None forces the lo/hi midpoint fallback path.
for lo, hi in ((0, 10), (14, 20), (24, 30)):
    w = w_of(0, lo=lo, hi=hi)
    w["morning"] = None
    cases.append({"id": f"nomorning-{lo}-{hi}", "w": w, "gender": "man", "style": "casual",
                  "want": engine.recommend(w, "man", "casual")})

offsets = []
base = {"lo": 8, "hi": 18, "feelsLo": 7, "feelsHi": 17, "morning": 10, "midday": 15, "evening": 12,
        "rain": 0, "wind": 0, "code": 0, "isRain": False, "isSnow": False, "swing": 10}
for off in (0, 0.5, 1.5, -1.5, 2, -3, 2.5):
    offsets.append({"id": f"offset{off}", "w": base, "offset": off,
                    "want": engine.apply_temp_offset(base, off)})
none_morning = dict(base, morning=None)
offsets.append({"id": "offset-none-morning", "w": none_morning, "offset": 2,
                "want": engine.apply_temp_offset(none_morning, 2)})

out = Path(__file__).parent / "golden_engine.json"
out.write_text(json.dumps({"recommend": cases, "offset": offsets}, indent=1, sort_keys=True) + "\n")
print(f"wrote {out} — {len(cases)} recommend cases, {len(offsets)} offset cases")
