#!/usr/bin/env python3
"""One garment must never fill two slots (user report 2026-08-02).

The LLM was returning the same closet item as BOTH `inner` and `base` — "wear your
tee under your tee". The prompt already said inner is an undershirt and base is the
visible top; the validator only checked that ids EXIST, so nothing caught it. Same
class as plan amendment 3: validate in code, never hope in prose.

Stubs the vLLM call so this is deterministic and needs neither the network nor a
resident model. Not named test_* on purpose: it sys.exit()s at module level, which
kills pytest collection for the whole tree.
Run: python3 server/tests/check_closet_dedupe.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}  {detail}")


CLOSET = [
    {"id": "aaaaaaaa-1", "label": "white tee", "category": "base", "colors": ["white"],
     "warmth": 2, "formality": ["casual"], "waterproof": False, "availableCount": 3},
    {"id": "aaaaaaaa-2", "label": "cotton undershirt", "category": "inner", "colors": ["white"],
     "warmth": 2, "formality": ["casual"], "waterproof": False, "availableCount": 5},
    {"id": "aaaaaaaa-3", "label": "dark chinos", "category": "bottoms", "colors": ["navy"],
     "warmth": 3, "formality": ["casual"], "waterproof": False, "availableCount": 2},
]
W = {"lo": 18, "hi": 26, "feelsLo": 17, "feelsHi": 27, "morning": 19, "midday": 25,
     "evening": 21, "rain": 10, "wind": 3, "desc": "Clear", "code": 0,
     "isRain": False, "isSnow": False, "swing": 8}


def reply(picks):
    return json.dumps({"picks": picks, "bullets": ["a", "b", "c", "d", "e", "f"], "tip": "t"})


print("=" * 68)
print("closet picks: one garment, one slot")
print("=" * 68)

# ---- 1. the unit that resolves it -----------------------------------------
print("\n[1] _dedupe_picks keeps the item in the slot its CATEGORY says")
by_cat = {i["id"]: i["category"] for i in CLOSET}
out = llm._dedupe_picks(
    {"inner": "aaaaaaaa-1", "base": "aaaaaaaa-1", "mid": None, "outer": None,
     "bottoms": "aaaaaaaa-3", "footwear": None, "accessories": None}, by_cat)
check("a `base` item duplicated into inner+base stays in base",
      out["base"] == "aaaaaaaa-1" and out["inner"] is None, out)
check("unrelated slots are untouched", out["bottoms"] == "aaaaaaaa-3", out)

out = llm._dedupe_picks(
    {"inner": "aaaaaaaa-2", "base": "aaaaaaaa-2", "mid": None, "outer": None,
     "bottoms": None, "footwear": None, "accessories": None}, by_cat)
check("an `inner` item duplicated into inner+base stays in inner",
      out["inner"] == "aaaaaaaa-2" and out["base"] is None, out)

out = llm._dedupe_picks(
    {"inner": None, "base": "aaaaaaaa-3", "mid": "aaaaaaaa-3", "outer": None,
     "bottoms": None, "footwear": None, "accessories": None}, by_cat)
kept = [k for k, v in out.items() if v == "aaaaaaaa-3"]
check("category not among the duplicated slots -> first in CATEGORIES order wins",
      kept == ["base"], out)

out = llm._dedupe_picks(
    {"inner": "aaaaaaaa-2", "base": "aaaaaaaa-1", "mid": None, "outer": None,
     "bottoms": "aaaaaaaa-3", "footwear": None, "accessories": None}, by_cat)
check("a clean answer is passed through unchanged",
      out["inner"] == "aaaaaaaa-2" and out["base"] == "aaaaaaaa-1", out)

# ---- 2. the retry ----------------------------------------------------------
print("\n[2] a duplicate triggers ONE corrective retry")
calls = []


def stub(sequence):
    it = iter(sequence)

    async def _chat(messages, max_tokens, timeout=45):
        calls.append(messages[0]["content"])
        return next(it)
    return _chat


dup = {"inner": "aaaaaaaa-1", "base": "aaaaaaaa-1", "mid": None, "outer": None,
       "bottoms": "aaaaaaaa-3", "footwear": None, "accessories": None}
good = {"inner": "aaaaaaaa-2", "base": "aaaaaaaa-1", "mid": None, "outer": None,
        "bottoms": "aaaaaaaa-3", "footwear": None, "accessories": None}

llm._chat = stub([reply(dup), reply(good)])
res = asyncio.run(llm.closet_outfit(W, "man", "casual", CLOSET))
check("retried after the duplicate", len(calls) == 2, f"{len(calls)} call(s)")
check("the retry prompt names the offending id",
      "aaaaaaaa-1" in calls[1] and "more than one slot" in calls[1])
check("the corrected answer is used",
      res["picks"]["inner"] == "aaaaaaaa-2" and res["picks"]["base"] == "aaaaaaaa-1", res["picks"])

# ---- 3. a stubborn model ---------------------------------------------------
print("\n[3] if the retry ALSO duplicates, resolve it rather than lose closet advice")
calls.clear()
llm._chat = stub([reply(dup), reply(dup)])
res = asyncio.run(llm.closet_outfit(W, "man", "casual", CLOSET))
check("did not give up and return None (that would drop to generic advice)", res is not None)
check("only ONE slot keeps the item",
      res and res["picks"]["base"] == "aaaaaaaa-1" and res["picks"]["inner"] is None,
      res["picks"] if res else None)
check("no id appears twice anywhere", res is not None and (
      lambda v: len(v) == len(set(v)))([x for x in res["picks"].values() if x]))
check("stopped after the allowed 2 attempts", len(calls) == 2, f"{len(calls)}")

# ---- 4. no regression on the existing id check -----------------------------
print("\n[4] ids that aren't in the wardrobe still fail the way they did")
calls.clear()
llm._chat = stub([reply({**good, "base": "not-a-real-id"}), reply(good)])
res = asyncio.run(llm.closet_outfit(W, "man", "casual", CLOSET))
check("bogus id triggers the id retry", len(calls) == 2)
check("and the valid retry is accepted", res is not None and res["picks"]["base"] == "aaaaaaaa-1")

# ---- 5. slot/category compatibility ----------------------------------------
# The model's favourite way to dodge the duplicate rule is to demote the tee into
# `inner` and let the engine fill `base` generically — which the user reads as the
# SAME "tee under tee" complaint. Observed live 2026-08-04.
print("\n[5] an item may only fill a slot its own category allows")
check("a base tee is not an inner",
      llm._slot_mismatches({"inner": "aaaaaaaa-1", "base": None}, by_cat) == ["inner"])
check("an inner in the base slot is also wrong",
      llm._slot_mismatches({"inner": None, "base": "aaaaaaaa-2"}, by_cat) == ["base"])
check("correct placement is accepted",
      llm._slot_mismatches({"inner": "aaaaaaaa-2", "base": "aaaaaaaa-1"}, by_cat) == [])
check("null slots are not mismatches",
      llm._slot_mismatches({"inner": None, "base": None}, by_cat) == [])

MID_OUTER = CLOSET + [
    {"id": "aaaaaaaa-4", "label": "grey fleece", "category": "mid", "colors": ["grey"],
     "warmth": 4, "formality": ["casual"], "waterproof": False, "availableCount": 1}]
mo_cat = {i["id"]: i["category"] for i in MID_OUTER}
check("mid may stand in for outer (a fleece as the outer layer is real)",
      llm._slot_mismatches({"outer": "aaaaaaaa-4"}, mo_cat) == [])

print("\n[6] a slot mismatch retries, then is cleared rather than left wrong")
calls.clear()
misplaced = {"inner": "aaaaaaaa-1", "base": None, "mid": None, "outer": None,
             "bottoms": "aaaaaaaa-3", "footwear": None, "accessories": None}
llm._chat = stub([reply(misplaced), reply(good)])
res = asyncio.run(llm.closet_outfit(W, "man", "casual", CLOSET))
check("retried on the mismatch", len(calls) == 2, f"{len(calls)}")
check("the retry prompt explains the slot rule",
      "category" in calls[1] and "inner" in calls[1], calls[1][-200:] if len(calls) > 1 else "")
check("the corrected answer is used", res["picks"]["inner"] == "aaaaaaaa-2")

calls.clear()
llm._chat = stub([reply(misplaced), reply(misplaced)])
res = asyncio.run(llm.closet_outfit(W, "man", "casual", CLOSET))
check("a stubborn mismatch clears the slot (engine's generic advice fills it)",
      res is not None and res["picks"]["inner"] is None, res["picks"] if res else None)
check("the legitimate pick in the same reply survives",
      res is not None and res["picks"]["bottoms"] == "aaaaaaaa-3")

print("=" * 68)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 68)
sys.exit(1 if failed else 0)
