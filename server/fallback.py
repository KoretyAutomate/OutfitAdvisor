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
    # 6. Dressed: a top, trousers, shoes — whatever they own that is legal.
    if not any(out.get(c) for c in TORSO):
        for slot in TORSO:
            alt = pk._suitable_for(slot, out, wd, day.plan, day.rules,
                                   hot_temp=pk._heat_temp(slot, day.plan, day.peak))
            if alt:
                out[slot] = alt
                break
    for slot in ("bottoms", "footwear"):
        if not out.get(slot) and not (slot == "bottoms" and wd.by_group.get(out.get("base")) == "onepiece"):
            out[slot] = pk._suitable_for(slot, out, wd, day.plan, day.rules)
    # 7. Warm enough for the coldest hour: knitwear or a jacket, the lightest that does it.
    if any(out.get(c) for c in TORSO) and not layers._still_warm(out, wd.by_item, day.plan):
        _warm_up(out, day)
    # 8. An undershirt is never worn on its own.
    if out.get("inner") and not any(out.get(c) for c in TORSO):
        out["inner"] = None
    return out, {s: out.get(s) for s in set(out) | set(before) if out.get(s) != before.get(s)}


def _warm_up(out: dict, day: Day) -> None:
    wd = day.wd
    cands = []
    for slot in ("mid", "outer"):
        if out.get(slot):
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
            cands.append((kind in TOPS, kind not in _WARM_FIRST, -scale.garment_temp(item), slot, iid))
    if cands:
        *_, slot, iid = min(cands)
        out[slot] = iid
