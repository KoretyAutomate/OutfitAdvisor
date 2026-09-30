"""
layers.py — whether an outfit makes sense as a STACK, not garment by garment.

User, 2026-09-30, on a 14-23C morning that was dressed in a long-sleeve tee as the
undershirt, a t-shirt over it and a cardigan over that: "a stupid recommendation
which no human would do".

Every check before this one judges ONE garment: is it allowed in its slot, is it
warm enough to be outermost, is it too warm for the hour it is worn through. Each
of those three garments passed each of them. What was wrong was the combination,
and nothing looked at the combination. Two rules do now, in code, after the model
has answered — the same posture as every other guard here, because a request in
the prompt is followed most of the time, and that is not the same as followed.

  SLEEVE RULE   a long sleeve never goes under a short one. The cuffs show below
                the short sleeve, and nobody dresses like that on purpose.
  LAYER BUDGET  how many torso layers the day allows, from how cold it is. Three
                on a mild morning is a layer too many even when each one is thin.

Both take clothing OFF, or swap an undershirt for a short-sleeved one, and never
touch the base or the outer layer — the base is the outfit, and the outer is also
the rain and wind protection. The one thing either ADDS is warmth the sleeve rule
itself took away: live on the day it shipped, the model answered long-T + tee three
times out of three, and taking the long-T off left a t-shirt alone on a 14C morning.
A person would reach for the cardigan, so the repair does too.

Split into its own module because picks.py sits at the 600-line ceiling.
"""
import re

import picks as pk
import reroll
import rules
import scale
from llm import _plan_temp, log
from sleeves import SLEEVE_STACK, sleeve_clashes, sleeve_of

_TORSO = ("inner", "base", "mid", "outer")

# What is shed first when the budget is exceeded. The undershirt goes before the
# cardigan: it is optional, invisible, and it was the layer in the complaint. The
# mid layer is the one that comes off by noon anyway. Never the base, never the
# outer.
_SHED_ORDER = ("inner", "mid")


def max_layers(picks: dict, by_item: dict, plan_temp: float) -> int:
    """How many torso layers today allows: 2 on a mild or warm day, up to 4 in the
    cold. The same warmth the day asks of an outer layer, so 12-18C on the absolute
    scale (warmth 2) allows two, 5-12C three, and below that four.

    Read on the BASE garment's scale, the one layer always worn, so a wardrobe graded
    against the wearer's own year is judged in its own units like every other check.
    """
    ref = by_item.get(picks.get("base")) or next(
        (by_item.get(picks[c]) for c in _TORSO if picks.get(c)), None) or {}
    return _budget(plan_temp, ref)


def day_budget(closet: list[dict], plan_temp: float) -> int:
    """The same number before anything is picked, for the prompt: read on the scale
    of a garment that can be the base, which is what max_layers will read it on."""
    ref = next((i for i in closet if "base" in (i.get("roles") or [i.get("category")])), {})
    return _budget(plan_temp, ref)


def _budget(plan_temp: float, ref: dict) -> int:
    need = scale.min_outer_warmth(plan_temp, scale.graded_on(ref))
    return max(2, min(4, need))


def _still_warm(picks: dict, by_item: dict, plan_temp: float) -> bool:
    return any(scale.warm_enough(by_item.get(picks[c]) or {}, plan_temp)
               for c in _TORSO if picks.get(c))


def _short_inner(picks: dict, wd, plan_temp: float, user_rules: list[dict],
                 peak_temp: float) -> str | None:
    """An owned undershirt that does not reach past the sleeve above it.

    Warm enough for the morning is not the test that matters for heat: the
    undershirt is worn all day, so it is judged by the afternoon like the heat pass
    judges it (picks._heat_temp). Checked against the morning only, a warmth-3
    undershirt replaced a warmth-2 one on a 14-to-23C day that the heat pass had
    just cleared. Raised by the pre-push reviewer, 2026-09-30."""
    for iid, item in wd.by_item.items():
        if iid in picks.values() or "inner" not in (wd.by_roles.get(iid) or ()):
            continue
        if sleeve_of(item) not in ("short", "none"):
            continue
        if scale.too_warm(item, pk._heat_temp("inner", plan_temp, peak_temp)):
            continue
        if rules.violations(user_rules, {**picks, "inner": iid}, wd.by_item):
            continue
        return iid
    return None


def _rewarm(picks: dict, wd, plan_temp: float, user_rules: list[dict]) -> list[tuple]:
    """Put back the warmth a sleeve repair took away: a mid layer first, the one
    that comes off by noon, then an outer. Only a garment that is warm enough on its
    own, not too warm for the morning, legal in that slot, allowed by the wearer's
    rules — and one that does not start a new sleeve clash of its own."""
    for slot in ("mid", "outer"):
        # An occupied slot is open too when what fills it is itself too thin — a
        # linen overshirt as the mid, with the warm cardigan owned and unworn. Only
        # skipped when its garment already does the job. Raised by the pre-push
        # reviewer, 2026-09-30.
        if picks.get(slot) and scale.warm_enough(wd.by_item.get(picks[slot]) or {}, plan_temp):
            continue
        for iid, item in wd.by_item.items():
            if iid in picks.values() or slot not in (wd.by_roles.get(iid) or ()):
                continue
            if not scale.warm_enough(item, plan_temp) or scale.too_warm(item, plan_temp):
                continue
            trial = {**picks, slot: iid}
            if rules.violations(user_rules, trial, wd.by_item) or sleeve_clashes(trial, wd.by_item):
                continue
            picks[slot] = iid
            return [(slot, iid, "warmth")]
    return []


def added_line(added: tuple, by_item: dict) -> str:
    """The bullet for a garment a repair put on: in the picture, so in the text too.
    A (slot, id) pair is picks._enforce_a_top's and keeps its own wording."""
    if len(added) < 3:
        return pk._added_top_line(added, by_item)
    label = str((by_item.get(added[1]) or {}).get("label") or "").strip()
    if added[2] == "sleeve":
        return (f"{label or 'A short-sleeved undershirt'} as the undershirt — short "
                "sleeves, so nothing shows below the ones over it.")
    return f"{label or 'A warmer layer'} — for the morning chill; take it off when it warms up."


_SLOT_WORDS = {"inner": ("inner", "undershirt"), "base": ("base",),
               "mid": ("mid-layer", "mid layer", "mid"), "outer": ("outer", "jacket", "coat")}
_UNNEEDED = re.compile(r"\b(no|none|not needed|not required|unnecessary|no need|skip)\b",
                       re.IGNORECASE)


def with_added(text: str, added: tuple | list, by_item: dict) -> str:
    """The advice text with the added garment's line on top, and the model's own
    line saying that slot is not needed taken out. Live, that line was "No mid-layer
    is needed as the heat makes a cardigan too warm" directly under a cardigan the
    repair had just put on — the outfit right and the words arguing with it.

    A line goes when it names the slot or the added garment's kind AND says it is
    not needed. Both, so "no rain, so sneakers" survives."""
    # One garment (a tuple, _enforce_a_top's) or several (a list, from tidy): a swap
    # and a re-warm in the same repair each put a garment on, and each needs its line.
    # Raised by the pre-push reviewer, 2026-09-30.
    each = [added] if isinstance(added, tuple) else list(added)
    kept = text.split("\n")
    for a in each:
        kind = str((by_item.get(a[1]) or {}).get("type") or "").replace("_", " ")
        words = [w for w in (*_SLOT_WORDS.get(a[0], (a[0],)), kind) if w]
        about = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b",
                           re.IGNORECASE)
        # The tip too: "No mid-layer is needed today." under a cardigan the repair
        # just put on is the same contradiction one line lower.
        kept = [ln for ln in kept if not (ln.startswith(("•", "💡")) and about.search(ln)
                                          and _UNNEEDED.search(ln))]
    return "".join(f"• {added_line(a, by_item)}\n" for a in each) + "\n".join(kept)


def hold(picks: dict, w: dict, wd, prefs, banned: list[dict],
         added: tuple | None) -> tuple[list[dict], list | None, set]:
    """Run tidy() on the FINAL picks and settle what it changed, for closet.py.

    Returns (banned, added, cleared):
      banned   plus every garment taken off, tagged so the prose says a layer was
               changed rather than blaming a rule the wearer never made;
      added    every garment put on that is still worn, plus _enforce_a_top's if it
               is — a repair's line for a garment a later step replaced would
               recommend something not in the outfit;
      cleared  every slot emptied here, for the caller's `covered`: an undershirt taken off because the
               outfit did not need it is not a hole in the wardrobe, and reporting
               one would put an undershirt on the shopping list.
    """
    plan = _plan_temp(w)
    before = dict(picks)
    put_on: dict = {}
    cleared: set = set()
    for slot, alt, why in tidy(picks, wd, plan, list(prefs.rules), reroll.peak_temp(w, plan)):
        log.warning("closet picks: %s %s (%s)", slot, f"swapped for {alt}" if alt else "shed", why)
        put_on[slot] = (slot, alt, why) if alt else None
        if (gone := wd.by_item.get(before.get(slot))) and picks.get(slot) != before.get(slot):
            banned = banned + [{**gone, "_why": "layers"}]
        if not picks.get(slot):
            cleared.add(slot)
    each = [a for a in [added, *put_on.values()] if a and picks.get(a[0]) == a[1]]
    return banned, each or None, cleared


def tidy(picks: dict, wd, plan_temp: float, user_rules: list[dict],
         peak_temp: float | None = None) -> list[tuple]:
    """Apply both rules to `picks` in place. Returns (slot, replacement or None, why).

    Sleeves first: the budget then counts the layers that are actually left.
    """
    done: list[tuple] = []
    peak = plan_temp if peak_temp is None else peak_temp
    warm_before = _still_warm(picks, wd.by_item, plan_temp)
    # Re-read after every repair, never from a list taken up front: a long undershirt
    # under a short base AND a short mid is two pairs, and swapping it for a short
    # one settles both — the stale second pair then took the replacement off too.
    # Raised by the pre-push reviewer, 2026-09-30. Bounded: each round removes or
    # shortens a layer, and there are three layers to judge.
    for _ in range(len(SLEEVE_STACK)):
        clashes = sleeve_clashes(picks, wd.by_item)
        if not clashes:
            break
        lower, _upper = clashes[0]
        alt = _short_inner(picks, wd, plan_temp, user_rules, peak) if lower == "inner" else None
        if alt:
            picks["inner"] = alt
            done.append(("inner", alt, "sleeve"))
            continue
        # The lower layer is what goes when it is the undershirt. When it is the base,
        # the base stays — it is the outfit — and the short-sleeved layer over it goes.
        off = lower if lower in _SHED_ORDER else _upper
        if off in _SHED_ORDER and picks.get(off):
            picks[off] = None
            done.append((off, None, "sleeve"))
    if done and warm_before and not _still_warm(picks, wd.by_item, plan_temp):
        done += _rewarm(picks, wd, plan_temp, user_rules)

    over = sum(1 for c in _TORSO if picks.get(c)) - max_layers(picks, wd.by_item, plan_temp)
    warm = _still_warm(picks, wd.by_item, plan_temp)
    for slot in _SHED_ORDER:
        if over <= 0:
            break
        if not picks.get(slot):
            continue
        trial = {**picks, slot: None}
        # Never shed somebody into the cold: if what is left has no garment warm
        # enough for the morning and what was there did, that layer was doing a job.
        if warm and not _still_warm(trial, wd.by_item, plan_temp):
            continue
        picks[slot] = None
        done.append((slot, None, "budget"))
        over -= 1
    return done
