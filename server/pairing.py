"""
pairing.py — the funnel's steps 6-8: what goes together (user, 2026-10-20).

Each rule reads the outfit chosen so far and says whether it still holds: trousers
and shoes as smart as the top, knit over the right collar, the layers in the right
order, one accent colour, the belt with the shoes. funnel.clash asks them in order;
the relax ladder can give each one up. Split from funnel.py at the 600-line ceiling.
"""
from typing import TYPE_CHECKING

import check
import garment
import style

if TYPE_CHECKING:
    from funnel import Ctx

VISIBLE = ("base", "mid", "outer", "bottoms", "footwear")
_COLLARED = frozenset({"polo", "shirt", "blouse", "blazer", "waistcoat"})
# What a chunky knit goes over: a tee (short or long sleeved), a button-up shirt — and
# a dress, which a heavy jumper over it is an ordinary way to wear.
_UNDER_CHUNKY = frozenset({"t_shirt", "shirt", "dress"})
_BROWN = ("brown", "tan", "cognac", "chocolate", "camel", "chestnut", "茶")
_BLACK = ("black", "黒")


def _items(ctx: "Ctx", picks: dict, slots) -> list[dict]:
    return [ctx.wd.by_item[picks[s]] for s in slots if picks.get(s)]


_KNITS = frozenset({"sweater", "cardigan", "hoodie", "fleece"})
_TOPS_ONLY_UNDER = frozenset({"t_shirt", "polo", "tank", "blouse", "shirt"})


def top_over_knit(ctx: "Ctx", picks: dict) -> bool:
    """A tee, polo, tank, blouse or shirt over knitwear: the layers in the wrong order
    (pre-push gate, 2026-10-20: a polo as mid over a sweater as base; a short-sleeved
    shirt as outer over a cardigan as mid)."""
    layered = [ctx.wd.by_item[picks[s]] for s in ("base", "mid", "outer") if picks.get(s)]
    return any(lo.get("type") in _KNITS and hi.get("type") in _TOPS_ONLY_UNDER
               for k, lo in enumerate(layered) for hi in layered[k + 1:])


def _register(ctx: "Ctx", picks: dict) -> bool:
    """Trousers and shoes as smart as the top, within one step; utility trousers
    never with a collar or a fine knit (style.LOOK_PRINCIPLES)."""
    # The outer layer counts when it is a top or tailoring (a blazer, an open oxford);
    # a commute coat does not (pre-push gate, 2026-10-20).
    outer = [o for o in _items(ctx, picks, ("outer",)) if not check.is_coat(o)]
    tops = [*_items(ctx, picks, ("base", "mid")), *outer]
    legs = _items(ctx, picks, ("bottoms", "footwear"))
    if not tops or not legs:
        return True
    if min(garment.level(i) for i in legs) < max(garment.level(i) for i in tops) - 1:
        return False
    trousers = ctx.wd.by_item.get(picks.get("bottoms")) or {}
    return not (garment.utility_trousers(trousers) and any(
        t.get("type") in _COLLARED or garment.gauge(t) in ("fine", "mid") for t in tops))


def _texture(ctx: "Ctx", picks: dict) -> bool:
    """A polo goes under a fine-gauge sweater or a cardigan, never a heavier knit
    (user, 2026-10-18: "Fabric of polo and sweater doesn't go well"); a chunky knit
    goes over a tee, a button-up shirt or a dress only; a shirt worn open
    as a layer goes over a tee or a tank, never over another collar."""
    # Every lower/upper pair of the layers, not only against the base: a knit in mid
    # is what an outer layer sits on (pre-push gate, 2026-10-20).
    layered = _items(ctx, picks, ("base", "mid", "outer"))
    return not any((u.get("type") == "polo" and o.get("type") == "sweater" and garment.gauge(o) != "fine")
                   or (garment.gauge(o) == "chunky" and u.get("type") not in _UNDER_CHUNKY)
                   or (o.get("type") in ("shirt", "blouse") and u.get("type") not in ("t_shirt", "tank"))
                   for k, u in enumerate(layered) for o in layered[k + 1:])


def _colour(ctx: "Ctx", picks: dict) -> bool:
    """Neutrals and at most one accent colour; at most one patterned garment."""
    seen = _items(ctx, picks, VISIBLE)
    accents = {a for i in seen if (a := style.accent_of(i))}
    busy = [i for i in seen if style.pattern_of(i) not in (None, "solid")]
    return len(accents) <= 1 and len(busy) <= 1


def _family(item: dict) -> str | None:
    c = " ".join(str(x).lower() for x in item.get("colors") or [])
    return "brown" if any(w in c for w in _BROWN) else "black" if any(w in c for w in _BLACK) else None


def _belt(ctx: "Ctx", picks: dict) -> bool:
    """A leather belt matches leather shoes: brown with brown, black with black."""
    belt = ctx.wd.by_item.get(picks.get("accessories")) or {}
    shoes = ctx.wd.by_item.get(picks.get("footwear")) or {}
    leather = garment.material(belt) in (None, "leather") and garment.material(shoes) == "leather"
    if belt.get("type") != "belt" or not leather:
        return True
    a, b = _family(belt), _family(shoes)
    return a is None or b is None or a == b


PAIRS = (("register", _register), ("texture", _texture), ("colour", _colour), ("belt", _belt))
