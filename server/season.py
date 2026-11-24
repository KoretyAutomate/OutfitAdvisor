"""
season.py — the seasonal closet (user, 2026-11-18).

User: "I don't need shorts nor summer pants to be in a part of choices during
winter. In summer, I don't need jacket nor sweater ... this morning I got a summer
pants recommendation which is completely off."

Design agreed with the user after two rounds with Codex:

- The season is the home climate's NORMAL for the day, not the forecast: an odd
  20C day in November must not bring the shorts back, nor a cold June morning the
  parka. The phone holds twelve monthly normal lows and highs (POST /climate) and
  sends them. This module reads the day's normal off them by date, so a snapshot
  saved weeks ago for the morning push is never stale, and the hemisphere never
  needs knowing.
- A garment is out of season when it fails the same comfort rules against the normal
  day that the actual-weather checks apply to the forecast: too warm for the
  hour its slot is judged by, or (legs only) a summer garment on a cold-normal
  day. A per-garment `season` overrides that: "all" (never out of season), "warm"
  (warm months only), "cold" (cold months only). "auto" or absent means the rule.
- Precedence: their rules and the actual weather first, then season, then rotation,
  taste and styling. funnel ranks an outfit with an out-of-season garment below every
  outfit without one, never removes it: when nothing in season fits, the closest
  comfortable outfit is still served, with a note.
- A mismatch only counts where something IN season could take that slot today (owned,
  not banned outright, comfortable). Otherwise it is simply what they have. That also
  keeps the search from walking every rule step for an in-season outfit that cannot
  exist.

No normals (an old phone, or a climate the archive could not measure): everything is
in season and only the actual weather applies.
"""
import calendar
import datetime as dt
import math
from dataclasses import dataclass

import garment
import layers
import picks as pk
import rules
import scale

MODES = ("auto", "all", "warm", "cold")
# On the garment's own scale: a normal morning that asks an outer layer for this much
# or more is a cold month. Absolute: below 12C. The "warm" and "cold" overrides split
# the year here, with no gap and no overlap.
COLD_MONTH_NEED = 3
# How far down the search order an out-of-season garment goes (funnel.priority_for):
# below a week of rotation, so beams look at in-season garments first. The rank,
# not this, is what guarantees the precedence.
PRIORITY_PENALTY = 8.0


@dataclass(frozen=True)
class Normal:
    lo: float
    hi: float


def clean_normals(v: object) -> list | None:
    """Twelve [lo, hi] pairs, January first, or None. Anything malformed is dropped,
    never a 422: a bad climate must cost the season and nothing else."""
    if not isinstance(v, list) or len(v) != 12:
        return None
    out = []
    for p in v:
        if not isinstance(p, list) or len(p) != 2:
            return None
        try:
            lo, hi = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not -90 <= lo <= hi <= 60:
            return None
        out.append([lo, hi])
    return out


def normal_for(normals: list | None, date: object) -> Normal | None:
    """The normal day on this date. Each month's value is its middle; a date between
    two middles is read off the line between them, around the year's end too."""
    if not normals:
        return None
    try:
        d = dt.date.fromisoformat(str(date))
    except ValueError:
        return None
    pos = d.month - 1 + (d.day - 0.5) / calendar.monthrange(d.year, d.month)[1] - 0.5
    i = math.floor(pos)
    f = pos - i
    a, b = normals[i % 12], normals[(i + 1) % 12]
    return Normal(round(a[0] + (b[0] - a[0]) * f, 1), round(a[1] + (b[1] - a[1]) * f, 1))


def out_of_season(item: dict, slot: str, n: Normal, actual: Normal | None = None) -> bool:
    """Would this garment, worn as `slot`, be wrong on the normal day?

    `actual` is today's real plan and peak, when there is one. A garment the actual
    morning calls for is never out of season for being WARM: the too-warm side is
    judged at the colder of the two days, and a cold-months garment is in season on
    an actually cold day. Otherwise a cold morning in July lost the knit under the
    coat to the season count (pre-push gate, 2026-11-21). The cold side stays on the
    normal: an odd warm November day still keeps the shorts away while comfortable
    trousers exist (_fits)."""
    mode = item.get("season") if item.get("season") in MODES else "auto"
    if mode == "all":
        return False
    sc = scale.graded_on(item)
    actual_cold = actual is not None and scale.min_outer_warmth(actual.lo, sc) >= COLD_MONTH_NEED
    if mode in ("warm", "cold"):
        cold_month = scale.min_outer_warmth(n.lo, sc) >= COLD_MONTH_NEED
        return cold_month if mode == "warm" else not (cold_month or actual_cold)
    if layers.covers_legs(slot, item) and scale.too_cold_for_legs(item, n.lo):
        return True
    hot = pk._heat_temp(slot, n.lo, n.hi)
    if actual is not None:
        hot = min(hot, pk._heat_temp(slot, actual.lo, actual.hi))
    return scale.too_warm(item, hot)


def normal(day) -> Normal | None:
    n = getattr(day.prefs, "normal", None)
    return n if isinstance(n, Normal) else None


# id(day) -> (day, {slot: something in season fits}). The day is kept in the value so
# its id cannot be reused while cached; a few requests' worth at most.
_FITS: dict = {}


def _fits(day, slot: str, n: Normal) -> bool:
    """They own something in season for this slot that they could wear today. A slot
    that can be left empty always has an in-season answer, which is leaving it
    off: a jacket in July counts as out of season even if it's the only jacket. If
    the actual morning needs it, the outfit without it fails the cold check, and
    the out-of-season jacket then ranks above being cold (funnel). Comfortable
    includes dry feet: in-season mesh sneakers are no answer on a wet day, so leather
    loafers kept for summer are not out of season then (pre-push gate, 2026-11-24:
    the season had outranked the rain)."""
    if slot in pk._SHEDDABLE:
        return True
    hit = _FITS.get(id(day))
    if hit is None or hit[0] is not day:
        while len(_FITS) >= 8:
            _FITS.pop(next(iter(_FITS)))
        hit = _FITS[id(day)] = (day, {})
    memo: dict[str, bool] = hit[1]
    if slot not in memo:
        wd = day.wd
        outright = [r for r in day.rules if not rules.is_combination(r)]
        today = Normal(day.plan, day.peak)
        memo[slot] = any(
            slot in (wd.by_roles.get(i) or ()) and not out_of_season(it, slot, n, today)
            and not rules.violations(outright, {slot: i}, wd.by_item)
            and not layers.overdressed(it, slot, wd, day.plan, day.peak, day.rules)
            and not layers.underdressed(it, slot, day)
            and not (slot == "footwear" and garment.wet(day.w) and garment.wets_through(it))
            for i, it in wd.by_item.items())
    return memo[slot]


def counts(day, slot: str, iid: str) -> bool:
    """This garment in this slot is out of season, and something in season could
    have taken the slot instead."""
    n = normal(day)
    it = day.wd.by_item.get(iid)
    return bool(n and it and out_of_season(it, slot, n, Normal(day.plan, day.peak)) and _fits(day, slot, n))


def mismatches(day, picks: dict, legs_only: bool = False) -> int:
    """How many worn garments are out of season, where something in season fits.
    `legs_only`: trousers, shoes and one-pieces only, the slots the weather's layering
    rules never touch (funnel holds these aside even on a coat morning)."""
    by = day.wd.by_item
    return sum(1 for s, i in picks.items()
               if i and (not legs_only or layers.covers_legs(s, by.get(i) or {})) and counts(day, s, i))
