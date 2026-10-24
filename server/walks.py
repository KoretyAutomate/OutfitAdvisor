"""
walks.py — the two ways funnel.search goes through combinations: the beam (fast,
the best few hundred partial outfits after each slot) and the exact walk.

Every combination, before a rule gives way (user, 2026-10-23):

"We need to make sure the selection is nothing violating the rule. If there is truly
no combination which does that, it needs to mention that in the commentary. I don't
care if it takes 10 minutes to pick, it must try all the possible combinations."

The beam is fast and nearly always right; at the end of each ladder step
where it found nothing, or only outfits that give rules up, exact() walks every
combination the step's rules allow, for any that gives up less. Split from funnel.py
at the 600-line ceiling; it reads funnel's names at call time, so a test that
monkeypatches funnel.WIDTHS reaches it too.
"""
import time

import check
import fit
import funnel
import layers


def _partial(ctx: "funnel.Ctx", picks: dict, priority) -> float:
    worn = [(sl, i) for sl, i in picks.items() if i and sl != "accessories"]
    return sum(priority(i, sl) for sl, i in worn) / max(1, len(worn)) + funnel._accessory(ctx, picks)


def beam(ctx: "funnel.Ctx", cands: dict, order: list, priority, shape: tuple = ()) -> list:
    """Slot by slot, the most constrained first: every candidate that goes with what
    is already chosen, keeping the BEAM best partial outfits after each slot. Wide
    where a depth-first walk is deep — it sees every first choice, not one."""
    partials: list = [{}]
    # Warm enough is a fact of the whole torso (check.py's cold issue): judged the
    # moment the torso is complete, so the beam never fills up with outfits that can
    # only fail at the end.
    warm = funnel._warm_fixable(ctx)
    for slot in order:
        if time.monotonic() > ctx.deadline:
            return []
        opts = list(cands.get(slot) or ())
        # An optional slot may stay empty; so may a required one they own nothing
        # for, which is a gap (gaps.py), not a reason to dress nobody; and so may the
        # top under a layer, which can be the top itself (a cardigan alone) — check.py
        # judges whether that dresses them, the rank prefers a top where one fits.
        # Not in the one-piece pass (no trousers in its order): there the base IS the legs.
        if slot in funnel.OPTIONAL or not opts or (slot == "base" and len(shape) > 1 and "bottoms" in order):
            opts.append(None)
        nxt = []
        for p in partials:
            for iid in opts:
                if iid and iid in p.values():
                    continue
                trial = {**p, slot: iid}
                if iid and funnel.clash(ctx, trial):
                    continue
                # Judged once the undershirt is decided too — it is the first optional slot,
                # after every layer — since it adds warmth (pre-push gate, 2026-10-21).
                if warm and slot == "inner" and not layers._still_warm(trial, ctx.wd.by_item, ctx.day.plan):
                    continue
                nxt.append(trial)
        # Once the undershirt's or the top's slot is decided, outfits with one go ahead
        # of those without, before the cut — the rank puts them first, so must the beam.
        nxt.sort(key=lambda q: (funnel._repeats(ctx, q), fit.bare(ctx, q, cands),
                                _left_off(q, "base", cands), -_partial(ctx, q, priority), funnel.key(q)))
        partials = nxt[:funnel._width(ctx)[1]]
    return partials


def _left_off(q: dict, slot: str, cands: dict) -> int:
    """This slot is decided, left empty, and something could have filled it."""
    return int(slot in q and not q[slot] and bool(cands.get(slot)))


class _OutOfTime(Exception):
    """The deadline passed in the middle of a walk."""


def _walk(ctx: "funnel.Ctx", cands: dict, order: list, visit, worse=None, prune_cold: bool = True) -> None:
    """Every combination, slot by slot, depth first: each candidate that goes with what
    is already chosen, and visit(picks) on every complete outfit. A branch is cut only
    where a rule in force is broken — no garment added later mends a broken pair — so
    nothing that keeps the rules is skipped. The same choices as beam(), without its cut.
    `worse(picks)`: a branch that can only end worse than what is already in hand.
    Raises _OutOfTime past ctx.deadline. `prune_cold`: cut a torso no garment makes
    warm where _warm_fixable guesses one could — the guess exact() drops when it
    finds nothing at all."""
    warm = prune_cold and funnel._warm_fixable(ctx)
    opts: list = []
    # A layer in the order is a shape with more than the base (beam()'s len(shape) > 1).
    layered = "mid" in order or "outer" in order
    for slot in order:
        o = list(cands.get(slot) or ())
        if slot in funnel.OPTIONAL or not o or (slot == "base" and layered and "bottoms" in order):
            o.append(None)
        opts.append(o)
    steps = [0]

    def go(n: int, picks: dict) -> None:
        if n == len(order):
            visit(picks)
            return
        steps[0] += 1
        if not steps[0] % 256 and time.monotonic() > ctx.deadline:
            raise _OutOfTime
        slot, worn = order[n], set(picks.values())
        for iid in opts[n]:
            if iid and iid in worn:
                continue
            trial = {**picks, slot: iid}
            if iid and (funnel.clash(ctx, trial) or (worse and worse(trial))):
                continue
            if warm and slot == "inner" and not layers._still_warm(trial, ctx.wd.by_item, ctx.day.plan):
                continue
            go(n + 1, trial)
    go(0, {})


def _bare_for_sure(ctx: "funnel.Ctx", cands: dict, order: list) -> bool:
    """No outfit of this walk can pass check.py: trousers or shoes have nothing to wear
    under these rules though they own some (check._dressed's no-bottoms / no-footwear,
    hard), and nothing that could change that is worn elsewhere in the walk. Without
    it an office day whose only trousers sit below the band walks millions of outfits
    with bare legs (2026-10-23: 2.8M, six minutes, on 87 garments)."""
    for slot in ("bottoms", "footwear"):
        if slot not in order or cands.get(slot):
            continue
        could = {i for i in ctx.wd.ids if slot in (ctx.wd.by_roles.get(i) or ())}
        elsewhere = any(i in could for s in order if s != slot for i in cands.get(s) or ())
        if not elsewhere and ctx.day.owns_for(slot, {}):
            return True
    return False


def exact(ctx: "funnel.Ctx", priority, bound: tuple | None = None, cold_too: bool = False) -> tuple[list, int, bool]:
    """(outfits, reached, finished): every combination the rules in ctx allow, for the
    outfits that give up the least (funnel.cost of funnel.needed()) — strictly less than
    `bound` when given, the cost of what the beam already has. Branch and bound: what
    a partial outfit gives up only grows as garments are added, so a branch already
    past the best in hand is cut, never one that could still beat it. Every outfit at
    the best cost is checked against check.issues, up to CHECKED_CAP of them; after
    that the walk goes on only where something strictly better could be.
    finished=False only when the deadline cut it (Codex review, 2026-10-23).
    `cold_too`: the outfits no garment makes warm as well, for search's last resort."""
    ctx = funnel.Ctx(ctx.day, ctx.target, ctx.relaxed, ctx.exclude, len(funnel.WIDTHS), ctx.deadline)
    cands, _ = funnel.candidates(ctx, priority)
    today = frozenset(s for s, ids in cands.items() if ids)
    ok: list = []
    cold: list = []
    seen: set = set()
    reached = [0]
    # The best cost in hand, and whether outfits AT it are still wanted.
    best: list = [bound, bound is None]

    def worse(p: dict) -> bool:
        if best[0] is None:
            return False
        c = funnel.cost(funnel.needed(ctx, p))
        return c > best[0] or (c == best[0] and not best[1])

    onepieces = [i for i in cands["base"] if ctx.wd.by_group.get(i) == "onepiece"]
    dress_owned = any(ctx.wd.by_group.get(i) == "onepiece" and "base" in (ctx.wd.by_roles.get(i) or ())
                      and funnel._keeps(ctx, "base", i, 4) is None for i in ctx.wd.ids)

    def every(prune_cold: bool) -> None:
        for shape in funnel.SHAPES:
            if ctx.day.plan >= check.HOT_DAY_C and shape != ("base",):
                continue
            for one in (False, True) if onepieces else (False,):
                if dress_owned and not one and not cands["bottoms"]:
                    continue
                c = {**cands, "base": onepieces if one else [i for i in cands["base"] if i not in onepieces]}
                order = funnel._order(shape, c, one)
                if _bare_for_sure(ctx, c, order):
                    continue

                def visit(p: dict, shape: tuple = shape) -> None:
                    reached[0] += 1
                    full = funnel._full(p)
                    if funnel.look(p) in ctx.exclude or funnel.key(full) in seen or worse(full):
                        return
                    seen.add(funnel.key(full))
                    got = funnel._evaluate(ctx, [(shape, p)], priority, today)
                    if not got:
                        return
                    if got[0].rank[0]:
                        # Cold: the best CHECKED_CAP by rank, for a closet with nothing
                        # warm — never a bound (pre-push gate, 2026-10-24: the first
                        # sixty hid one breaking fewer rules).
                        cold.extend(got)
                        cold.sort(key=lambda o: (o.rank, -o.score, funnel.key(o.picks)))
                        del cold[funnel.CHECKED_CAP:]
                        return
                    c = funnel.cost(got[0].relaxed)
                    if best[0] is None or c < best[0]:
                        best[0], best[1] = c, True
                        ok[:] = [o for o in ok if funnel.cost(o.relaxed) <= c]
                    ok.extend(got)
                    if len(ok) >= funnel.CHECKED_CAP:
                        best[1] = False
                _walk(ctx, c, order, visit, worse, prune_cold)

    try:
        # `cold_too`: search's last resort, once no step of the ladder found anything
        # warm — the cold-torso cut rests on a guess that a warmer garment fits, and
        # only this walk can say it does not. Never earlier: walking every cold
        # combination at each step spent the time a warm outfit needed (pre-push gate,
        # 2026-10-24).
        every(not cold_too)
    except _OutOfTime:
        return ok + cold, reached[0], False
    return ok + cold, reached[0], True
