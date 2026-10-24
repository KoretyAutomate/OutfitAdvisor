"""
funnel.py — code narrows the wardrobe; the model only chooses among what survives
(user, 2026-10-20).

User: "I personally feel narrowing down the options through out the flow is better
... occasion removes certain items, weather removes additional items, temperature
further narrows down with layering options, rotation defines priority ... remove
options which don't go well ... if nothing remains, go back and try second
priority". Agreed with three amendments: the pairing steps prune PAIRS against what
is already chosen, never items outright; every filter is absolute or relaxable, and
a relaxed one leaves a note; the model chooses among the top few and writes the
words (advisor._dress_funnel).

Why: the model used to fill every slot at once and check.py could only complain
afterwards — a 2/5 and a 3/5 were served (2026-10-18 10:29 / 10:35, 2026-10-20).

    1 the day ─ 2 occasion band ─ 3 weather ─ 4 layer shapes ─ 5 priority
      ─ 6-8 slot-by-slot search, pairs pruned ─ 9 relax ladder ─ 10 rank, top K
      ─ 11 check.issues: no hard issue, ever

check.py stays the one fact check: every outfit this returns has passed it, so a
funnel answer can never carry a hard issue the old path would have caught.
"""
import math
import time
from dataclasses import dataclass, field

import check
import garment
import layers
import pairing
import rules
import scale
import sleeves
import style
import walks
from llm import log
from vocab import CATEGORIES

K = 4                   # outfits the model chooses among
# (candidates per slot, partial outfits kept after each slot): the narrow pass first,
# the wide one only when it found nothing — before any rule gives way, so a legal
# outfit is never lost to a cap (pre-push reviewer, 2026-10-20).
# The last width takes every candidate: a strict outfit beyond the first sixteen is
# found before any rule gives way (pre-push reviewer, 2026-10-20).
WIDTHS = ((6, 120), (16, 400), (None, 400))
# Every candidate, no beam: the walk that settles whether ANY outfit keeps a step's
# rules before the next one gives way (user, 2026-10-23: "it must try all the
# possible combinations"). The beam is fast and nearly always right; this is the proof.
EXHAUSTIVE = (None, None)
CHECKED_CAP = 60        # complete outfits that pass check.issues, at most
VISIBLE = pairing.VISIBLE
OPTIONAL = ("inner", "accessories")
# Most constrained first, and on a tie the slots a stylist anchors on.
_TIE = ("footwear", "bottoms", "base", "mid", "outer")
# What a pass may give up, in order, when nothing survives. Their rules, the stacking
# and sleeve rules, warmth and heat are never on it. Trousers that match the top come
# before the day's level: a coherent outfit two steps down beats a smart top over
# cargo trousers (user, 2026-10-22).
RELAX = ("colour", "belt", "texture", "wet", "band1", "band2", "register", "band3", "snow", "coat")
# "snow" and "coat" last: they only give way where a pairing rule of theirs makes the
# gear unwearable with everything else — check.py then asks for nothing either.
NOTES = {
    "colour": "colours a little busier than usual — nothing quieter fits today",
    "belt": "the belt and shoes are different leathers — nothing matching is free today",
    "texture": "the knit and the top are not the ideal pairing — nothing better is free today",
    "wet": "nothing water-resistant to wear on your feet today — expect damp shoes in the rain",
    "register": "the trousers or shoes don't match the top — nothing that does is free today",
    # Either way off — too relaxed or too dressy (pre-push gate, 2026-10-20).
    "band1": "a step off the day's usual dress level — nothing at it is free today",
    "band2": "well off the day's usual dress level — little at it is free today",
    "band3": "well off the day's usual dress level — little at it is free today",
}
TRIED_ALL = "every combination of what you can wear today was tried, and none keeps every rule"
COATLESS_C = 14         # felt: warm enough at midday to carry the coat
SHAPES = (("base",), ("base", "mid"), ("base", "outer"), ("base", "mid", "outer"))


def target_level(look: "style.Look") -> int:
    """Step 1: how dressed-up today is, 1-5."""
    if look.style == "active":
        return 1
    return min(5, {"office": 3}.get(look.occasion, 2) + (1 if look.style == "smart" else 0))


def band(slot: str, target: int, office: bool, widen: int) -> tuple[int, int]:
    """Step 2: the levels a visible garment may have. Never below the office's level
    on an office day; a coat is commute wear and gets more room either way."""
    if slot == "outer":
        return target - 1 - widen, target + 2 + widen
    return target - (0 if office else 1) - widen, target + 1 + widen


@dataclass
class Ctx:
    """One request: the day, the target level, the relaxations in force."""

    day: "check.Day"
    target: int
    relaxed: frozenset = frozenset()
    exclude: frozenset = frozenset()     # looks (funnel.look) the model already turned down
    width: int = 0                       # index into WIDTHS
    # time.monotonic() by which the search stops, whatever it has (pre-push gate,
    # 2026-10-21: a 92-garment closet with 24 rules searched past the phone's 90 s).
    deadline: float = math.inf

    @property
    def wd(self):
        return self.day.wd

    @property
    def office(self) -> bool:
        return self.day.look.occasion == "office"

    @property
    def wet(self) -> bool:
        w = self.day.w
        return (w.get("rain") or 0) >= 50 or bool(w.get("isRain"))


@dataclass
class Outfit:
    picks: dict
    score: float
    found: list
    shape: tuple
    relaxed: tuple = ()
    off: tuple = ()          # what comes off by midday, for the advice text
    # Ranked before the score, in this order (pre-push plan review, 2026-10-20; rules
    # first since 2026-10-23): fewer rules given up; a re-roll shows something else
    # wherever it can; the layers fit the day (_layering, 2026-10-24); they wear an
    # undershirt whenever one fits, never under a T-shirt.
    rank: tuple = ()

    @property
    def sheds(self) -> tuple:
        return self.off


@dataclass
class Result:
    outfits: list
    relaxed: tuple
    target: int
    removed: dict = field(default_factory=dict)   # stage -> count, for the log
    # False when the deadline stopped the search before it had tried every combination
    # of a step: the advice then says so instead of claiming nothing better exists.
    complete: bool = True
    exact: int = 0       # outfits the exhaustive walks reached, for the log


# ── steps 2-3: what each slot may hold today ─────────────────────────────────────

def _snow_gear(ctx: Ctx, slot: str) -> bool:
    """Snow, and they own something waterproof for this slot that they could wear
    today: then only that — check.snow_gear, the very demand check.py's snow issue
    makes, asked of the garment alone. A pairing rule that rules it out with the rest
    is met by relaxing "snow" last."""
    return bool(ctx.day.w.get("isSnow")) and slot in ("footwear", "outer") and bool(
        check.snow_gear(slot, {}, ctx.day))


def _coat_day(ctx: Ctx) -> bool:
    """A cold morning, and they own a coat they could wear out today: then the outer
    layer is a coat — the demand check.py's no-coat issue makes, so absolute here."""
    day, wd = ctx.day, ctx.wd
    outright = [r for r in day.rules if not rules.is_combination(r)]
    return day.plan < layers.COAT_BELOW_C and any(
        check.is_coat(it) and "outer" in (wd.by_roles.get(i) or ())
        and not rules.violations(outright, {"outer": i}, wd.by_item)
        and not layers.overdressed(it, "outer", wd, day.plan, day.peak, day.rules)
        for i, it in wd.by_item.items())


def _keeps(ctx: Ctx, slot: str, iid: str, widen: int) -> str | None:
    """Why this garment cannot be worn as `slot` today, or None. The reason names the
    stage, for the log."""
    day, it = ctx.day, ctx.wd.by_item[iid]
    if rules.violations([r for r in day.rules if not rules.is_combination(r)], {slot: iid}, ctx.wd.by_item):
        return "rules"
    if layers.overdressed(it, slot, ctx.wd, day.plan, day.peak, day.rules):
        return "heat"
    if day.plan >= check.HOT_DAY_C and slot in ("mid", "outer"):
        return "heat"
    snow = "snow" not in ctx.relaxed and _snow_gear(ctx, slot)
    if snow and not it.get("waterproof"):
        return "snow"
    if slot == "outer" and "coat" not in ctx.relaxed and _coat_day(ctx) and not check.is_coat(it):
        return "coat"
    if slot in VISIBLE and not (snow and it.get("waterproof")):
        lo, hi = band(slot, ctx.target, ctx.office, widen)
        if not lo <= garment.level(it) <= hi:
            return "occasion"
    if slot == "footwear" and ctx.wet and "wet" not in ctx.relaxed and garment.wets_through(it):
        return "wet"
    return None


def candidates(ctx: Ctx, priority) -> tuple[dict, dict]:
    """({slot: [ids, best first]}, {stage: removed}) — steps 2-3 and 5."""
    # band3 spans every level, 1-5, whatever the day's target: what they have is worn.
    widen = 4 if "band3" in ctx.relaxed else 2 if "band2" in ctx.relaxed else 1 if "band1" in ctx.relaxed else 0
    out: dict = {s: [] for s in CATEGORIES}
    removed: dict = {}
    for iid in sorted(ctx.wd.ids):
        for slot in ctx.wd.by_roles.get(iid) or ():
            why = _keeps(ctx, slot, iid, widen)
            if why:
                removed[why] = removed.get(why, 0) + 1
            else:
                out[slot].append(iid)
    return {slot: _mixed(ctx, _best_first(ids, slot, priority)) for slot, ids in out.items()}, removed


def _best_first(ids: list, slot: str, priority) -> list:
    return sorted(ids, key=lambda i: (-priority(i, slot), i))


def _mixed(ctx: Ctx, ranked: list) -> list:
    """The best few, taken a kind at a time: the best of each kind first, then
    the next best of each. Six sweaters must not crowd the only coat out of a slot."""
    kinds: dict = {}
    for i in ranked:
        kinds.setdefault(ctx.wd.by_item[i].get("type"), []).append(i)
    out: list = []
    per = _width(ctx)[0] or len(ranked)
    while len(out) < per and any(kinds.values()):
        out += [ids.pop(0) for ids in kinds.values() if ids][:per - len(out)]
    return out


# ── steps 6-8: what goes together (pairing.py) ────────────────────────────────────

def clash(ctx: Ctx, picks: dict) -> str | None:
    """The first pairing rule these picks break, or None. Absolute rules first."""
    wd, day = ctx.wd, ctx.day
    if rules.violations(day.rules, picks, wd.by_item):
        return "rules"
    ids = {i for i in picks.values() if i}
    if any(a in ids and b in ids for a, b in day.look.disliked):
        return "disliked"
    if (check.stacked(picks, wd.by_item) or sleeves.sleeve_clashes(picks, wd.by_item)
            or pairing.top_over_knit(ctx, picks) or (picks.get("inner") and check.tee_base(picks, wd.by_item))):
        return "stack"
    if wd.by_group.get(picks.get("base")) == "onepiece" and picks.get("bottoms"):
        return "onepiece"
    return next((k for k, ok in pairing.PAIRS if k not in ctx.relaxed and not ok(ctx, picks)), None)


def _order(shape: tuple, cands: dict, onepiece_only: bool) -> list[str]:
    """The shape's slots, the fewest candidates first; optional slots last."""
    need = [*shape, *(() if onepiece_only else ("bottoms",)), "footwear"]
    need.sort(key=lambda s: (len(cands.get(s) or ()), _TIE.index(s) if s in _TIE else 9))
    return [*need, *OPTIONAL]


def _warm_fixable(ctx: Ctx) -> bool:
    """They own a torso garment warm enough for the coldest hour that they could wear
    today: not banned outright, and not too warm for the slot (a warmth-5 sweater on a
    14-20C day warms nobody — pre-push gate, 2026-10-20)."""
    day, wd = ctx.day, ctx.wd
    outright = [r for r in day.rules if not rules.is_combination(r)]
    return any(scale.warm_enough(it, day.plan) and any(
        r in check.TORSO and not rules.violations(outright, {r: i}, wd.by_item)
        and not layers.overdressed(it, r, wd, day.plan, day.peak, day.rules) for r in wd.by_roles.get(i) or ())
        for i, it in wd.by_item.items())


def _width(ctx: Ctx) -> tuple:
    return WIDTHS[ctx.width] if ctx.width < len(WIDTHS) else EXHAUSTIVE


def _repeats(ctx: Ctx, picks: dict) -> int:
    """Shown garments a re-roll has not replaced, ranked before any cap so its promise
    survives the search's limits. A garment is replaced only when its slot now holds
    something else: worn in another slot it is the same look (the cardigan moved from
    mid to outer), and an emptied slot is not something else — leaving the undershirt
    off is no change (pre-push gate, 2026-10-21). So a garment nothing could replace
    counts the same in every outfit and decides nothing. A slot not yet decided counts
    only if the garment is worn."""
    worn = {i for i in picks.values() if i}
    return sum(1 for s, i in ctx.day.prefs.shown_map.items() if i in worn or (s in picks and not picks[s]))


def sheds(day: "check.Day", picks: dict) -> tuple:
    """What comes off by midday: the coat once the day warms by six degrees AND reaches
    a coatless 14, the knit once it reaches 18 — and only over a top that stays on.
    A -5 to 1C day warms by six and keeps the coat on (pre-push gate, 2026-10-20)."""
    if not picks.get("base"):
        return ()
    off: list = []
    for slot, warm in (("outer", day.peak >= day.plan + 6 and day.peak >= COATLESS_C), ("mid", day.peak >= 18)):
        rest = {s: i for s, i in picks.items() if s not in (*off, slot)}
        # …and what stays on is warm enough by itself at the warmest hour (pre-push
        # gate, 2026-10-21: a thin tee under a jacket at 8-14C keeps the jacket).
        if warm and picks.get(slot) and layers._still_warm(rest, day.wd.by_item, day.peak):
            off.append(slot)
    return tuple(off)


# ── step 5: priority ─────────────────────────────────────────────────────────────

def priority_for(ctx: Ctx):
    """(id, slot) -> how much they would want it today, higher first: days since
    worn (capped at a week; yesterday's strongly down), a habit for that slot, the
    exact level of the day — and what is already on screen when they asked for
    something else, well down."""
    prefs = ctx.day.prefs
    habits = {(p.get("slot"), p.get("id")) for p in prefs.prefers if isinstance(p, dict)}
    shown = prefs.shown_map
    cache: dict = {}

    def pri(iid: str, slot: str) -> float:
        if (iid, slot) not in cache:
            it = ctx.wd.by_item[iid]
            # A coat is worn day after day (user, 2026-10-21): rotation never moves it.
            ago = None if it.get("group") == "outerwear" else it.get("_ago")
            p = 7.0 if not isinstance(ago, int) else float(min(max(ago, 0), 7)) - (3 if ago <= 1 else 0)
            p += 2 if (slot, iid) in habits else 0
            p -= 6 if shown.get(slot) == iid else 0
            p += 1 if slot in VISIBLE and garment.level(it) == ctx.target else 0
            # A cardigan is knitwear before it is a coat: each garment a little ahead in
            # the slot it is filed under, so a lone layer reads as what it is.
            p += 1 if it.get("category") == slot else 0
            cache[(iid, slot)] = p
        return cache[(iid, slot)]
    return pri


# ── steps 9-11 ───────────────────────────────────────────────────────────────────

def needed(ctx: Ctx, picks: dict) -> tuple:
    """Which relaxations THIS outfit needed — judged against the strict day, so a
    note is only ever about something the served outfit actually gives up."""
    strict = Ctx(ctx.day, ctx.target)
    out = [k for k, ok in pairing.PAIRS if not ok(strict, picks)]
    shoes = ctx.wd.by_item.get(picks.get("footwear")) or {}
    if strict.wet and garment.wets_through(shoes):
        out.append("wet")
    worst = 0
    for slot in VISIBLE:
        iid = picks.get(slot)
        if iid and not (_snow_gear(strict, slot) and ctx.wd.by_item[iid].get("waterproof")):
            lo, hi = band(slot, ctx.target, strict.office, 0)
            lvl = garment.level(ctx.wd.by_item[iid])
            worst = max(worst, lo - lvl, lvl - hi)
    out += ["band1"] if worst == 1 else ["band2"] if worst == 2 else ["band3"] if worst > 2 else []
    return tuple(k for k in RELAX if k in out)


def cost(gave: tuple) -> tuple:
    """Fewer rules given up first; on a tie, the later on the ladder the worse — two
    steps off the level and a mismatch is worse than one step and the same mismatch
    (Codex review, 2026-10-22)."""
    return len(gave), tuple(sorted((RELAX.index(k) for k in gave), reverse=True))

def _full(picks: dict) -> dict:
    return {c: picks.get(c) for c in CATEGORIES}


def look(picks: dict) -> frozenset:
    """The garments worn, whatever slots they are filed in: one look on the person."""
    return frozenset(i for i in picks.values() if i)


def key(picks: dict) -> tuple:
    """An outfit as a sortable, hashable value: an empty slot is ""."""
    return tuple(picks.get(c) or "" for c in CATEGORIES)


def _pass(ctx: Ctx, priority) -> tuple[list, dict, frozenset]:
    """One search over every layer shape, with the relaxations in ctx: (outfits,
    removed per stage, the slots anything can be worn in today)."""
    cands, removed = candidates(ctx, priority)
    found: list = []
    onepieces = [i for i in cands["base"] if ctx.wd.by_group.get(i) == "onepiece"]
    # A dress they could wear today, filtered here or not: the legs are its, so a pass
    # without trousers never dresses them bare — the band widens first (2026-10-21).
    dress_owned = any(ctx.wd.by_group.get(i) == "onepiece" and "base" in (ctx.wd.by_roles.get(i) or ())
                      and _keeps(ctx, "base", i, 4) is None for i in ctx.wd.ids)
    for shape in SHAPES:
        if ctx.day.plan >= check.HOT_DAY_C and shape != ("base",):
            continue
        for one in (False, True) if onepieces else (False,):
            # Without trousers to wear, the legs are the dress's: no outfit leaves it off
            # for bare legs (pre-push gate, 2026-10-21).
            if dress_owned and not one and not cands["bottoms"]:
                continue
            c = {**cands, "base": onepieces if one else [i for i in cands["base"] if i not in onepieces]}
            found += [(shape, p) for p in walks.beam(ctx, c, _order(shape, c, one), priority, shape)]
    return found, removed, frozenset(s for s, ids in cands.items() if ids)


def _accessory(ctx: Ctx, picks: dict) -> float:
    """An accessory is worn for a reason, never for the points: a belt with trousers or
    jeans, a scarf, gloves or a hat on a cold morning. Anything else stays home."""
    it = ctx.wd.by_item.get(picks.get("accessories"))
    if not it:
        return 0.0
    legs = (ctx.wd.by_item.get(picks.get("bottoms")) or {}).get("type")
    if it.get("type") == "belt":
        return 0.5 if legs in ("trousers", "jeans") else -1.0
    return 0.5 if it.get("type") in ("scarf", "gloves", "hat") and ctx.day.plan < layers.COAT_BELOW_C else -1.0


def _score(ctx: Ctx, picks: dict, priority, liked) -> float:
    worn = [(s, i) for s, i in picks.items() if i and s != "accessories"]
    mean = sum(priority(i, s) for s, i in worn) / max(1, len(worn))
    ids = {i for _, i in worn}
    return mean + _accessory(ctx, picks) + sum(1.0 for a, b in liked if a in ids and b in ids)


def _over(ctx: Ctx, picks: dict) -> int:
    """More torso layers than the day allows — check.py's "layers", ahead of the cap."""
    n = sum(1 for s in ("inner", "base", "mid", "outer") if picks.get(s))
    return int(n > layers.max_layers(picks, ctx.wd.by_item, ctx.day.plan))


def _layering(ctx: Ctx, picks: dict) -> int:
    """The layers do not fit the day (user, 2026-10-24: "Coat over the top"). On a cold
    morning: no coat; or a knit under it where the coat alone is warm enough, or none
    where it is not (always knit and coat below layers.KNIT_AND_COAT_BELOW_C). On a
    milder one: a knit AND a jacket where either alone is warm enough."""
    wd, plan = ctx.wd, ctx.day.plan
    mid, outer = (wd.by_item.get(picks.get(s)) for s in ("mid", "outer"))
    if plan < layers.COAT_BELOW_C:
        if not outer:
            return 1
        # Knitwear is the warmth between: a shirt open over a tee is not (2026-10-24).
        knit = bool(mid) and mid.get("type") in pairing.KNITWEAR
        return int(knit == (check.is_coat(outer) and layers.coat_alone(outer, plan)))
    return int(bool(mid and outer) and (scale.warm_enough(mid, plan) or scale.warm_enough(outer, plan)))


def bare(ctx: Ctx, picks: dict, cands: dict) -> int:
    """The undershirt's slot is decided, empty, something could fill it, and the top
    takes one — never a T-shirt (check.tee_base)."""
    return int("inner" in picks and not picks["inner"] and bool(cands.get("inner"))
               and not check.tee_base(picks, ctx.wd.by_item))


def _rank(ctx: Ctx, outfit: tuple, issues: list, gave: tuple, today: frozenset) -> tuple:
    """`today`: the slots something can be worn in. They wear an undershirt whenever
    they own one (user, 2026-07-15) — so an outfit whose top cannot take it ranks
    below one whose top can, not only one that merely left it off; and a layer worn
    as the top ranks below a top under it, where one fits."""
    shape, picks = outfit
    kinds = {i.kind for i in issues}
    repeats = max(sum(1 for k in kinds if k.startswith("repeat-")), _repeats(ctx, picks))
    cold = _layering(ctx, picks)
    under = int("no-inner" in kinds or ("inner" in today and not picks.get("inner")
                                        and not check.tee_base(picks, ctx.wd.by_item)))
    topless = int("base" in today and not picks.get("base"))
    # More layers than the day allows (check.py's soft "layers"): never offered beside
    # outfits within it — the chooser is told every outfit fits the weather (2026-10-21).
    over = int("layers" in kinds)
    # Fewer rules given up before anything else: a re-roll, the undershirt or the
    # knit-and-coat never buy a broken rule (user, 2026-10-23: "make sure the selection
    # is nothing violating the rule"; Codex review — a shown navy tee traded for a
    # colour clash). Flat, so any() still reads "falls short somewhere".
    return (*cost(gave), repeats, cold, under, topless, over)


def _diverse(ranked: list) -> list:
    """The best K that differ from each other in at least two visible slots, then —
    a wardrobe with one pair of shoes and one of trousers has few of those — any
    other distinct outfit, best first."""
    # The same garments filed in other slots are the same look on the person — a
    # cardigan as "outer" over nothing is the cardigan in mid — so only the better
    # ranked filing is offered.
    looks: dict = {}
    for o in ranked:
        looks.setdefault(look(o.picks), o)
    ranked = list(looks.values())
    kept: list = []
    for o in ranked:
        if len(kept) < K and all(sum(o.picks.get(s) != k.picks.get(s) for s in VISIBLE) >= 2 for k in kept):
            kept.append(o)
    for o in ranked:
        # Backfill: at least something you would see differs — a belt alone is not
        # another outfit.
        if len(kept) < K and o not in kept and all(
                any(o.picks.get(s) != k.picks.get(s) for s in VISIBLE) for k in kept):
            kept.append(o)
    return sorted(kept, key=ranked.index)


def _evaluate(c: Ctx, found: list, priority, today: frozenset) -> list:
    """Step 11 on the outfits of one pass: re-roll first, then rotation, each checked
    against check.issues until CHECKED_CAP pass."""
    # The rank's own order before any cut (pre-push gate, 2026-10-20): a cap reached by
    # well-rotated outfits without the knit or the undershirt must not hide the ones
    # with them.
    prelim = sorted(((_score(c, p, priority, c.day.look.liked), shape, p) for shape, p in found
                     if look(p) not in c.exclude),
                    key=lambda r: (cost(needed(c, _full(r[2]))), _repeats(c, r[2]), _layering(c, r[2]),
                                   int("inner" in today and not r[2].get("inner")
                                       and not check.tee_base(r[2], c.wd.by_item)),
                                   int("base" in today and not r[2].get("base")), _over(c, r[2]), -r[0],
                                   key(_full(r[2]))))
    ok: list = []
    seen: set = set()
    for pre, shape, p in prelim:
        full = _full(p)
        if key(full) in seen:
            continue
        seen.add(key(full))
        issues = check.issues(full, c.day)
        if check.hard(issues):
            continue
        soft = sum(1 for i in issues if not i.hard)
        gave = needed(c, full)
        rank = _rank(c, (shape, full), issues, gave, today)
        ok.append(Outfit(full, pre - 2 * soft, issues, shape, gave, sheds(c.day, full), rank))
        if len(ok) >= CHECKED_CAP:
            break
    return ok


def search(ctx: Ctx, priority=None) -> Result:
    """Steps 6-11 with the relax ladder: the top K outfits that pass every absolute
    rule and check.issues, giving up the fewest relaxable ones. Each step is tried
    narrow, then wide, then with every candidate; where all three find nothing, every
    combination is walked (_exact) before the next rule gives way — so a rule is given
    up only when no outfit in the closet keeps it. Empty only when nothing passes with
    the whole ladder given up, or the deadline came first (complete=False)."""
    priority = priority or priority_for(ctx)
    relaxed: list = []
    removed: dict = {}
    passes = [(step, w) for step in (None, *RELAX) for w in range(len(WIDTHS))]
    held: list = []          # a pass's best, held while a wider pass may do better
    complete, reached = True, 0
    for n, (step, width) in enumerate(passes):
        if time.monotonic() > ctx.deadline:
            log.warning("funnel: out of time after %d pass(es)", n)
            complete = False
            break
        if step and step not in relaxed:
            relaxed.append(step)
        c = Ctx(ctx.day, ctx.target, frozenset(relaxed), ctx.exclude, width, ctx.deadline)
        found, removed, today = _pass(c, priority)
        ok = sorted(_evaluate(c, found, priority, today) + held, key=lambda o: (o.rank, -o.score, key(o.picks)))
        last_width = n + 1 == len(passes) or passes[n + 1][0] != step
        # The best still falls short somewhere the rank counts — a repeat, no knit and
        # coat, no undershirt, no top under the layer, a rule given up: a wider pass of
        # the same rules may hold what the narrow one cut (pre-push gate, 2026-10-20).
        if ok and any(ok[0].rank) and not last_width:
            held = ok
            continue
        bound = min((cost(o.relaxed) for o in ok), default=None)
        if last_width and bound != cost(()):
            # The beam found nothing that keeps this step's rules, or only outfits that
            # give some up: every combination, before a rule gives way and before one
            # is said to be needed (user, 2026-10-23; Codex review — 21 striped tees
            # filled the beam while a plain navy one broke one rule fewer).
            more_ok, more, complete = walks.exact(c, priority, bound)
            reached += more
            ok = sorted(ok + more_ok, key=lambda o: (o.rank, -o.score, key(o.picks)))
            if more_ok:
                log.info("funnel: the beam missed %d outfit(s) giving up less at %s (%d reached)",
                         len(more_ok), step or "the strict rules", more)
            if not complete and not ok:
                break
        if ok:
            # The model chooses by eye, so it is only offered the top tier: no outfit
            # it can pick repeats what could change, skips the coat's knit or the
            # undershirt, wears a layer as the top, or gives up more rules than the
            # best ones do.
            tier = [o for o in ok if o.rank == ok[0].rank]
            return Result(_diverse(tier), tuple(relaxed), ctx.target, removed, complete, reached)
    if held:     # out of time with something in hand: serve the best of it
        tier = [o for o in held if o.rank == held[0].rank]
        return Result(_diverse(tier), tuple(relaxed), ctx.target, removed, False, reached)
    return Result([], tuple(relaxed), ctx.target, removed, complete, reached)


def notes(relaxed: tuple, complete: bool = True) -> list[str]:
    """What the served outfit gives up, in words — every rule it breaks, after a line
    saying that no combination keeps them all (user, 2026-10-23: "If there is truly no
    combination ... it needs to mention that in the commentary")."""
    said = [NOTES[r] for r in reversed(relaxed) if r in NOTES]
    if not said:
        return []
    lead = (TRIED_ALL if complete else
            "time ran out before every combination was tried — none of those tried keeps every rule")
    return [lead, *said]
