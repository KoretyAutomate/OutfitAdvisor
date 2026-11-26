"""
fit.py — whether an outfit fits the day as a whole, for funnel's rank (user,
2026-10-24): the layers the morning needs and no more, the undershirt where it goes,
a top under the coat. Split from funnel.py at the 600-line ceiling.
"""
import dataclasses
from typing import TYPE_CHECKING

import check
import layers
import pairing
import scale

if TYPE_CHECKING:
    import funnel


def layering(ctx: "funnel.Ctx", picks: dict) -> int:
    """The layers do not fit the day (user, 2026-10-24: "Coat over the top"). On a cold
    morning: no coat; or a knit under it where the coat alone is warm enough, or none
    where it is not (always knit and coat below layers.KNIT_AND_COAT_BELOW_C). On a
    milder one: a knit AND a jacket where either alone is warm enough."""
    wd, plan = ctx.wd, ctx.day.plan
    mid, outer = (wd.by_item.get(picks.get(s)) for s in ("mid", "outer"))
    if plan < layers.COAT_BELOW_C:
        if not outer:
            return 1
        # Knitwear under the coat — in mid, or as the top itself — is the warmth
        # between: a shirt open over a tee is not (2026-10-24; Codex review: a sweater
        # worn as the top was ranked down and moved into mid over nothing).
        base = wd.by_item.get(picks.get("base")) or {}
        if check.is_coat(outer) and layers.coat_alone(outer, plan):
            # Extra only as a layer BETWEEN: a sweater that is the only top stays on
            # (pre-push gate, 2026-10-24 — the parka went over the undershirt alone).
            # A cardigan with nothing under it is the top, too.
            return int(bool(mid) and bool(base) and mid.get("type") in pairing.KNITWEAR)
        return int((mid or base).get("type") not in pairing.KNITWEAR)
    return int(bool(mid and outer) and (scale.warm_enough(mid, plan) or scale.warm_enough(outer, plan)))


def underlayered(ctx: "funnel.Ctx", picks: dict) -> bool:
    """Below layers.KNIT_AND_COAT_BELOW_C, a coat with no knitwear under it (in mid, or
    as the top). The weather, not a preference: ranked with wet feet, ahead of every
    rule the search may give up (user, 2026-11-26: a tee under the duffle coat at 2C,
    "How can it recommend an outfit without a sweater"). Served only when no outfit
    in the closet has the knit — and never when they own no knit they could wear today,
    or every outfit would be held aside for one that is not there (Codex review,
    2026-11-26; the same posture as funnel.Ctx.dry)."""
    wd = ctx.wd
    outer = wd.by_item.get(picks.get("outer"))
    if ctx.day.plan >= layers.KNIT_AND_COAT_BELOW_C or not outer:
        return False
    mid, base = (wd.by_item.get(picks.get(s)) or {} for s in ("mid", "base"))
    return (mid.get("type") not in pairing.KNITWEAR and base.get("type") not in pairing.KNITWEAR
            and _knit_wearable(ctx))


def _knit_wearable(ctx: "funnel.Ctx") -> bool:
    """A knit they could wear under the coat today, with every rule the search may give
    up given up: kept on the request's Day, like season's and accessories' memos."""
    import funnel   # funnel imports this module
    memo: dict = ctx.day.memo.setdefault("fit.knit", {})
    if ctx.target not in memo:
        loose = dataclasses.replace(ctx, relaxed=frozenset(funnel.RELAX))
        memo[ctx.target] = any(
            ctx.wd.by_item[i].get("type") in pairing.KNITWEAR and funnel._keeps(loose, s, i, 4) is None
            for i in ctx.wd.ids for s in ("mid", "base") if s in (ctx.wd.by_roles.get(i) or ()))
    return memo[ctx.target]


def bare(ctx: "funnel.Ctx", picks: dict, cands: dict) -> int:
    """The undershirt's slot is decided, empty, something could fill it, and the top
    takes one — never a T-shirt (check.tee_base)."""
    return int("inner" in picks and not picks["inner"] and bool(cands.get("inner"))
               and not check.tee_base(picks, ctx.wd.by_item))


def topless(picks: dict, today: frozenset) -> int:
    """No top where one fits: an empty base that something could fill, or nothing at
    all between the undershirt and the coat while a mid layer could be worn (pre-push
    gate, 2026-10-24 — a parka over the undershirt alone beat the only cardigan)."""
    return int(not picks.get("base") and ("base" in today or (not picks.get("mid") and "mid" in today)))
