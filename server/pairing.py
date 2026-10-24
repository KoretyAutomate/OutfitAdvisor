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
# Knitted tops: a polo is knitted however fine (user, 2026-10-23).
_KNIT_TOPS = frozenset({"polo", *garment.KNITS})
_BROWN = ("brown", "tan", "cognac", "chocolate", "camel", "chestnut", "茶")
_BLACK = ("black", "黒")


def _items(ctx: "Ctx", picks: dict, slots) -> list[dict]:
    return [ctx.wd.by_item[picks[s]] for s in slots if picks.get(s)]


KNITWEAR = frozenset({"sweater", "cardigan", "hoodie", "fleece"})
_TOPS_ONLY_UNDER = frozenset({"t_shirt", "polo", "tank", "blouse", "shirt"})


def top_over_knit(ctx: "Ctx", picks: dict) -> bool:
    """A tee, polo, tank, blouse or shirt over knitwear: the layers in the wrong order
    (pre-push gate, 2026-10-20: a polo as mid over a sweater as base; a short-sleeved
    shirt as outer over a cardigan as mid)."""
    layered = [ctx.wd.by_item[picks[s]] for s in ("base", "mid", "outer") if picks.get(s)]
    return any(lo.get("type") in KNITWEAR and hi.get("type") in _TOPS_ONLY_UNDER
               for k, lo in enumerate(layered) for hi in layered[k + 1:])


def _register(ctx: "Ctx", picks: dict) -> bool:
    """Trousers, shoes and the coat as smart as the top, within one step; utility
    trousers never with a collar or a fine knit (style.LOOK_PRINCIPLES)."""
    # The outer layer counts when it is a top or tailoring (a blazer, an open oxford);
    # a commute coat does not (pre-push gate, 2026-10-20).
    outer = [o for o in _items(ctx, picks, ("outer",)) if not check.is_coat(o)]
    tops = [*_items(ctx, picks, ("base", "mid")), *outer]
    if not tops:
        return True
    smartest = max(garment.level(i) for i in tops)
    # The coat too, now: no more than a step below the top (user, 2026-10-24 — a puffer
    # over a blazer). A parka over a smart-casual knit is a step, and the chooser's eye.
    coats = [o for o in _items(ctx, picks, ("outer",)) if check.is_coat(o)]
    if any(garment.level(o) < smartest - 1 for o in coats):
        return False
    legs = _items(ctx, picks, ("bottoms", "footwear"))
    if not legs:
        return True
    if min(garment.level(i) for i in legs) < smartest - 1:
        return False
    trousers = ctx.wd.by_item.get(picks.get("bottoms")) or {}
    return not (garment.utility_trousers(trousers) and any(
        t.get("type") in _COLLARED or garment.gauge(t) in ("fine", "mid") for t in tops))


def _texture(ctx: "Ctx", picks: dict) -> bool:
    """No knit on knit: a polo, sweater or cardigan never goes under a sweater or a
    cardigan, however fine (user, 2026-10-18: "Fabric of polo and sweater doesn't go
    well"; 2026-10-23: "Do you think any fashion advisor would allow Knit on knit
    combination?" — a knit polo under a waffle cardigan). A turtleneck under a
    cardigan is the one exception. A chunky knit goes over a tee, a button-up shirt or
    a dress only; a shirt worn open as a layer goes over a tee or a tank, never over
    another collar."""
    # Every lower/upper pair of the layers, not only against the base: a knit in mid
    # is what an outer layer sits on (pre-push gate, 2026-10-20).
    layered = _items(ctx, picks, ("base", "mid", "outer"))
    return not any(_knit_on_knit(u, o)
                   or (garment.gauge(o) == "chunky" and u.get("type") not in _UNDER_CHUNKY)
                   or (o.get("type") in ("shirt", "blouse") and u.get("type") not in ("t_shirt", "tank"))
                   for k, u in enumerate(layered) for o in layered[k + 1:])


def _knit_on_knit(under: dict, over: dict) -> bool:
    if over.get("type") not in garment.KNITS or under.get("type") not in _KNIT_TOPS:
        return False
    return not (garment.turtleneck(under) and over.get("type") == "cardigan")


def _colour(ctx: "Ctx", picks: dict) -> bool:
    """Neutrals and at most one accent colour; at most one patterned or textured
    garment."""
    seen = _items(ctx, picks, VISIBLE)
    accents = {a for i in seen if (a := style.accent_of(i))}
    # A marl or waffle knit is as busy as a print beside one (user, 2026-10-24: "Pattern
    # shirt x kind of patterned knit looks off to me").
    busy = [i for i in seen if style.pattern_of(i) not in (None, "solid") or garment.textured(i)]
    return len(accents) <= 1 and len(busy) <= 1


def _family(item: dict) -> str | None:
    c = " ".join(str(x).lower() for x in item.get("colors") or [])
    return "brown" if any(w in c for w in _BROWN) else "black" if any(w in c for w in _BLACK) else None


def _belt(ctx: "Ctx", picks: dict) -> bool:
    """A leather belt matches leather shoes: brown with brown, black with black. A
    belt in an accent colour shares it with the shoes, whatever they are made of
    (user, 2026-10-24: a red leather belt with grey mesh sneakers)."""
    belt = ctx.wd.by_item.get(picks.get("accessories")) or {}
    shoes = ctx.wd.by_item.get(picks.get("footwear")) or {}
    if belt.get("type") == "belt" and shoes and (a := style.accent_of(belt)) and style.accent_of(shoes) != a:
        return False
    leather = garment.material(belt) in (None, "leather") and garment.material(shoes) == "leather"
    if belt.get("type") != "belt" or not leather:
        return True
    a, b = _family(belt), _family(shoes)
    return a is None or b is None or a == b


PAIRS = (("register", _register), ("texture", _texture), ("colour", _colour), ("belt", _belt))
