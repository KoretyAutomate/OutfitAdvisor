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
    # 4. Two tops, or two of the same kind (two shirts): the one worn over the other
    #    comes off — the same condition check.py calls `stacked`.
    seen_kinds: set = set()
    tops = 0
    for c in TORSO:
        if not out.get(c):
            continue
        kind = wd.by_item[out[c]].get("type")
        if (kind in TOPS and tops) or (kind and kind in seen_kinds):
            out[c] = None
            continue
        tops += kind in TOPS
        seen_kinds.add(kind)
    # 5. Far too warm: a cooler garment they own, or off if the slot can go.
    for slot in [s for s, i in out.items() if i]:
        if not out.get(slot):
            continue                              # a dress put on above took it off
        if layers.overdressed(wd.by_item[out[slot]], slot, wd, day.plan, day.peak, day.rules):
            out[slot] = None
            alt = pk._suitable_for(slot, out, wd, day.plan, day.rules,
                                   hot_temp=pk._heat_temp(slot, day.plan, day.peak))
            if alt or slot in pk._SHEDDABLE:
                _put(out, slot, alt, wd)
            else:
                out[slot] = before[slot]          # nothing cooler: better dressed than not
    # 6. Dressed: a top, trousers, shoes — whatever they own that is legal. A top
    #    that suits the heat first; failing that any legal top, because too warm is
    #    better than undressed (raised by the pre-push reviewer, 2026-10-11).
    if not any(out.get(c) for c in TORSO):
        _put_on_a_top(out, day)
    for slot in ("bottoms", "footwear"):
        if not out.get(slot) and not (slot == "bottoms" and wd.by_group.get(out.get("base")) == "onepiece"):
            # What suits the heat first — shorts before jeans at 30C — and only
            # failing that anything legal. Raised by the pre-push reviewer, 2026-10-11.
            out[slot] = pk._suitable_for(slot, out, wd, day.plan, day.rules,
                                         hot_temp=pk._heat_temp(slot, day.plan, day.peak)) \
                or pk._suitable_for(slot, out, wd, day.plan, day.rules)
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


def _put(out: dict, slot: str, iid: str | None, wd) -> None:
    """Put a garment on; a dress in `base` takes the trousers off AT ONCE, so every
    later search judges the outfit that will actually be worn. Raised by the
    pre-push reviewer, 2026-10-11."""
    out[slot] = iid
    if slot == "base" and iid and wd.by_group.get(iid) == "onepiece":
        out["bottoms"] = None


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
                _put(out, slot, alt, day.wd)
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
            kind = item.get("type") or ""
            # Never a second top: that is the stack step 4 just took apart. Raised by
            # the pre-push reviewer, 2026-10-11.
            if kind in TOPS and any(wd.by_item[out[c]].get("type") in TOPS for c in TORSO if out.get(c) and c != slot):
                continue
            trial = {**out, slot: iid}
            if rules.violations(day.rules, trial, wd.by_item) or sleeve_clashes(trial, wd.by_item):
                continue
            snow_wet = bool(day.w.get("isSnow")) and slot == "outer" and not item.get("waterproof")
            cands.append((snow_wet, kind in TOPS, kind not in _WARM_FIRST, -scale.garment_temp(item), slot, iid))
    if cands:
        *_, slot, iid = min(cands)
        out[slot] = iid
        return
    # No layer to add: a warmer TOP in place of the thin one — the knit polo instead
    # of the polo, rather than both.
    base = out.get("base")
    if base and wd.by_item[base].get("type") in TOPS:
        for iid, item in wd.by_item.items():
            # The base is worn all day: too warm judged by the afternoon (pre-push
            # reviewer, 2026-10-11).
            if (iid not in out.values() and "base" in (wd.by_roles.get(iid) or ())
                    and scale.warm_enough(item, day.plan)
                    and not scale.too_warm(item, pk._heat_temp("base", day.plan, day.peak))
                    and not rules.violations(day.rules, {**out, "base": iid}, wd.by_item)):
                out["base"] = iid
                return
