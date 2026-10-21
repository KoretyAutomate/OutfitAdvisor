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
from dataclasses import dataclass, field

import check
import garment
import layers
import rules
import scale
import sleeves
import style
from vocab import CATEGORIES

K = 4                   # outfits the model chooses among
PER_SLOT = 6            # best candidates per slot carried into the search
BEAM = 120              # partial outfits kept after each slot, per layer shape
CHECKED_CAP = 60        # complete outfits that pass check.issues, at most
VISIBLE = ("base", "mid", "outer", "bottoms", "footwear")
OPTIONAL = ("inner", "accessories")
# Most constrained first, and on a tie the slots a stylist anchors on.
_TIE = ("footwear", "bottoms", "base", "mid", "outer")
# What a pass may give up, in order, when nothing survives. Their rules, the stacking
# and sleeve rules, warmth and heat are never on it.
RELAX = ("colour", "belt", "texture", "wet", "register", "band1", "band2")
NOTES = {
    "colour": "colours a little busier than usual — nothing quieter fits today",
    "belt": "the belt and shoes are different leathers — nothing matching is free today",
    "texture": "the knit and the top are not the ideal pairing — nothing better is free today",
    "wet": "nothing water-resistant to wear on your feet today — expect damp shoes in the rain",
    "register": "the trousers or shoes are more relaxed than the top — nothing smarter is free today",
    "band1": "a little more relaxed than the day calls for — nothing at the usual level is free",
    "band2": "much more relaxed than the day calls for — little that fits the day is free",
}
_COLLARED = frozenset({"polo", "shirt", "blouse", "blazer", "waistcoat"})
_BROWN = ("brown", "tan", "cognac", "chocolate", "camel", "chestnut", "茶")
_BLACK = ("black", "黒")
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
    exclude: frozenset = frozenset()     # outfit keys the model already turned down

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
    # Ranked before the score, in this order (pre-push plan review, 2026-10-20):
    # a re-roll shows something else wherever it can; a cold morning gets knitwear AND
    # a coat; they wear an undershirt whenever one fits; fewer rules given up.
    rank: tuple = ()

    @property
    def sheds(self) -> tuple:
        """What comes off by midday, for the advice text."""
        return sheds(self.shape, self.picks)


@dataclass
class Result:
    outfits: list
    relaxed: tuple
    target: int
    removed: dict = field(default_factory=dict)   # stage -> count, for the log


# ── steps 2-3: what each slot may hold today ─────────────────────────────────────

def _snow_gear(ctx: Ctx, slot: str) -> bool:
    """Snow, and they own something waterproof for this slot that no rule of theirs
    bans outright: then only that — the same demand check.py's snow issue makes, and
    an absolute one, because check.py would reject anything else anyway."""
    wd = ctx.wd
    outright = [r for r in ctx.day.rules if not rules.is_combination(r)]
    return bool(ctx.day.w.get("isSnow")) and slot in ("footwear", "outer") and any(
        it.get("waterproof") and slot in (wd.by_roles.get(i) or ())
        and not rules.violations(outright, {slot: i}, wd.by_item) for i, it in wd.by_item.items())


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
    snow = _snow_gear(ctx, slot)
    if snow and not it.get("waterproof"):
        return "snow"
    if slot == "outer" and _coat_day(ctx) and not check.is_coat(it):
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
    widen = 2 if "band2" in ctx.relaxed else 1 if "band1" in ctx.relaxed else 0
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
    """The best PER_SLOT, taken a kind at a time: the best of each kind first, then
    the next best of each. Six sweaters must not crowd the only coat out of a slot."""
    kinds: dict = {}
    for i in ranked:
        kinds.setdefault(ctx.wd.by_item[i].get("type"), []).append(i)
    out: list = []
    while len(out) < PER_SLOT and any(kinds.values()):
        out += [ids.pop(0) for ids in kinds.values() if ids][:PER_SLOT - len(out)]
    return out


# ── steps 6-8: what goes together ────────────────────────────────────────────────

def _items(ctx: Ctx, picks: dict, slots) -> list[dict]:
    return [ctx.wd.by_item[picks[s]] for s in slots if picks.get(s)]


def _register(ctx: Ctx, picks: dict) -> bool:
    """Trousers and shoes as smart as the top, within one step; utility trousers
    never with a collar or a fine knit (style.LOOK_PRINCIPLES)."""
    tops = _items(ctx, picks, ("base", "mid"))
    legs = _items(ctx, picks, ("bottoms", "footwear"))
    if not tops or not legs:
        return True
    if min(garment.level(i) for i in legs) < max(garment.level(i) for i in tops) - 1:
        return False
    trousers = ctx.wd.by_item.get(picks.get("bottoms")) or {}
    return not (garment.utility_trousers(trousers) and any(
        t.get("type") in _COLLARED or garment.gauge(t) in ("fine", "mid") for t in tops))


def _texture(ctx: Ctx, picks: dict) -> bool:
    """A polo goes under a fine-gauge sweater or a cardigan, never a heavier knit
    (user, 2026-10-18: "Fabric of polo and sweater doesn't go well"); a shirt worn
    open as a layer goes over a tee or a tank, never over another collar."""
    under = [ctx.wd.by_item[picks[s]] for s in ("base",) if picks.get(s)]
    over = [ctx.wd.by_item[picks[s]] for s in ("mid", "outer") if picks.get(s)]
    return not any((u.get("type") == "polo" and o.get("type") == "sweater" and garment.gauge(o) != "fine")
                   or (o.get("type") in ("shirt", "blouse") and u.get("type") not in ("t_shirt", "tank"))
                   for u in under for o in over)


def _colour(ctx: Ctx, picks: dict) -> bool:
    """Neutrals and at most one accent colour; at most one patterned garment."""
    seen = _items(ctx, picks, VISIBLE)
    accents = {a for i in seen if (a := style.accent_of(i))}
    busy = [i for i in seen if style.pattern_of(i) not in (None, "solid")]
    return len(accents) <= 1 and len(busy) <= 1


def _family(item: dict) -> str | None:
    c = " ".join(str(x).lower() for x in item.get("colors") or [])
    return "brown" if any(w in c for w in _BROWN) else "black" if any(w in c for w in _BLACK) else None


def _belt(ctx: Ctx, picks: dict) -> bool:
    """A leather belt matches leather shoes: brown with brown, black with black."""
    belt = ctx.wd.by_item.get(picks.get("accessories")) or {}
    shoes = ctx.wd.by_item.get(picks.get("footwear")) or {}
    leather = garment.material(belt) in (None, "leather") and garment.material(shoes) == "leather"
    if belt.get("type") != "belt" or not leather:
        return True
    a, b = _family(belt), _family(shoes)
    return a is None or b is None or a == b


_PAIRS = (("register", _register), ("texture", _texture), ("colour", _colour), ("belt", _belt))


def clash(ctx: Ctx, picks: dict) -> str | None:
    """The first pairing rule these picks break, or None. Absolute rules first."""
    wd, day = ctx.wd, ctx.day
    if rules.violations(day.rules, picks, wd.by_item):
        return "rules"
    ids = {i for i in picks.values() if i}
    if any(a in ids and b in ids for a, b in day.look.disliked):
        return "disliked"
    if check.stacked(picks, wd.by_item) or sleeves.sleeve_clashes(picks, wd.by_item):
        return "stack"
    if wd.by_group.get(picks.get("base")) == "onepiece" and picks.get("bottoms"):
        return "onepiece"
    return next((k for k, ok in _PAIRS if k not in ctx.relaxed and not ok(ctx, picks)), None)


def _order(shape: tuple, cands: dict, onepiece_only: bool) -> list[str]:
    """The shape's slots, the fewest candidates first; optional slots last."""
    need = [*shape, *(() if onepiece_only else ("bottoms",)), "footwear"]
    need.sort(key=lambda s: (len(cands.get(s) or ()), _TIE.index(s) if s in _TIE else 9))
    return [*need, *OPTIONAL]


def _partial(ctx: Ctx, picks: dict, priority) -> float:
    worn = [(sl, i) for sl, i in picks.items() if i and sl != "accessories"]
    return sum(priority(i, sl) for sl, i in worn) / max(1, len(worn)) + _accessory(ctx, picks)


def _warm_fixable(ctx: Ctx) -> bool:
    """They own a torso garment warm enough for the coldest hour, not banned outright."""
    day, wd = ctx.day, ctx.wd
    outright = [r for r in day.rules if not rules.is_combination(r)]
    return any(scale.warm_enough(it, day.plan) and any(
        r in check.TORSO and not rules.violations(outright, {r: i}, wd.by_item) for r in wd.by_roles.get(i) or ())
        for i, it in wd.by_item.items())


def _beam(ctx: Ctx, cands: dict, order: list, priority, shape: tuple = ()) -> list:
    """Slot by slot, the most constrained first: every candidate that goes with what
    is already chosen, keeping the BEAM best partial outfits after each slot. Wide
    where a depth-first walk is deep — it sees every first choice, not one."""
    partials: list = [{}]
    # Warm enough is a fact of the whole torso (check.py's cold issue): judged the
    # moment the shape's last torso layer is chosen, so the beam never fills up with
    # outfits that can only fail at the end.
    warm = _warm_fixable(ctx)
    for slot in order:
        opts = list(cands.get(slot) or ())
        # An optional slot may stay empty; so may a required one they own nothing
        # for, which is a gap (gaps.py), not a reason to dress nobody.
        if slot in OPTIONAL or not opts:
            opts.append(None)
        nxt = []
        for p in partials:
            for iid in opts:
                if iid and iid in p.values():
                    continue
                trial = {**p, slot: iid}
                if iid and clash(ctx, trial):
                    continue
                if (warm and slot in shape and all(s in trial for s in shape)
                        and not layers._still_warm(trial, ctx.wd.by_item, ctx.day.plan)):
                    continue
                nxt.append(trial)
        nxt.sort(key=lambda q: (-_partial(ctx, q, priority), key(q)))
        partials = nxt[:BEAM]
    return partials


def sheds(shape: tuple, picks: dict) -> tuple:
    return tuple(s for s in ("outer", "mid") if s in shape and picks.get(s))


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
            ago = it.get("_ago")
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
    out = [k for k, ok in _PAIRS if not ok(strict, picks)]
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
    out += ["band1"] if worst == 1 else ["band2"] if worst > 1 else []
    return tuple(k for k in RELAX if k in out)

def _full(picks: dict) -> dict:
    return {c: picks.get(c) for c in CATEGORIES}


def key(picks: dict) -> tuple:
    """An outfit as a sortable, hashable value: an empty slot is ""."""
    return tuple(picks.get(c) or "" for c in CATEGORIES)


def _pass(ctx: Ctx, priority) -> tuple[list, dict, bool]:
    """One search over every layer shape, with the relaxations in ctx: (outfits,
    removed per stage, whether an undershirt can be worn today at all)."""
    cands, removed = candidates(ctx, priority)
    found: list = []
    onepieces = [i for i in cands["base"] if ctx.wd.by_group.get(i) == "onepiece"]
    for shape in SHAPES:
        if ctx.day.plan >= check.HOT_DAY_C and shape != ("base",):
            continue
        for one in (False, True) if onepieces else (False,):
            c = {**cands, "base": onepieces if one else [i for i in cands["base"] if i not in onepieces]}
            found += [(shape, p) for p in _beam(ctx, c, _order(shape, c, one), priority, shape)]
    return found, removed, bool(cands["inner"])


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


def _rank(ctx: Ctx, outfit: tuple, issues: list, gave: tuple, inner_today: bool) -> tuple:
    """`inner_today`: an undershirt of theirs can be worn today. They wear one
    whenever they own one (user, 2026-07-15) — so an outfit whose top cannot take it
    ranks below one whose top can, not only one that merely left it off."""
    shape, picks = outfit
    kinds = {i.kind for i in issues}
    repeats = sum(1 for k in kinds if k.startswith("repeat-"))
    cold = int(ctx.day.plan < layers.COAT_BELOW_C and shape != SHAPES[-1])
    bare = int("no-inner" in kinds or (inner_today and not picks.get("inner")))
    return (repeats, cold, bare, len(gave))


def _diverse(ranked: list) -> list:
    """The best K that differ from each other in at least two visible slots, then —
    a wardrobe with one pair of shoes and one of trousers has few of those — any
    other distinct outfit, best first."""
    # The same garments filed in other slots are the same look on the person — a
    # cardigan as "outer" over nothing is the cardigan in mid — so only the better
    # ranked filing is offered.
    looks: dict = {}
    for o in ranked:
        looks.setdefault(frozenset(o.picks.values()), o)
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


def search(ctx: Ctx, priority=None) -> Result:
    """Steps 6-11 with the relax ladder: the top K outfits that pass every absolute
    rule and check.issues, giving up the fewest relaxable ones."""
    priority = priority or priority_for(ctx)
    relaxed: list = []
    removed: dict = {}
    for step in (None, *RELAX):
        if step:
            relaxed.append(step)
        c = Ctx(ctx.day, ctx.target, frozenset(relaxed), ctx.exclude)
        found, removed, inner_today = _pass(c, priority)
        prelim = sorted(((_score(c, p, priority, c.day.look.liked), shape, p) for shape, p in found
                         if key(_full(p)) not in c.exclude), key=lambda r: (-r[0], key(_full(r[2]))))
        ok = []
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
            rank = _rank(c, (shape, full), issues, gave, inner_today)
            ok.append(Outfit(full, pre - 2 * soft, issues, shape, gave, rank))
            if len(ok) >= CHECKED_CAP:
                break
        if ok:
            ok.sort(key=lambda o: (o.rank, -o.score, key(o.picks)))
            # The model chooses by eye, so it is only offered the top tier: no outfit
            # it can pick repeats what could change, skips the coat's knit or the
            # undershirt when the best ones do not.
            tier = [o for o in ok if o.rank[:3] == ok[0].rank[:3]]
            return Result(_diverse(tier), tuple(relaxed), ctx.target, removed)
    return Result([], tuple(relaxed), ctx.target, removed)


def notes(relaxed: tuple) -> list[str]:
    """What the day had to give up, in words — at most the two most telling."""
    return [NOTES[r] for r in reversed(relaxed) if r in NOTES][:2]
