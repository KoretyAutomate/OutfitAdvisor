"""
fallback.py — the last resort, when the advisor has had its revisions and its best
answer still breaks a hard fact (2026-10-11 refactor).

A small SEARCH, not a sequence of repairs. It started as one ordered function of
steps — unstack, cool down, cover, warm up — and the pre-push review found the same
shape of hole again and again: one step undoing another, or a fix that needed two
changes at once (a tee for the hot sweater AND a cardigan over it). A fixed order
cannot see a combination; a search can.

From the model's own outfit it tries changing one garment at a time, up to DEPTH
changes, keeping the BEAM best at each depth, and returns the best outfit seen,
ranked by the same facts check.py reports:

    0. none of their rules broken — absolute, never traded for anything below
    1. least undressed    (no top, trousers or shoes they own — dressed beats comfortable)
    2. fewest hard issues (cold, overheated, stacked, their rules, snow gear …)
    3. a top in base      (not a lone layer filed as mid)
    4. fewest changes     (the model chose; change as little of it as possible)
    5. fewest soft issues

Reached rarely: the model is told every issue first (advisor.dress).
"""
import rules
from check import Day, hard, issues
from vocab import CATEGORIES

DEPTH = 3
BEAM = 12
_UNDRESSED = frozenset({"no-top", "inner-alone", "no-bottoms", "no-footwear"})


def fix(picks: dict, day: Day) -> tuple[dict, dict]:
    """(picks, changed) where `changed` maps each slot touched to what it holds now."""
    wd = day.wd
    start = {c: picks.get(c) for c in CATEGORIES}
    # What can never stand, whatever else happens: an id not in the wardrobe, one
    # garment in two places, a garment in a slot it cannot be worn as.
    seen_ids: set = set()
    for slot, iid in start.items():
        if iid and (iid not in wd.ids or iid in seen_ids or slot not in (wd.by_roles.get(iid) or ())):
            start[slot] = None
        elif iid:
            seen_ids.add(iid)
    # Their rules are absolute — never traded for coverage or warmth: the blamed
    # garment of each broken rule comes off before the search starts, and the
    # search ranks any rule broken above everything else. Raised by the pre-push
    # reviewer, 2026-10-11.
    for _ in CATEGORIES:
        broken = rules.violations(day.rules, start, wd.by_item)
        if not broken:
            break
        start[broken[0]["slot"]] = None
    best, best_rank = start, _rank(start, picks, day)
    beam, visited = [start], {_key(start)}
    # Deep enough to fix every hard issue one change at a time, however many slots
    # need it (four white garments under a no-white rule).
    depth = min(len(CATEGORIES), DEPTH + len(hard(issues(start, day))))
    for _ in range(depth):
        if best_rank[:4] == (0, 0, 0, 0):
            break
        nxt, fresh = [], set()
        for p in beam:
            for q in _moves(p, day):
                k = _key(q)
                if k not in visited and k not in fresh:
                    fresh.add(k)
                    nxt.append((_rank(q, picks, day), hard(issues(q, day)), q))
        if not nxt:
            break
        nxt.sort(key=lambda r: r[0])
        # Diverse first: the best outfit for each distinct set of unresolved issues,
        # then the rest by rank. Otherwise fifty equivalent sweater swaps fill the
        # beam and prune the one different path (the tee, then a layer). Raised by
        # the pre-push reviewer, 2026-10-11.
        seen_sigs: set = set()
        first, rest = [], []
        for r in nxt:
            sig = frozenset(r[1])
            (rest if sig in seen_sigs else first).append(r)
            seen_sigs.add(sig)
        beam = [q for _, _, q in (first + rest)[:BEAM]]
        # Only what is KEPT is marked: an outfit pruned at this depth may be the one
        # step a later path needs. Raised by the pre-push reviewer, 2026-10-11.
        visited |= {_key(q) for q in beam}
        if nxt[0][0] < best_rank:
            best_rank, best = nxt[0][0], nxt[0][2]
    return best, {s: best.get(s) for s in CATEGORIES if best.get(s) != picks.get(s)}


def _rank(p: dict, original: dict, day: Day) -> tuple:
    found = issues(p, day)
    h = hard(found)
    wd = day.wd
    # Legs a dress covered stay covered: bare legs count as undressed even when they
    # own no trousers to put on.
    bare_legs = int(not p.get("bottoms") and wd.by_group.get(p.get("base")) != "onepiece"
                    and wd.by_group.get(original.get("base")) == "onepiece")
    # A layer worn over nothing reads as a misfiled outfit ("Mid layer: knit polo"):
    # the top belongs in base.
    misfiled = int(not p.get("base") and any(p.get(c) for c in ("mid", "outer")))
    changes = sum(1 for c in CATEGORIES if p.get(c) != original.get(c))
    broken = sum(1 for k in h if k.startswith("rule-"))
    return (broken, len(h & _UNDRESSED) + bare_legs, len(h), misfiled, changes,
            sum(1 for i in found if not i.hard))


def _moves(p: dict, day: Day):
    """Every outfit one garment away: a slot emptied, or filled with an unused garment
    that can be worn there. A dress in `base` takes the trousers off in the same move."""
    wd = day.wd
    worn = {i for i in p.values() if i}
    for slot in CATEGORIES:
        if p.get(slot):
            yield {**p, slot: None}
        for iid in sorted(wd.ids):
            if iid in worn or slot not in (wd.by_roles.get(iid) or ()):
                continue
            q = {**p, slot: iid}
            if slot == "base" and wd.by_group.get(iid) == "onepiece":
                q["bottoms"] = None
            yield q


def _key(p: dict) -> tuple:
    return tuple(p.get(c) for c in CATEGORIES)
