#!/usr/bin/env python3
"""Does the wearer's own sentence produce a rule that actually FIRES? (2026-09-05)

The unit tests next door prove the refusal and the repair. They cannot prove the
thing the user complained about, which is a claim about what a 122B model returns
for a particular English sentence — and that is precisely where this broke: every
field of the rule it produced was legal, the restatement was word-perfect, and the
rule could not fire for any outfit.

So this asks the REAL /rule endpoint, then runs the answer through the REAL
violations() against the outfit the wearer kept being given.

Not named test_* on purpose: it needs vLLM resident and sys.exit()s.
Run: python3 server/tests/check_rule_live.py
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rules  # noqa: E402  (path set above; see tests/conftest.py for the same trick)

BASE = "http://100.112.171.54:8787"

BY_ITEM = {
    "u1": {"label": "white undershirt", "type": "undershirt", "group": "underwear",
           "colors": ["white"]},
    "t1": {"label": "white crew-neck tee", "type": "t_shirt", "group": "tops",
           "colors": ["white"]},
    "j1": {"label": "blue jeans", "type": "jeans", "group": "bottoms",
           "colors": ["blue"]},
}
WORN = {"inner": "u1", "base": "t1", "mid": None, "outer": None,
        "bottoms": "j1", "footwear": None, "accessories": None}

# The wearer's own words, and the variants they are likely to reach for. Case is
# included deliberately: before the fix, the same sentence in lower case parsed
# correctly and in the user's capitalisation did not.
PHRASINGS = [
    "no inner with white Crew-neck T-shirt",
    "no inner with white crew-neck t-shirt",
    "No inner with white Crew-neck T-shirt",
    "don't wear an undershirt under my white crew neck t-shirt",
    "white V-neck inner + white T shall be banned",
    "never an undershirt with the white tee",
]


def _garment(iid, label, cat, kind, group, colors):
    return {"id": iid, "label": label, "category": cat, "type": kind, "group": group,
            "roles": [cat], "colors": colors, "warmth": 2,
            "formality": ["casual"], "waterproof": False, "availableCount": 3}


# The wardrobe the complaint is about: an undershirt, the white crew-neck tee, and
# just enough else to make a real outfit.
CLOSET = [
    _garment("g-under-01", "white undershirt", "inner", "undershirt", "underwear",
             ["white"]),
    _garment("g-tee-0001", "white crew-neck tee", "base", "t_shirt", "tops", ["white"]),
    _garment("g-jean-001", "blue jeans", "bottoms", "jeans", "bottoms", ["blue"]),
    _garment("g-shoe-001", "sneakers", "footwear", "sneakers", "footwear", ["white"]),
]


def end_to_end(rule: dict) -> int:
    """The whole morning, not just the parse: does /advice actually honour it?

    This is the only check that answers the wearer's question. The parse can be
    right and the enforcement still hand back the wrong garment — which is exactly
    what happened once the rule started firing: it took away the TEE.
    """
    body = {"lat": 40.7, "lon": -74.0, "gender": "man", "style": "casual", "day": 0,
            "closet": CLOSET, "closetOnly": True,
            "rules": [{"kind": rule["kind"], "a": rule["a"], "b": rule.get("b"),
                       "id": "rl-live", "text": "no inner with white crew-neck tee"}]}
    r = httpx.post(BASE + "/advice", json=body,
                   headers={"X-OA-Client": "probe/rule"}, timeout=180)
    r.raise_for_status()
    d = r.json()
    picks = d.get("picks") or {}
    lbl = {i["id"]: i["label"] for i in CLOSET}
    print("\n" + "=" * 68)
    print("END TO END — POST /advice with that rule and that wardrobe")
    print(f"   closetUsed={d.get('closetUsed')}")
    for slot in ("inner", "base", "mid", "outer", "bottoms", "footwear"):
        print(f"   {slot:12} {lbl.get(picks.get(slot), '-') if picks.get(slot) else '-'}")
    print(f"   missing={d.get('missing')}")
    bad = []
    if not d.get("closetUsed"):
        bad.append("the closet was not used at all")
    if picks.get("inner"):
        bad.append("the undershirt is STILL there — the rule was ignored")
    if picks.get("base") != "g-tee-0001":
        bad.append("the white tee was taken away instead of the undershirt")
    if "inner" in (d.get("missing") or []):
        bad.append("a banned combination was recorded as a wardrobe gap")
    for b in bad:
        print(f"[FAIL] {b}")
    if not bad:
        print("[PASS] the tee stayed, the undershirt went, and no gap was recorded")
    return 0 if not bad else 1


def main() -> int:
    passed = failed = 0
    for text in PHRASINGS:
        r = httpx.post(BASE + "/rule", json={"text": text}, timeout=120)
        if r.status_code != 200:
            print(f"[FAIL] {text!r}\n       HTTP {r.status_code} — not turned into "
                  f"a rule at all")
            failed += 1
            continue
        rule = r.json()
        fires = rules.violations([rule], WORN, BY_ITEM)
        if fires:
            print(f"[PASS] {text!r}\n       -> {rule['kind']} a={rule['a']} "
                  f"b={rule.get('b')}\n       fires on the outfit, blaming "
                  f"{fires[0]['slot']}: {fires[0]['why']}")
            passed += 1
        else:
            print(f"[FAIL] {text!r}\n       -> {rule['kind']} a={rule['a']} "
                  f"b={rule.get('b')}\n       restated {rule.get('restated')!r}\n"
                  f"       but does NOT fire on white undershirt + white tee")
            failed += 1
    print("=" * 68)
    print(f"RESULT: {passed} passed, {failed} failed")
    if failed:
        return 1
    # Whatever the wearer's own sentence parsed to is what gets driven through a
    # real generation — not a hand-written rule that happens to work.
    first = httpx.post(BASE + "/rule", json={"text": PHRASINGS[0]}, timeout=120).json()
    return end_to_end(first)


if __name__ == "__main__":
    sys.exit(main())
