"""
fallback.py — the last resort, when the advisor has had its revisions and its best
answer still breaks a hard fact (2026-10-11 refactor).

One function, in one order, replacing the thirteen repair passes that used to run
on EVERY answer. It is reached rarely — the model is told about every issue first
(advisor.dress) — and it only does what a person would agree is necessary: take off
what cannot be worn, put on what is missing, add warmth when they would be cold,
take off what is far too warm. Everything else stays the model's choice.
"""
import layers
import picks as pk
import rules
import scale
from check import TOPS, TORSO, Day
from sleeves import sleeve_clashes

# What a person reaches for to get warmer: knitwear, then a jacket — never a top.
_WARM_FIRST = ("cardigan", "sweater", "hoodie", "fleece", "waistcoat", "blazer", "jacket", "coat", "puffer")


def fix(picks: dict, day: Day) -> tuple[dict, dict]:
    """(picks, changed) where `changed` maps each slot touched to what it holds now."""
    wd, out = day.wd, dict(picks)
    before = dict(out)

    # 1. What cannot be worn as given: unknown, twice, wrong slot.
    seen: set = set()
    for slot, iid in list(out.items()):
        if iid and (iid not in wd.ids or iid in seen or slot not in (wd.by_roles.get(iid) or ())):
            out[slot] = None
        elif iid:
            seen.add(iid)
    # 2. Their rules, one blamed slot at a time (each clearing can resolve others).
    for _ in range(len(out)):
        broken = rules.violations(day.rules, out, wd.by_item)
        if not broken:
            break
        out[broken[0]["slot"]] = None
    # 3. A dress covers the legs.
    if wd.by_group.get(out.get("base")) == "onepiece":
        out["bottoms"] = None
    # 4. Two tops: the one worn over the other comes off.
    torso = [c for c in TORSO if out.get(c)]
    tops = [c for c in torso if wd.by_item[out[c]].get("type") in TOPS]
    for c in tops[1:]:
        out[c] = None
    # 5. Far too warm: a cooler garment they own, or off if the slot can go.
    for slot in [s for s, i in out.items() if i]:
        if layers.overdressed(wd.by_item[out[slot]], slot, wd, day.plan, day.peak):
            out[slot] = None
            alt = pk._suitable_for(slot, out, wd, day.plan, day.rules,
                                   hot_temp=pk._heat_temp(slot, day.plan, day.peak))
            if alt or slot in pk._SHEDDABLE:
                out[slot] = alt
            else:
                out[slot] = before[slot]          # nothing cooler: better dressed than not
    # 6. Dressed: a top, trousers, shoes — whatever they own that is legal. A top
    #    that suits the heat first; failing that any legal top, because too warm is
    #    better than undressed (raised by the pre-push reviewer, 2026-10-11).
    if not any(out.get(c) for c in TORSO):
        _put_on_a_top(out, day)
    for slot in ("bottoms", "footwear"):
        if not out.get(slot) and not (slot == "bottoms" and wd.by_group.get(out.get("base")) == "onepiece"):
            out[slot] = pk._suitable_for(slot, out, wd, day.plan, day.rules)
    # 7. Warm enough for the coldest hour: knitwear or a jacket, the lightest that does it.
    if any(out.get(c) for c in TORSO) and not layers._still_warm(out, wd.by_item, day.plan):
        _warm_up(out, day)
    # 8. An undershirt is never worn on its own.
    if out.get("inner") and not any(out.get(c) for c in TORSO):
        out["inner"] = None
    # 9. Snow: the waterproof boots or coat they own. Snow is not rain. Raised by the
    #    pre-push reviewer, 2026-10-11.
    if day.w.get("isSnow"):
        _snow_proof(out, day)
    # 10. A dress covers the legs — again, since steps 5 and 6 can put one on.
    #    Raised by the pre-push reviewer, 2026-10-11.
    if wd.by_group.get(out.get("base")) == "onepiece":
        out["bottoms"] = None
    return out, {s: out.get(s) for s in set(out) | set(before) if out.get(s) != before.get(s)}


def _snow_proof(out: dict, day: Day) -> None:
    wd = day.wd
    for slot in ("footwear", "outer"):
        if out.get(slot) and wd.by_item[out[slot]].get("waterproof"):
            continue
        for iid, item in wd.by_item.items():
            if not item.get("waterproof") or iid in out.values() or slot not in (wd.by_roles.get(iid) or ()):
                continue
            if slot == "outer" and not scale.warm_enough(item, day.plan) and out.get(slot):
                continue
            if not rules.violations(day.rules, {**out, slot: iid}, wd.by_item):
                out[slot] = iid
                break


def _put_on_a_top(out: dict, day: Day) -> None:
    for heat in (True, False):
        for slot in TORSO:
            hot = pk._heat_temp(slot, day.plan, day.peak) if heat else None
            alt = pk._suitable_for(slot, out, day.wd, day.plan, day.rules, hot_temp=hot)
            if alt:
                out[slot] = alt
                return


def _warm_up(out: dict, day: Day) -> None:
    wd = day.wd
    cands = []
    for slot in ("mid", "outer"):
        # An occupied layer is open too when it is itself too thin: a linen overshirt
        # as the mid, a warmth-3 jacket at 3C, with a sweater owned and unworn.
        # Raised by the pre-push reviewer, 2026-10-11.
        if out.get(slot) and scale.warm_enough(wd.by_item[out[slot]], day.plan):
            continue
        for iid, item in wd.by_item.items():
            if iid in out.values() or slot not in (wd.by_roles.get(iid) or ()):
                continue
            if not scale.warm_enough(item, day.plan) or scale.too_warm(item, day.plan):
                continue
            trial = {**out, slot: iid}
            if rules.violations(day.rules, trial, wd.by_item) or sleeve_clashes(trial, wd.by_item):
                continue
            kind = item.get("type") or ""
            snow_wet = bool(day.w.get("isSnow")) and slot == "outer" and not item.get("waterproof")
            cands.append((snow_wet, kind in TOPS, kind not in _WARM_FIRST, -scale.garment_temp(item), slot, iid))
    if cands:
        *_, slot, iid = min(cands)
        out[slot] = iid
