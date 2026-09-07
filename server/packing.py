"""Trip packing arithmetic and repairs (2026-09-07).

A 15-day trip came back with two pairs of bottoms. The prompt caps the model at
two pack entries per category (a shape bound against mid-JSON truncation), the
count rule wanted five, and nothing in code closed the gap — so the bound became
the answer. This module holds what the packing route needs to be honest without
trusting the model to count: how many of a category a trip needs, a top-up that
fills the list from what the wardrobe has, wording for a real shortfall, whether a
trip involves a travel day, and validation of the model's first-days plan.

Split out of app.py, which sits at the line ceiling.
"""
import logging
import math

import scale
from vocab import CATEGORIES

log = logging.getLogger("outfit.llm")

# Only inner, base and bottoms scale with the trip's length; you re-wear a coat.
SCALING = ("inner", "base", "bottoms")

# From this far away a trip starts and ends in a cabin: a flight, or a long train.
# Under it you drive or ride an hour and step out dressed for the destination.
TRAVEL_KM = 300

# How many of the first mornings the model is asked to lay out.
PLAN_DAYS = 3


def needed(category: str, n_days: int) -> int:
    """How many of a category a trip actually needs, given its length."""
    if category in ("inner", "base"):
        return n_days + 1
    if category == "bottoms":
        return max(1, -(-n_days // 3))  # ceil(n/3)
    return 1


def is_travel(km: float | None) -> bool:
    return km is not None and km >= TRAVEL_KM


def suits(item: dict, cat: str, lo: float | None, hi: float | None) -> bool:
    """Is this garment wearable on SOME day of the trip?

    The model packs for the forecast; a repair that ignores it could top a winter
    trip up with shorts (the pre-push reviewer, 2026-09-07). Same arithmetic as
    the daily outfit, on the garment's own scale — but against the range, not
    both ends at once: a 5–25C trip needs both the warm trousers and the shorts,
    each for its own days (the reviewer again). So a garment is out only when it
    is too much even on the COLDEST day, or — for bottoms, which are worn alone —
    too thin even on the WARMEST. Tops are layered; a thin shirt under a coat is
    right at -2C, so no floor applies to inner and base.
    """
    if lo is not None and scale.too_warm(item, lo):
        return False
    if cat == "bottoms" and hi is not None:
        need = scale.min_outer_warmth(hi, scale.graded_on(item))
        if (item.get("warmth") or 3) < need - 1:
            return False
    return True


def owned_for(items: list[dict], cat: str, lo: float | None, hi: float | None) -> list[dict]:
    """What the wardrobe can actually put on for this trip, in this category."""
    return [i for i in items if i["category"] == cat and i["availableCount"] >= 1 and suits(i, cat, lo, hi)]


def trip_range(summary: dict) -> tuple[float, float]:
    """The temperatures the list was packed for. Beyond the forecast horizon the
    prompt packs for the extremes seen in past years, not the averages, so the
    repair reads the same numbers (the reviewer's third point)."""
    if summary.get("mode") == "normals":
        return (summary.get("loMinEver", summary["loMin"]), summary.get("hiMaxEver", summary["hiMax"]))
    return (summary["loMin"], summary["hiMax"])


def top_up(pack: list[dict], items: list[dict], n_days: int, styles: list[str],
           lo: float | None = None, hi: float | None = None) -> list[dict]:
    """Bring each scaling category up to what the trip needs, from what is owned.

    Target is the smaller of the need and what the wardrobe has available AND
    suitable for the trip's weather, so a short closet is never over-packed and a
    winter trip never gains shorts. Packed items go up to their own count first
    (a second pair of the same chinos); then unpacked suitable items join, those
    fitting the trip's registers first. Returns the same list, repaired in
    place, so ids the plan already references stay valid.
    """
    by_id = {i["id"]: i for i in items}
    for cat in SCALING:
        owned = owned_for(items, cat, lo, hi)
        ok_ids = {i["id"] for i in owned}
        target = min(needed(cat, n_days), sum(i["availableCount"] for i in owned))
        # Only SUITABLE packed items count towards the target. A pair of shorts the
        # model put on a winter list stays (its reasons are its own) but does not
        # stand in for the trousers the trip needs (the pre-push reviewer, 2026-09-07).
        got = sum(p["qty"] for p in pack if p["category"] == cat and p["id"] in ok_ids)
        if got >= target:
            continue
        before = got
        for p in pack:
            if p["category"] != cat or p["id"] not in ok_ids or got >= target:
                continue
            room = by_id[p["id"]]["availableCount"] - p["qty"]
            if room > 0:
                add = min(room, target - got)
                p["qty"] += add
                got += add
        packed_ids = {p["id"] for p in pack}
        spare = [i for i in owned if i["id"] not in packed_ids]
        spare.sort(key=lambda i: (not any(s in i["formality"] for s in styles), -i["availableCount"]))
        for i in spare:
            if got >= target:
                break
            qty = min(i["availableCount"], target - got)
            pack.append({"id": i["id"], "category": cat, "label": i["label"], "qty": qty,
                         "why": "enough for the length of the trip"})
            got += qty
        # Category and counts only — never labels (privacy invariant of the journal).
        log.info("packing top-up: %s %s -> %s of %s needed", cat, before, got, needed(cat, n_days))
    return pack


def counts(pack: list[dict]) -> dict[str, int]:
    """Quantity packed per category."""
    out: dict[str, int] = {}
    for p in pack:
        out[p["category"]] = out.get(p["category"], 0) + p["qty"]
    return out


NOUN = {"inner": ("undershirt", "undershirts"), "base": ("top", "tops"),
        "bottoms": ("pair of bottoms", "pairs of bottoms")}


def topup_line(before: dict[str, int], after: dict[str, int], n_days: int) -> str | None:
    """One sentence saying what the server added, for the top of the prose.

    The model's bullets were written before the repair and still say "two pairs";
    the list says five. Without this line the text and the list disagree and the
    reader trusts neither (live probe, 2026-09-07).
    """
    parts = []
    for c in SCALING:
        d = after.get(c, 0) - before.get(c, 0)
        if d > 0:
            parts.append(f"{d} more {NOUN[c][0] if d == 1 else NOUN[c][1]}")
    if not parts:
        return None
    return f"Added from your closet for {n_days} days: " + ", ".join(parts) + "."


def shortfall(category: str, have: int, want: int, n_days: int) -> str:
    """What to say when the wardrobe itself is short for the trip.

    "only 2 of ~5 clean — plan a laundry day" sat under a heading that said "You
    don't own", which is wrong for "you own two, wash twice". Say how often.
    """
    if have == 0:
        return f"none in your closet yet — bring or buy ~{want}"
    every = max(2, round(n_days * have / want))
    unit = "pairs" if category == "bottoms" else "tops"
    return f"{have} {unit} for {n_days} days — a wash every ~{every} days"


def validate_plan(raw: object, days: list[dict], pack: list[dict], travel: bool,
                  k: int = PLAN_DAYS) -> list[dict]:
    """The model's first-days plan, kept only where it names packed items.

    One entry per day for the first k days, each slot an id from `pack` whose
    category matches the slot, else null. A day that names nothing packed is
    dropped rather than invented. Day 1 is the travel day when the trip has one.
    """
    packed = {p["id"]: p for p in pack}
    k = min(k, len(days))
    out: list[dict] = []
    entries = raw if isinstance(raw, list) else []
    for i in range(k):
        entry = entries[i] if i < len(entries) and isinstance(entries[i], dict) else {}
        picks: dict[str, str | None] = {}
        for slot in CATEGORIES:
            iid = entry.get(slot)
            ok = isinstance(iid, str) and iid in packed and packed[iid]["category"] == slot
            picks[slot] = iid if ok else None
        if not any(picks.values()):
            continue
        out.append({"date": days[i]["date"], "travel": bool(travel and i == 0), "picks": picks})
    if len(out) < k:
        log.info("packing plan: %s of %s days usable", len(out), k)
    return out


def wash_days(n_days: int, have: int, want: int) -> int:
    """How many washes a shortfall implies — for a test to reason about, mostly."""
    if have <= 0 or have >= want:
        return 0
    return math.ceil(want / have) - 1
