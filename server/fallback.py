"""
fallback.py — the last resort, when the advisor has had its revisions and its best
answer still breaks a hard fact (2026-10-11 refactor).

One function, in one order, replacing the thirteen repair passes that used to run
on EVERY answer. It is reached rarely — the model is told about every issue first
(advisor.dress) — and it only does what a person would agree is necessary: take off
what cannot be worn, put on what is missing, add warmth when they would be cold,
take off what is far too warm. Everything else stays the model's choice.
"""
import check
import layers
import picks as pk
import rules
import scale
from check import TOPS, TORSO, Day, stacked
from sleeves import sleeve_clashes

_UNDRESSED = frozenset({"no-top", "inner-alone", "no-bottoms", "no-footwear"})
_COMFORT = ("hot-", "cold", "snow-")
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
    # 4. Two tops, or two of the same kind: the one worn over the other comes off.
    _unstack(out, wd)
    # 5. Far too warm: a cooler garment they own, or off if the slot can go.
    for slot in [s for s, i in out.items() if i]:
        if not out.get(slot):
            continue                              # a dress put on above took it off
        if layers.overdressed(wd.by_item[out[slot]], slot, wd, day.plan, day.peak, day.rules):
            was = out[slot]
            alt = _first(slot, out, day, pk._heat_temp(slot, day.plan, day.peak))
            if alt:
                _put(out, slot, alt, wd)
            elif slot in pk._SHEDDABLE and not _adds_trouble(out, {**out, slot: None}, day):
                out[slot] = None
            else:
                out[slot] = was                   # nothing cooler: better dressed than not
    # 6. Dressed: a top, trousers, shoes — whatever they own that is legal. A top
    #    that suits the heat first; failing that any legal top, because too warm is
    #    better than undressed (raised by the pre-push reviewer, 2026-10-11).
    if not any(out.get(c) for c in TORSO):
        _put_on_a_top(out, day)
    # 7. Warm enough for the coldest hour: knitwear or a jacket, the lightest that does it.
    if any(out.get(c) for c in TORSO) and not layers._still_warm(out, wd.by_item, day.plan):
        _warm_up(out, day)
    # 7b. Trousers and shoes LAST among the garments, after everything that can
    #     change the top — a dress swapped for a sweater above needs its trousers
    #     back (raised by the pre-push reviewer, 2026-10-11). What suits the heat
    #     first — shorts before jeans at 30C — and only failing that anything legal.
    for slot in ("bottoms", "footwear"):
        if not out.get(slot) and not (slot == "bottoms" and wd.by_group.get(out.get("base")) == "onepiece"):
            out[slot] = _first(slot, out, day, pk._heat_temp(slot, day.plan, day.peak)) \
                or _first(slot, out, day, None)
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


def _unstack(out: dict, wd) -> None:
    """Take garments off from the top down until the torso is not `stacked`."""
    for c in reversed(TORSO):
        if not stacked(out, wd.by_item):
            return
        if out.get(c) and any(out.get(lower) for lower in TORSO[:TORSO.index(c)]):
            out[c] = None


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
            if not rules.violations(day.rules, {**out, slot: iid}, wd.by_item) \
                    and not _adds_trouble(out, {**out, slot: iid}, day):
                out[slot] = iid
                break


def _adds_trouble(out: dict, trial: dict, day: Day) -> bool:
    """Would this change add a hard issue the outfit did not have — the same facts
    check.py judges? Every change the fallback makes passes this, so no step can
    undo another (raised by the pre-push reviewer, 2026-10-11, more than once). Legs
    a dress covered must stay covered, owned trousers or not."""
    wd = day.wd
    if wd.by_group.get(out.get("base")) == "onepiece" and wd.by_group.get(trial.get("base")) != "onepiece" \
            and not trial.get("bottoms"):
        return True
    before, after = check.hard(check.issues(out, day)), check.hard(check.issues(trial, day))
    added = after - before
    # Dressed beats comfortable: a change that covers a bare top, legs or feet may
    # leave them too warm or too cold — the only hoodie on a hot day is still a top.
    # Raised by the pre-push reviewer, 2026-10-11.
    if added and (before - after) & _UNDRESSED and all(k.startswith(_COMFORT) for k in added):
        return False
    return bool(added)


def _first(slot: str, out: dict, day: Day, hot: float | None) -> str | None:
    """The first unused garment they own that is legal for `slot`, warm enough if it
    is the outer layer, under `hot` if given, and adds no hard issue."""
    wd = day.wd
    for iid, item in wd.by_item.items():
        if iid in out.values() or slot not in (wd.by_roles.get(iid) or ()):
            continue
        if slot == "outer" and not scale.warm_enough(item, day.plan):
            continue
        if hot is not None and scale.too_warm(item, hot):
            continue
        trial = {**out, slot: iid}
        if slot == "base" and wd.by_group.get(iid) == "onepiece":
            trial["bottoms"] = None
        if rules.violations(day.rules, trial, wd.by_item) or _adds_trouble(out, trial, day):
            continue
        return iid
    return None


def _put_on_a_top(out: dict, day: Day) -> None:
    for heat in (True, False):
        for slot in TORSO:
            alt = _first(slot, out, day, pk._heat_temp(slot, day.plan, day.peak) if heat else None)
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
            trial = {**out, slot: iid}
            # Never the stack step 4 just took apart — the SAME rule check.py applies.
            # Raised twice by the pre-push reviewer, 2026-10-11.
            if stacked(trial, wd.by_item) or rules.violations(day.rules, trial, wd.by_item) \
                    or sleeve_clashes(trial, wd.by_item) or _adds_trouble(out, trial, day):
                continue
            snow_wet = bool(day.w.get("isSnow")) and slot == "outer" and not item.get("waterproof")
            cands.append((snow_wet, kind in TOPS, kind not in _WARM_FIRST, -scale.garment_temp(item), slot, iid))
    if cands:
        *_, slot, iid = min(cands)
        out[slot] = iid
        return
    # No layer to add: a warmer garment in place of the thin base — the knit polo
    # instead of the polo, the thick sweater instead of the thin one — never both.
    if out.get("base"):
        for iid, item in wd.by_item.items():
            # The base is worn all day: too warm judged by the afternoon (pre-push
            # reviewer, 2026-10-11).
            if (iid in out.values() or "base" not in (wd.by_roles.get(iid) or ())
                    or not scale.warm_enough(item, day.plan)
                    or scale.too_warm(item, pk._heat_temp("base", day.plan, day.peak))):
                continue
            trial = {**out, "base": iid}
            # Out of a dress: the trousers come in the SAME change, or not at all.
            if wd.by_group.get(out["base"]) == "onepiece" and wd.by_group.get(iid) != "onepiece":
                legs = _first("bottoms", trial, day, pk._heat_temp("bottoms", day.plan, day.peak)) \
                    or _first("bottoms", trial, day, None)
                if not legs:
                    continue
                trial["bottoms"] = legs
            if (not stacked(trial, wd.by_item) and not rules.violations(day.rules, trial, wd.by_item)
                    and not _adds_trouble(out, trial, day)):
                out.update(trial)
                return
