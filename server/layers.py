"""
layers.py — whether an outfit makes sense as a STACK, not garment by garment.

Since the 2026-10-11 refactor: the warmth and layer FACTS (warm enough, too warm,
how many layers today allows) read by check.py and fallback.py. The repairs that
used to act on them are gone — the advisor is told, and chooses again.

User, 2026-09-30, on a 14-23C morning that was dressed in a long-sleeve tee as the
undershirt, a t-shirt over it and a cardigan over that: "a stupid recommendation
which no human would do".

Every check before this one judges ONE garment: is it allowed in its slot, is it
warm enough to be outermost, is it too warm for the hour it is worn through. Each
of those three garments passed each of them. What was wrong was the combination,
and nothing looked at the combination. Two rules do now, in code, after the model
has answered — the same posture as every other guard here, because a request in
the prompt is followed most of the time, and that is not the same as followed.

  SLEEVE RULE   a long sleeve never goes under a short one. The cuffs show below
                the short sleeve, and nobody dresses like that on purpose.
  LAYER BUDGET  how many torso layers the day allows, from how cold it is. Three
                on a mild morning is a layer too many even when each one is thin.

Both take clothing OFF, or swap an undershirt for a short-sleeved one, and never
touch the base or the outer layer — the base is the outfit, and the outer is also
the rain and wind protection. The one thing either ADDS is warmth the sleeve rule
itself took away: live on the day it shipped, the model answered long-T + tee three
times out of three, and taking the long-T off left a t-shirt alone on a 14C morning.
A person would reach for the cardigan, so the repair does too.

Split into its own module because picks.py sits at the 600-line ceiling.
"""

import picks as pk
import rules
import scale

_TORSO = ("inner", "base", "mid", "outer")

# Below this felt temperature at the coldest hour, going out means a jacket or coat
# over the knitwear (user, 2026-10-18: a 2-13C morning served a sweater and no coat).
# The plan temperature already carries the wearer's warm/cold calibration.
COAT_BELOW_C = 8
# Below this the coat goes over knitwear whatever the coat (user, 2026-10-18: felt
# -1..10C). Between it and COAT_BELOW_C a warm coat over the top is enough (user,
# 2026-10-24: "Coat over the top" — a knit polo, a cardigan AND a parka at 5-12C).
KNIT_AND_COAT_BELOW_C = 5


def coat_alone(item: dict, plan_temp: float) -> bool:
    """This coat is warm enough over the top by itself this cold morning: a level
    warmer than the coldest hour asks of the outermost garment."""
    need = scale.min_outer_warmth(plan_temp, scale.graded_on(item))
    return plan_temp >= KNIT_AND_COAT_BELOW_C and (item.get("warmth") or 3) >= need + 1


def tee_base(picks: dict, by_item: dict) -> bool:
    """The top is a T-shirt: no undershirt under it (user, 2026-10-24: "No undershirt
    rule is for T-shirt and not shirts"). Under a shirt, a polo or a knit, as before."""
    return (by_item.get(picks.get("base")) or {}).get("type") == "t_shirt"


def max_layers(picks: dict, by_item: dict, plan_temp: float) -> int:
    """How many torso layers today allows: 2 on a mild or warm day, up to 4 in the
    cold. The same warmth the day asks of an outer layer, so 12-18C on the absolute
    scale (warmth 2) allows two, 5-12C three, and below that four.

    Read on the BASE garment's scale, the one layer always worn, so a wardrobe graded
    against the wearer's own year is judged in its own units like every other check.
    """
    ref = by_item.get(picks.get("base")) or next(
        (by_item.get(picks[c]) for c in _TORSO if picks.get(c)), None) or {}
    # A cold morning can be undershirt, top, knitwear AND a coat — four, whatever the
    # scale says, or the budget fights the coat the check demands and the undershirt
    # is what gets dropped (plan review, 2026-10-18).
    return max(4 if plan_temp < COAT_BELOW_C else 2, _budget(plan_temp, ref))


def _budget(plan_temp: float, ref: dict) -> int:
    need = scale.min_outer_warmth(plan_temp, scale.graded_on(ref))
    return max(2, min(4, need))


def _still_warm(picks: dict, by_item: dict, plan_temp: float) -> bool:
    return any(scale.warm_enough(by_item.get(picks[c]) or {}, plan_temp)
               for c in _TORSO if picks.get(c))


def overdressed(item: dict, slot: str, wd, plan_temp: float, peak_temp: float,
                user_rules: list[dict] | None = None) -> bool:
    """Is this garment too warm to wear as `slot` today, in a way that can be HELPED?

    Too warm by the numbers, and either the slot can simply be left off (an
    undershirt, a layer) or they own something cooler for it. Trousers they have
    nothing cooler than are not too warm, they are the trousers: the live test days
    (2026-10-11) found every pair marked TOO WARM on an 18-23C day, the model
    obeying, and the legs left bare. picks._cool_down always kept such trousers;
    the prompt and the review now say the same.
    """
    hot = pk._heat_temp(slot, plan_temp, peak_temp)
    if not scale.too_warm(item, hot):
        return False
    if slot in pk._SHEDDABLE:
        return True
    # An alternative they have banned outright is no alternative: asking for it would
    # be an impossible correction (raised by the pre-push reviewer, 2026-10-11).
    outright = [r for r in user_rules or [] if not rules.is_combination(r)]
    return any(slot in (wd.by_roles.get(i) or ()) and not scale.too_warm(it, hot)
               and not rules.violations(outright, {slot: i}, wd.by_item)
               for i, it in wd.by_item.items() if it is not item)


def _top_for_an_undershirt(wd, user_rules: list[dict], plan_temp: float, peak_temp: float) -> bool:
    """They own a top other than a tee — a shirt, a knit, a cardigan worn as the top —
    not banned outright and not too warm today: the undershirt goes under
    that instead — so the cold tee is a choice to change, not a gap (pre-push gate,
    2026-10-24)."""
    outright = [r for r in user_rules or [] if not rules.is_combination(r)]
    # …that today allows: a warmth-5 sweater on a 7-12C day is no top to change into.
    # A cardigan worn as the top goes over the undershirt too (pre-push gate, 2026-10-24).
    return any(it.get("type") != "t_shirt" and any(
        r in ("base", "mid") and not rules.violations(outright, {r: i}, wd.by_item)
        and not overdressed(it, r, wd, plan_temp, peak_temp, user_rules) for r in wd.by_roles.get(i) or ())
        for i, it in wd.by_item.items())


def too_cold_for_outfit(picks: dict, wd, plan_temp: float, user_rules: list[dict],
                        peak_temp: float | None = None) -> bool:
    """Nothing on the torso is warm enough for the morning, after every repair has
    had its turn: the wardrobe has nothing to fix it with. Only meaningful on the
    FINISHED picks."""
    # Nothing on the torso at all is a missing top, not a cold morning: the gap
    # for that is the slot's own, and on a hot day it is no reason to buy a coat.
    if not any(picks.get(c) for c in _TORSO) or _still_warm(picks, wd.by_item, plan_temp):
        return False
    # A warm garment owned and merely not usable together with the rest (a sleeve
    # clash, a pairing rule) is a styling problem, not something to buy. One the
    # wearer has banned outright does not count: for them the wardrobe has no such
    # garment. Worn all day, a layer is judged by the afternoon for heat too.
    peak = plan_temp if peak_temp is None else peak_temp
    return not any(scale.warm_enough(item, plan_temp)
                   and any(not scale.too_warm(item, pk._heat_temp(r, plan_temp, peak))
                           and not rules.violations(user_rules, {r: iid}, wd.by_item)
                           for r in wd.by_roles.get(iid) or () if r in _TORSO
                           # An undershirt warms nobody wearing a tee: it never goes
                           # under one (Codex review, 2026-10-24 — every tee outfit
                           # was "fixably" cold, and a tee-only closet got nothing).
                           and not (r == "inner" and tee_base(picks, wd.by_item)
                                    and not _top_for_an_undershirt(wd, user_rules, plan_temp, peak)))
                   for iid, item in wd.by_item.items() if iid not in picks.values())


