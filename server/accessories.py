"""
accessories.py — one slot per body area, chosen after the outfit (user, 2026-11-24).

User: "Accessories needs to be split. Belt and scarf can go together." Asked how far,
they chose by body area: belt, neck (scarf, tie), head (hat), hands (gloves) and an
umbrella. vocab.ACCESSORY_SLOTS names them.

Each is worn for a reason, never for the points: a belt with trousers or jeans, a
scarf on a coat morning, a hat and gloves below 5C (engine.py's generic bar), an
umbrella on a wet day (funnel's bar). A tie is still never chosen, as before the split.

They are NOT part of the outfit search. Five optional slots there multiplied every
combination the exhaustive walk tries (three of each: 4^5 = 1,024 per outfit) and
let equal scarf variants crowd different trousers out of the beam (Codex plan review,
2026-11-24). So the search dresses the six clothing slots, and each outfit it finds
gets its accessories here: per slot, the best candidate the day has a reason for that
breaks no rule and no pairing (a brown belt with black shoes) with what is worn.
"""
import layers
from vocab import ACCESSORY_SLOTS

COLD_HANDS_C = 5.0        # a hat and gloves below this (engine.py's generic advice)
WET_RAIN_PCT = 50         # funnel.Ctx.wet's bar, so a wet day means one thing
WARM_HAT = 3              # a cap or sun hat (warmth 1-2) is no cold-weather hat
_KIND = {"belt": "belt", "neck": "scarf", "head": "hat", "hands": "gloves", "umbrella": "umbrella"}
_BELTED = ("trousers", "jeans")


def wet(w: dict) -> bool:
    return (w.get("rain") or 0) >= WET_RAIN_PCT or bool(w.get("isRain"))


def wanted(slot: str, day, picks: dict) -> bool:
    """Does today, with these clothes, call for something in this slot?"""
    if slot == "belt":
        return (day.wd.by_item.get(picks.get("bottoms")) or {}).get("type") in _BELTED
    if slot == "neck":
        return day.plan < layers.COAT_BELOW_C
    if slot in ("head", "hands"):
        return day.plan < COLD_HANDS_C
    return slot == "umbrella" and wet(day.w)


def reason(slot: str, item: dict, day, picks: dict) -> bool:
    """This garment, in this slot, is worn for a reason today."""
    if item.get("type") != _KIND.get(slot) or not wanted(slot, day, picks):
        return False
    return slot != "head" or int(item.get("warmth") or WARM_HAT) >= WARM_HAT


def score(day, picks: dict) -> float:
    """+0.5 for each accessory worn for a reason, -1 for one worn without (a model's
    or a re-roll's pick): the rank's old accessory term, per slot."""
    by = day.wd.by_item
    return sum(0.5 if reason(s, by[i], day, picks) else -1.0
               for s in ACCESSORY_SLOTS if (i := picks.get(s)) and i in by)


# (id(day), target, relaxed, width, cold_ok) -> (day, {slot: [ids, best first]}): what
# funnel._keeps and the priority depend on. The day is kept so its id cannot be reused
# while cached; a few requests' worth at most.
_CANDS: dict = {}


def _candidates(ctx, priority, keeps, widen: int) -> dict:
    k = (id(ctx.day), ctx.target, ctx.relaxed, ctx.width, ctx.cold_ok)
    hit = _CANDS.get(k)
    if hit is None or hit[0] is not ctx.day:
        while len(_CANDS) >= 32:
            _CANDS.pop(next(iter(_CANDS)))
        wd = ctx.wd

        def ranked(s: str) -> list:
            ids = [i for i in wd.ids if s in (wd.by_roles.get(i) or ()) and keeps(ctx, s, i, widen) is None]
            return sorted(ids, key=lambda i: (-priority(i, s), i))
        hit = _CANDS[k] = (ctx.day, {s: ranked(s) for s in ACCESSORY_SLOTS})
    return hit[1]


def dress(ctx, picks: dict, priority, keeps, clash, widen: int) -> dict:
    """The outfit with its accessories: per slot, the best candidate worn for a reason
    that `clash` (funnel.clash) lets through. Accessories already in it are kept."""
    if any(picks.get(s) for s in ACCESSORY_SLOTS):
        return picks
    out = dict(picks)
    for slot, ids in _candidates(ctx, priority, keeps, widen).items():
        for iid in ids:
            trial = {**out, slot: iid}
            if reason(slot, ctx.wd.by_item[iid], ctx.day, out) and not clash(ctx, trial):
                out = trial
                break
    return out
