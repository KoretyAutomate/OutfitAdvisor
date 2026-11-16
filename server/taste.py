"""
taste.py — what they wore on days like today (user, 2026-11-14):

"I want to keep a log of what I wore with parameters which influence decision
(occasion, weather, temperature) so that suggestion naturally fits into my taste."

The phone keeps the log (`oa.outfitlog`, one entry per day: the outfit, the occasion,
the RAW weather) and sends it with every request; this server remembers nothing
between requests, so a Taste is built from that request alone and dropped after it.

How it steers the funnel (PLAN.md, 2026-11-14), never ahead of a rule:
  bonus      an item worn on days like today, per slot — part of the outfit's score
  pair       two garments worn TOGETHER on such days — part of the outfit's score
  potential  the best pair a garment could still be part of — SEARCH guidance only,
             so a favourite pair's first member survives the cut before its partner
             is chosen; never in a finished outfit's score
  within     the outfits offered to the chooser, once the log is confident enough
Nothing is added to a garment worn today or yesterday (coats excepted, as rotation
excepts them), so rotation behaves exactly as it did without a log.

Also holds offer(): the top tier → what the chooser sees (moved from funnel.py at its
600-line ceiling). It imports funnel at call time: schemas.py imports this module for
clean_worn, and must not pull the whole funnel in with it.
"""
import datetime as dt
import logging
import math
from dataclasses import replace

log = logging.getLogger("outfit-advisor")

SLOTS = ("inner", "base", "mid", "outer", "bottoms", "footwear")
VISIBLE = ("base", "mid", "outer", "bottoms", "footwear")
OCCASIONS = ("office", "wfh", "off")
MAX_ENTRIES = 90         # the phone's cap; the bytes cap (48 KB) is the phone's too
KEEP_DAYS = 120
TEMP_RANGE = (-90.0, 60.0)    # schemas.ClimateAnchors' range: real polar days included
CONFIDENT = 0.5          # from here on, the chooser is only offered outfits like theirs
WITHIN = 1.0             # ... whose taste is this close to the best of the tier
_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-")


# ── the log, as it arrives: SHAPE only, dropped never refused ──────────────────────

def _num(v: object, lo: float, hi: float) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v) if lo <= v <= hi else None


def _id(v: object) -> bool:
    return isinstance(v, str) and 8 <= len(v) <= 64 and set(v) <= _ID_CHARS


def _entry(e: object) -> dict | None:
    if not isinstance(e, dict):
        return None
    day, picks, chose = e.get("day"), e.get("picks"), e.get("chose")
    try:
        if not isinstance(day, str) or len(day) != 10:
            return None
        dt.date.fromisoformat(day)
    except ValueError:
        return None
    temp = _num(e.get("temp"), *TEMP_RANGE)
    if temp is None or not isinstance(picks, dict):
        return None
    worn = {s: i for s, i in picks.items() if s in SLOTS and _id(i)}
    if not worn or len(set(worn.values())) != len(worn):
        return None      # nothing usable, or one garment in two slots: not an outfit
    occasion = e.get("occasion")
    return {"day": day, "occasion": occasion if occasion in OCCASIONS else None, "temp": temp,
            "rain": _num(e.get("rain"), 0, 100) or 0.0, "picks": worn,
            "chose": sorted({s for s in chose if s in worn}) if isinstance(chose, list) else []}


def clean_worn(v: object) -> list[dict]:
    """The log with every malformed entry dropped: a stale or corrupt entry costs
    itself, never the morning. One per day, the LAST in array order winning — the
    phone stores the latest action last, so a corrupt timestamp cannot win."""
    if not isinstance(v, list):
        return []
    by_day: dict = {}
    for e in v[-MAX_ENTRIES:]:
        got = _entry(e)
        if got:
            by_day.pop(got["day"], None)
            by_day[got["day"]] = got
    return list(by_day.values())


# ── a request's taste ──────────────────────────────────────────────────────────────

def _pair_key(a: tuple, b: tuple) -> tuple:
    return (a, b) if VISIBLE.index(a[0]) < VISIBLE.index(b[0]) else (b, a)


def _pairs(worn: list) -> list:
    """Every pair of (slot, id) among the visible slots, in VISIBLE order."""
    vis = [x for x in worn if x[0] in VISIBLE]
    return [_pair_key(vis[i], vis[j]) for i in range(len(vis)) for j in range(i + 1, len(vis))]


def _norm(score: dict, scope) -> dict:
    """score / the best score in its scope (a slot, or a slot-pair) — so much-worn
    trousers cannot mute every top."""
    best: dict = {}
    for k, v in score.items():
        best[scope(k)] = max(best.get(scope(k), 0.0), v)
    return {k: v / best[scope(k)] for k, v in score.items() if best[scope(k)] > 0}


class Taste:
    """The days like today, reduced to what was worn on them. Empty (confidence 0)
    when there is no log: every method then answers 0 and nothing changes."""

    def __init__(self, items: dict | None = None, pairs: dict | None = None, confidence: float = 0.0,
                 rot: dict | None = None, days: int = 0):
        self.items = items or {}            # (id, slot) -> 0..1 within its slot
        self.pairs_ = pairs or {}           # ((slot, id), (slot, id)) -> 0..1 within its slot-pair
        self.confidence = confidence
        self.rot = rot or {}                # id -> 0..1; absent = 1 (not worn lately, or a coat)
        self.days = days                    # entries that counted, for the log
        self._best: dict = {}
        for (a, b), v in self.pairs_.items():
            if self.fresh(a[1]) and self.fresh(b[1]):
                for me in (a, b):
                    self._best[me] = max(self._best.get(me, 0.0), v)

    def fresh(self, iid: str) -> bool:
        """Not worn today or yesterday (a coat always is: rotation never moves it)."""
        return self.rot.get(iid, 1.0) > 0

    def bonus(self, iid: str, slot: str) -> float:
        return 3.0 * self.confidence * self.items.get((iid, slot), 0.0) * self.rot.get(iid, 1.0)

    def pair(self, picks: dict) -> float:
        """How much of this outfit was worn together on days like today: the mean over
        its pairs, so a bigger outfit is not favoured for having more of them."""
        ps = _pairs([(s, picks[s]) for s in VISIBLE if picks.get(s)])
        if not ps or not self.confidence:
            return 0.0
        got = [self.pairs_.get(k, 0.0) if self.fresh(k[0][1]) and self.fresh(k[1][1]) else 0.0 for k in ps]
        return 2.0 * self.confidence * sum(got) / len(got)

    def potential(self, iid: str, slot: str) -> float:
        return 2.0 * self.confidence * self._best.get((slot, iid), 0.0)

    def strong_pairs(self) -> list:
        """The 3 strongest pairs of garments not just worn: kept as candidates past the
        cut, so a favourite pair reaches the search at all."""
        strong = sorted((-v, k) for k, v in self.pairs_.items()
                        if v >= 0.5 and self.fresh(k[0][1]) and self.fresh(k[1][1]))
        return [k for _, k in strong[:3]] if self.confidence else []

    def of(self, picks: dict) -> float:
        """The outfit's taste: its garments' mean bonus plus its pair score."""
        worn = [(s, picks[s]) for s in SLOTS if picks.get(s)]
        mean = sum(self.bonus(i, s) for s, i in worn) / len(worn) if worn else 0.0
        return mean + self.pair(picks)

    def within(self, tier: list) -> list:
        """The tier's outfits close to the best for taste, once the log is confident:
        the model's eye still picks, but cannot throw the preference away."""
        if self.confidence < CONFIDENT or not tier:
            return tier
        best = max(self.of(o.picks) for o in tier)
        return [o for o in tier if self.of(o.picks) >= best - WITHIN]


NONE = Taste()


def weight(e: dict, occasion: str | None, temp: float, wet: bool, age: int) -> float:
    """How much a past day is like today: occasion × temperature × wet × recency."""
    occ = 0.5 if not occasion or not e["occasion"] else 1.0 if e["occasion"] == occasion else 0.25
    warm = max(0.0, 1.0 - abs(e["temp"] - temp) / 6.0)
    rain = 1.0 if (e["rain"] >= 50) == wet else 0.5
    return occ * warm * rain * 0.5 ** (age / 60.0)


def build(worn: list, closet: list, recent: dict, occasion: str | None, temp: float, w: dict) -> Taste:
    """`worn` already shape-checked (clean_worn); `closet` the garments sent today;
    `recent` {id: days ago}; `temp` today's RAW plan temperature; `w` the forecast,
    whose `date` is the day being dressed — so tomorrow's advice ages the log from
    tomorrow, and a phone ahead of this server across the date line keeps its today."""
    try:
        target = dt.date.fromisoformat(str(w.get("date")))
    except ValueError:
        target = dt.date.today()
    groups = {i["id"]: i.get("group") for i in closet}
    rot = {}
    for iid, ago in recent.items():
        if iid in groups and groups[iid] != "outerwear" and isinstance(ago, int):
            rot[iid] = max(0.0, min(1.0, (ago - 1) / 3.0))
    wet = (w.get("rain") or 0) >= 50 or bool(w.get("isRain"))
    items: dict = {}
    pairs: dict = {}
    total, days = 0.0, 0
    for e in worn:
        age = (target - dt.date.fromisoformat(e["day"])).days
        mine = [(s, i) for s, i in e["picks"].items() if i in groups]
        if not 0 <= age <= KEEP_DAYS or not mine:
            continue     # in the future, too old, or nothing they still own
        wt = weight(e, occasion, temp, wet, age)
        if wt <= 0:
            continue
        total, days = total + wt, days + 1
        for s, i in mine:
            items[(i, s)] = items.get((i, s), 0.0) + wt * (1.5 if s in e["chose"] else 1.0)
        for k in _pairs(sorted(mine, key=lambda x: SLOTS.index(x[0]))):
            chosen = k[0][0] in e["chose"] or k[1][0] in e["chose"]
            pairs[k] = pairs.get(k, 0.0) + wt * (1.5 if chosen else 1.0)
    return Taste(_norm(items, lambda k: k[1]), _norm(pairs, lambda k: (k[0][0], k[1][0])),
                 min(1.0, total / 3.0), rot, days)


def get(day) -> Taste:
    t = getattr(day.prefs, "taste", None)
    return t if isinstance(t, Taste) else NONE


def raw_temps(w: dict) -> dict:
    """The real forecast's planned temperatures, BEFORE the wearer's calibration: what
    the phone logs. Never planTemp − tempOffset — the offset is added and then rounded
    (engine.apply_temp_offset), so that subtraction is lossy."""
    import llm
    plan = llm._plan_temp(w)
    return {"rawPlanTemp": round(plan, 1), "rawPeakTemp": round(llm._peak_temp(w, plan), 1)}


def prefs(req, w: dict, t0: float):
    """The request's Prefs, its Look and its Taste — app.py's one call."""
    import llm
    import picks as pk
    import rules
    import style
    p = pk.Prefs.of(rules.clean_rules(req.rules), req.closetOnly, [x.model_dump() for x in req.prefers],
                    req.shown, req.skipped)
    t = build(req.worn, [i.model_dump() for i in req.closet or []], req.recent, req.occasion,
              llm._plan_temp(w), w) if req.worn else NONE
    if req.worn:
        # Counts only: never a date, a garment or an outfit (privacy, as /advice's other logs).
        log.info("taste: %d day(s) logged, %d counted, confidence %.2f", len(req.worn), t.days, t.confidence)
    return style.look_of(replace(p, taste=t), req, t0)


# ── what the chooser is offered ────────────────────────────────────────────────────

def offer(day, tier: list) -> list:
    """The top tier → the outfits the model chooses among: first those close to their
    taste (within), then the best K that differ from each other in at least two
    visible slots, then — a wardrobe with one pair of shoes and one of trousers has few
    of those — any other distinct outfit, best first."""
    import funnel
    ranked = get(day).within(tier)
    # The same garments filed in other slots are the same look on the person — a
    # cardigan as "outer" over nothing is the cardigan in mid — so only the better
    # ranked filing is offered.
    looks: dict = {}
    for o in ranked:
        looks.setdefault(funnel.look(o.picks), o)
    ranked = list(looks.values())
    kept: list = []
    for o in ranked:
        if len(kept) < funnel.K and all(sum(o.picks.get(s) != k.picks.get(s) for s in VISIBLE) >= 2
                                        for k in kept):
            kept.append(o)
    for o in ranked:
        # Backfill: at least something you would see differs — a belt alone is not
        # another outfit.
        if len(kept) < funnel.K and o not in kept and all(
                any(o.picks.get(s) != k.picks.get(s) for s in VISIBLE) for k in kept):
            kept.append(o)
    return sorted(kept, key=ranked.index)
