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
import itertools
import logging
import math

import rules
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
    is too much even on the COLDEST day, or — for trousers and shoes, which are
    worn alone — too thin even on the WARMEST. Tops are layered; a thin shirt under
    a coat is right at -2C, so no floor applies to inner and base. The leg floor is
    the daily outfit's (scale.too_cold_for_legs, 2026-11-18): summer wear only, so
    the two never disagree about the same garment.
    """
    if lo is not None and scale.too_warm(item, lo):
        return False
    return not (cat in LEGS and hi is not None and scale.too_cold_for_legs(item, hi))


LEGS = ("bottoms", "footwear")


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
           band: tuple = (None, None), user_rules: list[dict] | None = None) -> list[dict]:
    """Bring each scaling category up to what the trip needs, from what is owned.

    Target is the smaller of the need and what the wardrobe has available AND
    suitable for the trip's weather, so a short closet is never over-packed and a
    winter trip never gains shorts. Packed items go up to their own count first
    (a second pair of the same chinos); then unpacked suitable items join, those
    fitting the trip's registers first. Returns the same list, repaired in
    place, so ids the plan already references stay valid. `band`: the trip's
    (lo, hi); `user_rules`: what replacement shoes must keep with the trousers.
    """
    lo, hi = band
    by_id = {i["id"]: i for i in items}
    # Summer legs on a winter list come off, whatever the model's reason (user,
    # 2026-11-18: "I don't need shorts nor summer pants ... during winter"). This
    # reverses the 2026-09-07 call to keep them standing in for nothing.
    dropped = too_thin(pack, items, lo, hi)
    if dropped:
        pack[:] = [p for p in pack if p not in dropped]
        log.info("packing: %d leg item(s) too thin for the trip left out", len(dropped))
        _replace_shoes(pack, items, styles, band, user_rules or [])
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
        spare.sort(key=lambda i: (*_fit(i, cat, pack, user_rules or [], by_id),
                                  not any(s in i["formality"] for s in styles), -i["availableCount"]))
        for i in spare:
            if got >= target:
                break
            qty = min(i["availableCount"], target - got)
            pack.append({"id": i["id"], "category": cat, "label": i["label"], "qty": qty,
                         "why": "enough for the length of the trip"})
            got += qty
        # Category and counts only — never labels (privacy invariant of the journal).
        log.info("packing top-up: %s %s -> %s of %s needed", cat, before, got, needed(cat, n_days))
    if dropped:     # the mornings the added tops and trousers make get shoes too
        _replace_shoes(pack, items, styles, band, user_rules or [])
    return pack


def _replace_shoes(pack: list[dict], items: list[dict], styles: list[str], band: tuple,
                   user_rules: list[dict]) -> None:
    """Shoes are not topped up, so dropped ones are replaced by the best suitable pair
    owned; owning none is /packing's footwear gap (pre-push gate, 2026-11-21: sandals
    dropped from a winter list left no shoes at all). BEFORE the trousers and tops are
    topped up, which then go with them (_fit), and chosen with them in mind: first a
    pair some suitable top and trousers they own may be worn with, then one no rule
    bans with everything packed of a kind — sneakers banned with the only jeans or the
    only tee left the planned mornings barefoot while loafers or chinos stayed home
    (pre-push gate, 2026-11-24). Then the pair banned with the fewest packed garments."""
    by_id = {i["id"]: i for i in items}

    def alone(shoe: dict) -> bool:
        """Some kind of garment the trip needs has nothing suitable to wear with it."""
        return any((kind := owned_for(items, cat, *band)) and all(
            rules.violations(user_rules, {cat: i["id"], "footwear": shoe["id"]}, by_id) for i in kind)
            for cat in ("base", "bottoms"))
    shoes = sorted(owned_for(items, "footwear", *band),
                   key=lambda i: (alone(i), *_fit(i, "footwear", pack, user_rules, by_id),
                                  not any(s in i["formality"] for s in styles), i["id"]))
    kept = [by_id[p["id"]] for p in pack if p["category"] == "footwear" and p["id"] in by_id]
    if not shoes and not kept:
        return
    # Shoes still on the list stay; a pair is added only for what they cannot cover
    # (pre-push gate, 2026-11-24: boots kept, banned with the jeans, left that morning
    # barefoot while loafers stayed home).
    chosen = list(kept) or [shoes[0]]
    # Every morning the list can make gets shoes it may wear: each packed top with each
    # packed pair of trousers (a one-piece alone), checked WHOLE. Checked one garment at
    # a time, boots banned with the tee and sneakers with the jeans each passed, and the
    # tee-and-jeans morning went barefoot while loafers stayed home (pre-push gate,
    # 2026-11-24).
    for look in _mornings(pack, by_id, user_rules):
        def ok(shoe: dict, look: dict = look) -> bool:
            return not rules.violations(user_rules, {**look, "footwear": shoe["id"]}, by_id)
        if not any(ok(c) for c in chosen) and (fits := [s for s in shoes if s not in chosen and ok(s)]):
            chosen.append(fits[0])
    for c in chosen[len(kept):]:
        pack.append({"id": c["id"], "category": "footwear", "label": c["label"], "qty": 1,
                     "why": "warm enough for the trip"})


def _mornings(pack: list[dict], by_id: dict, user_rules: list[dict]) -> list[dict]:
    """The legal top-and-trousers mornings the packed list can make; a one-piece is a
    morning alone."""
    tops = [p["id"] for p in pack if p["category"] == "base" and p["id"] in by_id] or [None]
    legs = [p["id"] for p in pack if p["category"] == "bottoms" and p["id"] in by_id] or [None]
    out = []
    for t, b in itertools.product(tops, legs):
        one = t and by_id[t].get("group") == "onepiece"
        look = {k: v for k, v in (("base", t), ("bottoms", None if one else b)) if v}
        if look and look not in out and not rules.violations(user_rules, look, by_id):
            out.append(look)
    return out


def _fit(item: dict, slot: str, pack: list[dict], user_rules: list[dict], by_id: dict) -> tuple:
    """How well a garment joining the list goes with what is packed: (banned by some
    rule with everything packed of another kind, how many packed garments it is
    banned with). Lower is better. Trousers banned with the only shoes, or shoes with
    the only tee, would leave the planned mornings short while a pair that goes stays
    home (pre-push gate, 2026-11-24)."""
    kinds: dict[str, list[str]] = {}
    for p in pack:
        if p["category"] != slot and p["id"] in by_id:
            kinds.setdefault(p["category"], []).append(p["id"])
    hits = {k: sum(bool(rules.violations(user_rules, {k: i, slot: item["id"]}, by_id)) for i in ids)
            for k, ids in kinds.items()}
    return any(hits[k] == len(ids) for k, ids in kinds.items()), sum(hits.values())


def counts(pack: list[dict]) -> dict[str, int]:
    """Quantity packed per category."""
    out: dict[str, int] = {}
    for p in pack:
        out[p["category"]] = out.get(p["category"], 0) + p["qty"]
    return out


NOUN = {"inner": ("undershirt", "undershirts"), "base": ("top", "tops"),
        "bottoms": ("pair of bottoms", "pairs of bottoms")}


def too_thin(pack: list[dict], items: list[dict], lo: float | None, hi: float | None) -> list[dict]:
    """Packed trousers and shoes too thin even for the trip's warmest day: what top_up
    leaves at home (2026-11-18)."""
    # The cold side only: a pair too WARM for a hot trip is the model's call and stays,
    # as before; only summer legs on a cold trip are left home (pre-push gate,
    # 2026-11-21: warmth-3 jeans dropped from a 24-30C trip and called "too light").
    by_id = {i["id"]: i for i in items}
    return [p for p in pack if p["category"] in LEGS and p["id"] in by_id
            and hi is not None and scale.too_cold_for_legs(by_id[p["id"]], hi)]


def topup_line(before: dict[str, int], after: dict[str, int], n_days: int,
               gone: list[dict] | None = None) -> str | None:
    """One sentence saying what the server changed, for the top of the prose.

    The model's bullets were written before the repair and still say "two pairs";
    the list says five. Without this line the text and the list disagree and the
    reader trusts neither (live probe, 2026-09-07). `gone`: what too_thin left at
    home, named, since the bullets may still say to bring it (pre-push gate,
    2026-11-21).
    """
    left = ("Left at home, too light for this trip's weather: "
            + ", ".join(str(p.get("label") or "an item") for p in gone) + ".") if gone else ""
    parts = []
    for c in SCALING:
        d = after.get(c, 0) - before.get(c, 0)
        if d > 0:
            parts.append(f"{d} more {NOUN[c][0] if d == 1 else NOUN[c][1]}")
    added = f"Added from your closet for {n_days} days: " + ", ".join(parts) + "." if parts else ""
    return " ".join(x for x in (left, added) if x) or None


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
        refill = []
        for slot in CATEGORIES:
            iid = entry.get(slot)
            ok = isinstance(iid, str) and iid in packed and packed[iid]["category"] == slot
            picks[slot] = iid if ok else None
            # Trousers or shoes the list no longer holds (top_up drops summer legs from
            # a winter trip): keep_rules refills the slot from what IS packed, within
            # their rules, so a planned morning never goes out without them (pre-push
            # gate, 2026-11-21).
            if slot in LEGS and isinstance(iid, str) and not ok:
                refill.append(slot)
        if not any(picks.values()):
            continue
        day = {"date": days[i]["date"], "travel": bool(travel and i == 0), "picks": picks}
        out.append({**day, "_refill": refill} if refill else day)
    if len(out) < k:
        log.info("packing plan: %s of %s days usable", len(out), k)
    return out


def keep_rules(plan: list[dict], user_rules: list[dict], items: list[dict],
               pack: list[dict] | None = None) -> list[dict]:
    """The planned mornings held to the wearer's rules (pre-push reviewer, 2026-10-11):
    packing both halves of a banned pair is fine, wearing them together on a planned
    morning is not — the blamed garment comes off that morning; a morning with
    nothing left is dropped. A slot validate_plan marked for refilling gets the first
    packed garment of its kind that keeps every rule with the rest of the morning,
    rotated by day so three mornings don't all wear the same pair."""
    by_item = {i["id"]: i for i in items}
    out = []
    for n, day in enumerate(plan):
        picks = dict(day["picks"])
        # The morning's own rule breaks first, so an unrelated banned pair cannot veto
        # every replacement (pre-push gate, 2026-11-21).
        for _ in CATEGORIES:
            broken = rules.violations(user_rules, picks, by_item)
            if not broken:
                break
            picks[broken[0]["slot"]] = None
        picks.update(_refill(day, picks, pack or [], user_rules, by_item, n))
        day = {k: v for k, v in day.items() if k != "_refill"}
        if any(picks.values()):
            out.append({**day, "picks": picks})
    return out


def _refill(day: dict, picks: dict, pack: list[dict], user_rules: list[dict], by_item: dict, n: int) -> dict:
    """The replacements for a morning's marked slots, chosen TOGETHER: trousers picked
    first could rule out the only shoes another pair goes with (pre-push gate,
    2026-11-21). The first combination keeping every rule with every slot filled,
    else the one filling most; each slot's packed garments rotated by day `n`. Never
    trousers under a one-piece."""
    onepiece = (by_item.get(picks.get("base")) or {}).get("group") == "onepiece"
    slots = [s for s in day.get("_refill", ()) if not (s == "bottoms" and onepiece)]
    options = []
    for slot in slots:
        kind = [p["id"] for p in pack if p["category"] == slot and p["id"] in by_item]
        options.append([*(kind[n % len(kind):] + kind[:n % len(kind)] if kind else []), None])
    best: tuple = (-1, ())
    for combo in itertools.product(*options):
        filled = sum(c is not None for c in combo)
        if filled > best[0] and not rules.violations(user_rules, {**picks, **dict(zip(slots, combo, strict=True))},
                                                     by_item):
            best = (filled, combo)
            if filled == len(slots):
                break
    # Nothing passed at all only if the morning still broke a rule on its own: refill
    # nothing rather than raise.
    return dict(zip(slots, best[1], strict=True)) if best[0] >= 0 else {}


def wash_days(n_days: int, have: int, want: int) -> int:
    """How many washes a shortfall implies — for a test to reason about, mostly."""
    if have <= 0 or have >= want:
        return 0
    return math.ceil(want / have) - 1


def with_feedback(items: list[dict], days: list[dict], summary: dict, offset: float,
                  user_rules: list[dict]) -> tuple[list[dict], tuple[list[dict], dict]]:
    """What the wearer taught the daily advice, for the packing list too (2026-10-11):
    a garment banned outright stays home, and the forecast the list is packed for is
    shifted by how warm or cold they run — a COPY, the trip card still shows the real
    forecast. Pairing rules travel to the prompt (packlist), since a suitcase holds
    both halves of a pair without either being wrong."""
    outright = [r for r in user_rules if not rules.is_combination(r)]
    # Banned only where EVERY role it can play is banned: "no sweater as the base"
    # still packs it as a mid layer — and is then FILED as one, so the counting, the
    # top-up and the plan, which all read `category`, never use it in the banned
    # role (pre-push reviewer, 2026-10-11).
    kept = []
    for i in items:
        allowed = [r for r in (i.get("roles") or [i["category"]])
                   if not rules.violations(outright, {r: i["id"]}, {i["id"]: i})]
        if allowed:
            kept.append({**i, "roles": allowed,
                         "category": i["category"] if i["category"] in allowed else allowed[0]})

    def shift(v: object) -> object:
        return math.floor(v + offset + 0.5) if isinstance(v, (int, float)) and offset else v
    felt_days = [{**d, "lo": shift(d.get("lo")), "hi": shift(d.get("hi"))} for d in days]
    felt = {**summary, **{k: shift(summary[k]) for k in ("loMin", "hiMax", "loMinEver", "hiMaxEver") if k in summary}}
    return kept, (felt_days, felt)
