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
import rules
import scale

SLEEVES = ("short", "long", "none")

# The torso, bottom to top. `outer` is left out of the sleeve rule: a gilet is
# sleeveless on purpose, and a short-sleeved jacket over a long sleeve is rare
# enough that guessing at it would cost more than it saves.
_SLEEVE_STACK = ("inner", "base", "mid")
_TORSO = ("inner", "base", "mid", "outer")

# What is shed first when the budget is exceeded. The undershirt goes before the
# cardigan: it is optional, invisible, and it was the layer in the complaint. The
# mid layer is the one that comes off by noon anyway. Never the base, never the
# outer.
_SHED_ORDER = ("inner", "mid")

# Read off the NAME, for garments saved before the field existed. Checked long ->
# none -> short, so "long-sleeve tee" is long and not a tee's default. English and
# the Japanese the wearer actually writes ("ロンT" is how a long-sleeve tee is
# sold in Japan).
_LONG = re.compile(r"long[\s\-]*(sleeve[sd]?|t\b|tee)|longsleeve|\bl/s\b|長袖|ロン\s*[tTｔＴ]",
                   re.IGNORECASE)
_NONE = re.compile(r"sleeveless|\btank\b|camisole|\bcami\b|ノースリーブ|タンク", re.IGNORECASE)
_SHORT = re.compile(r"short[\s\-]*sleeve[sd]?|\bs/s\b|半袖", re.IGNORECASE)

# What a KIND implies when neither the wearer nor the name says. Only kinds where
# the answer is near-universal: a "tee" with no qualifier is short-sleeved, a
# cardigan is long. Shirts and thermals come both ways, so they stay unknown — and
# an unknown sleeve never triggers the rule. Guessing wrong would take away a
# garment the wearer chose for no reason they could see.
TYPE_SLEEVE = {
    "t_shirt": "short", "polo": "short", "tank": "none", "waistcoat": "none",
    "sweater": "long", "cardigan": "long", "hoodie": "long", "fleece": "long",
}


def sleeve_of(item: dict) -> str | None:
    """The garment's sleeve: stated, else read from its name, else its kind's."""
    s = item.get("sleeve")
    if s in SLEEVES:
        return s
    label = str(item.get("label") or "")
    for pat, answer in ((_LONG, "long"), (_NONE, "none"), (_SHORT, "short")):
        if pat.search(label):
            return answer
    return TYPE_SLEEVE.get(str(item.get("type") or ""))


def sleeve_clashes(picks: dict, by_item: dict) -> list[tuple[str, str]]:
    """(lower, upper) pairs where a long sleeve sits under a short one."""
    worn = [(c, sleeve_of(by_item.get(picks[c]) or {})) for c in _SLEEVE_STACK if picks.get(c)]
    return [(lo, hi) for i, (lo, s_lo) in enumerate(worn) if s_lo == "long"
            for hi, s_hi in worn[i + 1:] if s_hi == "short"]


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


def _short_inner(picks: dict, wd, plan_temp: float, user_rules: list[dict]) -> str | None:
    """An owned undershirt that does not reach past the sleeve above it."""
    for iid, item in wd.by_item.items():
        if iid in picks.values() or "inner" not in (wd.by_roles.get(iid) or ()):
            continue
        if sleeve_of(item) not in ("short", "none"):
            continue
        if scale.too_warm(item, plan_temp):
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
        if picks.get(slot):
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
    return f"{label or 'A warmer layer'} — for the morning chill; take it off when it warms up."


_SLOT_WORDS = {"inner": ("inner", "undershirt"), "base": ("base",),
               "mid": ("mid-layer", "mid layer", "mid"), "outer": ("outer", "jacket", "coat")}
_UNNEEDED = re.compile(r"\b(no|none|not needed|not required|unnecessary|no need|skip)\b",
                       re.IGNORECASE)


def with_added(text: str, added: tuple, by_item: dict) -> str:
    """The advice text with the added garment's line on top, and the model's own
    line saying that slot is not needed taken out. Live, that line was "No mid-layer
    is needed as the heat makes a cardigan too warm" directly under a cardigan the
    repair had just put on — the outfit right and the words arguing with it.

    A line goes when it names the slot or the added garment's kind AND says it is
    not needed. Both, so "no rain, so sneakers" survives."""
    kind = str((by_item.get(added[1]) or {}).get("type") or "").replace("_", " ")
    words = [w for w in (*_SLOT_WORDS.get(added[0], (added[0],)), kind) if w]
    about = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
    kept = [ln for ln in text.split("\n")
            if not (ln.startswith("•") and about.search(ln) and _UNNEEDED.search(ln))]
    return f"• {added_line(added, by_item)}\n" + "\n".join(kept)


def tidy(picks: dict, wd, plan_temp: float, user_rules: list[dict]) -> list[tuple]:
    """Apply both rules to `picks` in place. Returns (slot, replacement or None, why).

    Sleeves first: the budget then counts the layers that are actually left.
    """
    done: list[tuple] = []
    warm_before = _still_warm(picks, wd.by_item, plan_temp)
    for lower, _upper in sleeve_clashes(picks, wd.by_item):
        if not picks.get(lower):
            continue                     # already taken off for an earlier pair
        alt = _short_inner(picks, wd, plan_temp, user_rules) if lower == "inner" else None
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
