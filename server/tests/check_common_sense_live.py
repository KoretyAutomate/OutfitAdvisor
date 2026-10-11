#!/usr/bin/env python3
"""Saved test days: would a person wear what the REAL model picks? (user, 2026-10-11)

"Style check needs to have a common sense as no human would wear such outfit ...
Shouldn't we approach it with the prompt?" A prompt is judged by what the model
does with it, which a stub cannot show — so every prompt change runs these days
against the resident model before it ships, and every odd outfit the wearer
reports becomes one more day here.

In-process (closet.closet_outfit against vLLM on :8000), so it checks the code in
this checkout, not whatever the service happens to be running.

Not named test_*: it needs vLLM resident, and it sys.exit()s.
Run: python3 server/tests/check_common_sense_live.py [runs per day]
"""
import asyncio
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import closet
import style
from picks import Prefs

TOPS = {"t_shirt", "polo", "tank", "blouse", "shirt"}


def g(iid, label, kind, roles, warmth, **kw):
    """`kind` is "group/type", e.g. "tops/polo"."""
    group, typ = kind.split("/")
    return {"id": f"itm-{iid}", "label": label, "category": roles[0], "group": group, "type": typ,
            "roles": list(roles), "colors": ["navy"], "warmth": warmth, "formality": ["casual"],
            "waterproof": False, "availableCount": 1, **kw}


def day(morning, rain=0):
    return {"date": "2026-10-11", "code": 61 if rain >= 50 else 2, "desc": "Rain" if rain >= 50 else "Cloudy",
            "lo": morning, "hi": morning + 5, "swing": 5, "feelsLo": morning, "feelsHi": morning + 5,
            "rain": rain, "wind": 3, "morning": morning, "midday": morning + 4, "evening": morning + 2,
            "isSnow": False, "isRain": rain >= 50}


POLO = g("navypolo", "navy polo shirt", "tops/polo", ("base", "mid", "outer"), 2)
KNIT_POLO = g("knitpolo", "grey knit polo", "tops/polo", ("base", "mid", "outer"), 3, colors=["grey"])
TEE = g("whitetee", "white crew-neck T-shirt", "tops/t_shirt", ("base",), 1, colors=["white"])
OXFORD = g("oxford", "blue oxford shirt", "tops/shirt", ("base", "mid", "outer"), 2, colors=["blue"])
INNER = g("vinner", "grey v-neck inner", "underwear/undershirt", ("inner",), 1, colors=["grey"])
SWEATER = g("sweater", "navy v-neck sweater", "tops/sweater", ("base", "mid", "outer"), 4)
CARDI = g("cardi", "charcoal cardigan", "tops/cardigan", ("mid", "outer"), 3, colors=["charcoal"])
HOODIE = g("hoodie", "grey hoodie", "tops/hoodie", ("mid", "outer"), 3, colors=["grey"])
JACKET = g("jacket", "olive field jacket", "outerwear/jacket", ("outer",), 3, colors=["olive"])
RAIN = g("rainjkt", "black rain jacket", "outerwear/rainwear", ("outer",), 2, colors=["black"], waterproof=True)
PANTS = g("drawstr", "beige drawstring pants", "bottoms/trousers", ("bottoms",), 3, colors=["beige"])
JEANS = g("jeans", "blue jeans", "bottoms/jeans", ("bottoms",), 3, colors=["blue"])
SNEAK = g("sneaker", "white sneakers", "footwear/sneakers", ("footwear",), 2, colors=["white"])
LOAFER = g("loafer", "brown loafers", "footwear/loafers", ("footwear",), 2, colors=["brown"])

# name: (weather, wardrobe). Add the wearer's next odd outfit here.
DAYS = {
    # 2026-10-11, the morning push: a polo over a polo.
    "polo-on-polo, 10C": (day(10), [POLO, KNIT_POLO, TEE, CARDI, PANTS, JEANS, SNEAK]),
    # 2026-10-11, 07:55: no shoes on a 93% rain day. Rain gear is NOT required.
    "rain 93%, 15C": (day(15, 93), [INNER, POLO, OXFORD, SWEATER, RAIN, PANTS, JEANS, SNEAK, LOAFER]),
    "tee on a cold morning, 6C": (day(6), [TEE, OXFORD, HOODIE, JACKET, JEANS, SNEAK]),
    "mild, many tops, 18C": (day(18), [TEE, POLO, KNIT_POLO, OXFORD, CARDI, JEANS, PANTS, SNEAK, LOAFER]),
}


def nonsense(picks: dict, by_id: dict, owned: list) -> list[str]:
    """What no person would wear. The EVAL's oracle — never used to dress anyone."""
    torso = [by_id[picks[c]] for c in ("base", "mid", "outer") if picks.get(c)]
    out = []
    if sum(1 for i in torso if i["type"] in TOPS - {"shirt"}) > 1 or \
            sum(1 for i in torso if i["type"] in TOPS) > 2:
        out.append("tops stacked: " + " + ".join(i["label"] for i in torso))
    kinds = [i["type"] for i in torso]
    if len(kinds) != len(set(kinds)):
        out.append("two of a kind: " + ",".join(kinds))
    if not picks.get("footwear") and any(i["category"] == "footwear" for i in owned):
        out.append("no shoes")
    if not picks.get("bottoms") and (by_id.get(picks.get("base")) or {}).get("group") != "onepiece":
        out.append("no trousers")
    if not picks.get("base"):
        out.append("no top")
    return out


async def main(runs: int) -> int:
    logging.basicConfig(level=logging.INFO, format="    %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    bad = total = 0
    for name, (w, wardrobe) in DAYS.items():
        by_id = {i["id"]: i for i in wardrobe}
        print(f"\n== {name}")
        for n in range(runs):
            t = time.monotonic()
            prefs = replace(Prefs(), look=style.Look("casual", "man"))
            r = await closet.closet_outfit(w, "man", "casual", wardrobe, prefs)
            total += 1
            if r is None:
                bad += 1
                print(f"  run {n + 1}: NO OUTFIT")
                continue
            worn = {c: by_id[i]["label"] for c, i in r["picks"].items() if i}
            wrong = nonsense(r["picks"], by_id, wardrobe)
            bad += bool(wrong)
            print(f"  run {n + 1} ({time.monotonic() - t:.0f}s): {'FAIL ' + '; '.join(wrong) if wrong else 'ok'}"
                  f"  {worn}")
    print(f"\n{total - bad}/{total} outfits a person would wear")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)))
