"""scale.py — how warm a garment has to be, and what its number means.

Split out of picks.py on 2026-08-31, when it crossed the 600-line ceiling. The
division is the one the module already had: picks.py judges an ANSWER — which items
may sit in which slots, whose bans are kept, whether anybody is dressed at the end
— and this is the one thing in it that is not about a particular outfit at all, but
about what the number 1-5 on a garment MEANS.

Two scales live here, and a garment says which one it was numbered on:

  ABSOLUTE   "1=summer-thin, 5=deep-winter", judged against 5/12/18C. One climate,
             written once and asked of every wearer. Everything classified before
             2026-08-31 is on it, and so is everybody who has set no home area.

  HOME       the wearer's own year: the coldest month is warmth 5, the annual
             average 3, the warmest month 1 (user, 2026-08-30).

They are NOT interchangeable, and the difference is a whole level in the middle of
a temperate year — the absolute table's implicit warmth 3 is about 8C, while a real
annual average is nearer 13. Re-reading an old number on the new scale would quietly
demote every garment the wearer already owns, so each garment is judged by the scale
its number was written on, and migrates only when it is re-graded.

The JS twin is in app/www/index.html (climateAnchors, warmthTemp, minOuterWarmth).
"""

import math
from dataclasses import dataclass
from typing import Protocol

# The scale of last resort: absolute degrees, the same everywhere on earth. Used for
# every garment numbered before the home scale existed, and for every wearer who has
# set no home area — with nowhere to measure from, a temperate guess is more honest
# than an invented one.
ABSOLUTE_TABLE = ((5, 4), (12, 3), (18, 2))

# Where the anchors sit on the 1-5 scale. 5 is the warmest garment and belongs to the
# coldest month; 1 is the thinnest and belongs to the warmest.
WARMTH_COLD, WARMTH_AVG, WARMTH_HOT = 5, 3, 1

# What a garment's `warmth` was measured against. Absent means the older one, which
# is the only safe reading of a closet saved before this field existed.
ABSOLUTE, HOME = "absolute", "home"


def _half_up(x: float) -> int:
    """Round halves AWAY from zero, like JS Math.round on a positive number.

    Python's round() breaks a tie to even, so a computed 4.5 was a 4 here and a 5 in
    the phone's twin — the app's gap check and the server's outfit check disagreeing
    at exactly the thresholds either of them lands on. Raised by the pre-push
    reviewer, 2026-08-31.
    """
    return math.floor(x + 0.5)


@dataclass(frozen=True)
class Climate:
    """The home climate the 1-5 warmth scale is measured against (user, 2026-08-30).

    "3 should be referred as the annual average temperature of the home location,
    5 the highest, and low the lowest. We should always take the mid point of the
    Monthly average range."

    Three anchors, computed once from the home area's twelve monthly midpoints
    (weather.fetch_climate_anchors):

        cold  the coldest month   -> warmth 5, the warmest thing they own
        avg   the annual average  -> warmth 3
        hot   the warmest month   -> warmth 1

    The DIRECTION is the one the garments already had: 5 stays the wool coat and 1
    the t-shirt, so nothing in a closet is renumbered. What changes is which
    temperature each number answers to.
    """

    cold: float
    avg: float
    hot: float

    @classmethod
    def of(cls, cold: float | None, avg: float | None, hot: float | None) -> "Climate | None":
        """A usable scale, or None — and None means "fall back", never "crash".

        The anchors arrive from the phone, which computed them from an archive that
        can be short a month, or from a home the wearer has just moved. A degenerate
        scale (a flat year, or the ends the wrong way round) would divide by zero or
        grade backwards, and either is worse than the absolute table it replaces.
        """
        if cold is None or avg is None or hot is None:
            return None
        if not (cold < avg < hot):
            return None
        return cls(float(cold), float(avg), float(hot))

    def temp_for(self, warmth: int) -> float:
        """The temperature this warmth answers to — what the picker's labels say.

        Piecewise-linear through the three anchors rather than one straight line end
        to end: the annual average is rarely halfway between the extremes, and a
        single line would put warmth 3 somewhere the wearer has never called average.

        UNROUNDED, deliberately. Both sides round once, where it is displayed, so a
        tie cannot be broken differently in the two languages.
        """
        w = max(WARMTH_HOT, min(WARMTH_COLD, warmth))
        if w >= WARMTH_AVG:
            f = (w - WARMTH_AVG) / (WARMTH_COLD - WARMTH_AVG)
            return self.avg + (self.cold - self.avg) * f
        f = (WARMTH_AVG - w) / (WARMTH_AVG - WARMTH_HOT)
        return self.avg + (self.hot - self.avg) * f

    def warmth_for(self, plan_temp: float) -> int:
        """The warmth a day of this temperature asks for — temp_for, inverted."""
        if plan_temp <= self.cold:
            return WARMTH_COLD
        if plan_temp >= self.hot:
            return WARMTH_HOT
        if plan_temp <= self.avg:
            w = WARMTH_AVG + (WARMTH_COLD - WARMTH_AVG) * (self.avg - plan_temp) / (self.avg - self.cold)
        else:
            w = WARMTH_AVG - (WARMTH_AVG - WARMTH_HOT) * (plan_temp - self.avg) / (self.hot - self.avg)
        return max(WARMTH_HOT, min(WARMTH_COLD, _half_up(w)))


class Anchors(Protocol):
    """Whatever carries the three numbers — schemas.ClimateAnchors, in practice.

    A Protocol rather than the model itself: this module sits below the request
    shapes and must not import them, and `object` left the attributes invisible to
    the type checker.
    """

    cold: float
    avg: float
    hot: float


def warmth_phrase(item: dict) -> str:
    """How to say a garment's warmth to a model, in the units it was written in.

    "warmth 3/5" is a number on an unnamed scale, and this codebase now has two of
    them. The outfit path can afford that — every pick is checked afterwards, and a
    misread outer layer is cleared — but PACKING has no such guard: the model's
    answer is the answer, so a home-scale 3 read as an absolute 3 packs the wrong
    clothes for the trip and nothing notices. Raised by the pre-push reviewer,
    2026-08-31.

    So a graded garment states what it is FOR, and an ungraded one keeps the bare
    number it has always had rather than being given a temperature nobody measured.
    """
    c = graded_on(item)
    n = f"warmth {item.get('warmth')}/5"
    return f"{n} (for days around {c.temp_for(item.get('warmth') or 3):.0f}C)" if c else n


def from_anchors(a: Anchors | None) -> Climate | None:
    """The wearer's warmth scale as it arrives on the wire, or None.

    One reader for every endpoint that takes anchors, so /advice and /classify can
    never disagree about what warmth 4 means — which would be worse than neither of
    them knowing.
    """
    return Climate.of(a.cold, a.avg, a.hot) if a is not None else None


def absolute_min_warmth(plan_temp: float) -> int:
    for below, need in ABSOLUTE_TABLE:
        if plan_temp < below:
            return need
    return 1


def graded_on(item: dict) -> Climate | None:
    """The scale THIS garment's number was written on, or None for the absolute one.

    Carried by the garment itself, as three numbers rather than the word "home".
    "home" alone says a garment was graded against somebody's year without saying
    WHOSE: a jumper graded in Singapore, read against Oslo's anchors after a move,
    is re-interpreted against a climate that never saw it — the same silent re-grade
    the stamp exists to prevent, one move later. Raised by the pre-push reviewer,
    2026-08-31.

    Anchors that do not make a usable scale fall back to absolute, like everything
    else here: a garment must never become unjudgeable.
    """
    if item.get("warmthScale") != HOME:
        return None
    a = item.get("warmthAnchors") or []
    if len(a) != 3:
        return None
    return Climate.of(a[0], a[1], a[2])


def min_outer_warmth(plan_temp: float, item_climate: Climate | None = None) -> int:
    """How warm the outermost garment must be — on the scale IT was numbered on.

    A garment classified as "warmth 3" under "1=summer-thin, 5=deep-winter" is not
    making the same claim as one graded against a particular wearer's own year, and
    reading the first with the second's ruler demotes it by about a level. So the
    guard asks each garment for the rule its own number was written under, and a
    closet holding several is judged correctly item by item rather than all at once.

    This is why the scale is a property of a GARMENT here and not of the request:
    what needs to be known at 06:45 is what each number meant when it was written,
    and that does not change when the wearer moves house.
    """
    if item_climate is not None:
        return item_climate.warmth_for(plan_temp)
    return absolute_min_warmth(plan_temp)


def warm_enough(item: dict, plan_temp: float) -> bool:
    """Is this garment warm enough to be the outermost layer today?

    One reader, so the check that CLEARS a pick and the search for a replacement can
    never disagree about the same garment — which is how a slot was once emptied and
    then reported as a wardrobe gap with a legal alternative sitting unused.
    """
    return (item.get("warmth") or 3) >= min_outer_warmth(plan_temp, graded_on(item))
