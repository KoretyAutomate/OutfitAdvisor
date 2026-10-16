"""picks.py — holding an outfit to the rules, once the model has proposed one.

Since the 2026-10-11 refactor: the wardrobe index, preferences, handles and the
"could anything else fill this slot" search that check.py, fallback.py and gaps.py
share. The repair passes that lived here are gone — advisor.py asks again instead.

Split out of closet.py on 2026-08-27, when it crossed the 600-line ceiling. The
division is the one the module already had: closet.py builds the prompt and runs
the conversation, and everything here judges the ANSWER — which items may sit in
which slots, whether the outer layer is warm enough, whether the wearer's own bans
are kept, whether anybody is dressed at the end of it, and which empty slots mean
the wardrobe is genuinely short of a garment.

The WORDS moved to prose.py on 2026-08-29, at the same ceiling and on the same
division: here the garments, there the sentences that describe them.

The through-line, from the PPK week onwards: a model is asked, and then checked.
"""

from dataclasses import dataclass

import handles as _handles
import rules
import scale

# Re-exported: the naming moved to handles.py at the 600-line ceiling (2026-09-01),
# and closet.py reads them through this module — one import site rather than a churn
# of call sites for a move that changed no behaviour.
handles_for = _handles.handles_for
resolve_handles = _handles.resolve_handles
_unknown_ids = _handles._unknown_ids


@dataclass(frozen=True)
class Prefs:
    """What the wearer has told us, as opposed to what the weather has.

    One object rather than a growing tail of keyword arguments: every one of these
    has to reach both the prompt and the validation, and threading them separately
    is how a flag ends up honoured in one and ignored in the other.

    rules        prohibitions, already validated by rules.clean_rules()
    closet_only  the wardrobe is COMPLETE, so never suggest a garment they do not
                 own — an unfillable slot is a gap, not a shopping hint
    shown        what the wearer is already looking at, and asking to move on from
    skipped      why they did NOT wear recent suggestions, their words, newest last

    `shown` is the odd one out — it is what WE told THEM, not the reverse — and it
    lives here anyway for the reason in the paragraph above: it has to reach the
    prompt, which asks for a different outfit, and the validation, which checks it
    got one. Those two disagreeing is the whole bug it exists to fix.
    """

    rules: tuple = ()
    closet_only: bool = False
    #: garments the wearer keeps choosing for a slot — a hint, never a constraint
    prefers: tuple = ()
    #: {slot: item id} already on screen for today; empty on the day's first ask
    shown: tuple = ()
    look: object = None   # style.Look — register, gender, the wearer's look votes
    #: reasons recent suggestions went unworn — already cleaned by the schema
    skipped: tuple = ()

    @classmethod
    def of(cls, rules_list: list[dict] | None, closet_only: bool = False,
           prefers: list[dict] | None = None,
           shown: dict | None = None,
           skipped: list[str] | None = None) -> "Prefs":
        # A tuple of pairs, because Prefs is frozen and hashable and a dict is
        # neither. `shown_map` below is what every reader actually wants.
        return cls(tuple(rules_list or []), closet_only, tuple(prefers or []),
                   tuple(sorted((shown or {}).items())), skipped=tuple(skipped or ()))

    @property
    def shown_map(self) -> dict:
        return dict(self.shown)


# Slots a hot day may legitimately leave EMPTY. Nobody is underdressed for want of
# a mid layer in August; they are underdressed for want of trousers, which is why
# the rest are swapped for something cooler or left alone.
# `inner` belongs here for the same reason the prompt has always said "Inner: None
# needed" on a hot day: an undershirt is optional. Without it, somebody whose only
# undershirt is a thermal was told to wear it in 32C, because there was nothing
# cooler to swap in. Raised by the pre-push reviewer, 2026-09-01.
_SHEDDABLE = ("inner", "mid", "outer", "accessories")

# What you are still wearing at three in the afternoon. The rest comes off when it
# warms up — that is what a layer IS — so the two are judged against different hours.
_ALL_DAY = ("inner", "base", "bottoms", "footwear")


def _heat_temp(slot: str, plan_temp: float, peak_temp: float) -> float:
    """Which hour decides whether this garment is too warm.

    The floor is always the morning: you have to be warm enough for the coldest
    moment you are out in. The ceiling is not the same hour. A mid layer put on at
    23C comes off at noon and is judged by the morning it was chosen for; a pair of
    trousers is worn through the 32C afternoon and has to be right for it.

    The first draft judged everything by the morning, which on a 18C-to-32C day let
    warmth-3 trousers through on exactly the reasoning that produced the complaint.
    Raised by the pre-push reviewer, 2026-09-01.
    """
    return max(plan_temp, peak_temp) if slot in _ALL_DAY else plan_temp


# Words that name a garment, from the taxonomy the app already has. A bullet that
# uses one of these is recommending a THING to put on, as opposed to giving advice
# about the weather.
def _suitable_for(slot: str, picks: dict, wd: "Wardrobe",
                  plan_temp: float, user_rules: list[dict],
                  hot_temp: float | None = None) -> str | None:
    """The first owned garment that could legitimately fill this slot, or None.

    The search _has_suitable_alternative always did; it only ever reported whether
    one existed, and _enforce_a_top needs the garment itself.

    The trial outfit is the one that would actually be WORN, which for a one-piece
    means without the trousers it replaces. Judging a dress against the bottoms
    still in the slot let a rule banning that pairing reject the dress — and if it
    was the only top, the wearer was left with none, on account of a garment that
    would have been taken off. Raised by the pre-push reviewer, 2026-08-29.
    """
    for iid, item in wd.by_item.items():
        if iid in picks.values():
            continue                              # already worn somewhere else
        if slot not in (wd.by_roles.get(iid) or ()):
            continue
        if slot == "outer" and not scale.warm_enough(item, plan_temp):
            continue
        # `hot_temp` is set only when the CALLER is cooling somebody down, and it is
        # the hour THAT SLOT is judged by — the cold stays on plan_temp above, so a
        # replacement chosen for the afternoon still has to survive the morning.
        #
        # Off everywhere else, deliberately: the gap check asks whether the wardrobe
        # owns anything legal, and a garment that is too warm is still one they own —
        # refusing it there would report a gap for a wardrobe that has an answer.
        if hot_temp is not None and scale.too_warm(item, hot_temp):
            continue
        trial = {**picks, slot: iid}
        if slot == "base" and wd.by_group.get(iid) == "onepiece":
            trial["bottoms"] = None
        if rules.violations(user_rules, trial, wd.by_item):
            continue
        return iid
    return None


def _has_suitable_alternative(slot: str, picks: dict, wd: "Wardrobe",
                              plan_temp: float, user_rules: list[dict]) -> bool:
    """Could some OTHER owned garment have filled this slot properly?

    Reached when a pick was cleared for being unsuitable — too thin for the cold, or
    banned by the wearer. That says the CHOSEN garment was wrong; it does not say
    the wardrobe is short of one. If a warm enough, legal alternative is sitting
    there unused, recording a gap would eventually recommend buying a coat the
    person already owns.

    Judged by the same rules that did the clearing, so an alternative this accepts
    is one the generator could legitimately have picked.
    """
    return _suitable_for(slot, picks, wd, plan_temp, user_rules) is not None


@dataclass(frozen=True)
class Wardrobe:
    """The lookups every validation step reads, as one thing.

    They are always used together, and passing them separately grew the signatures
    past what anyone can read — and, worse, made it possible to hand one function an
    index over a different list from another. Built once from the already-filtered
    wardrobe the prompt was built from; an index over anything else is how a model
    gets to name an item the validator then rejects.
    """

    ids: frozenset
    by_cat: dict
    by_roles: dict
    by_group: dict
    by_item: dict


def _index(closet: list[dict]) -> Wardrobe:
    return Wardrobe(
        frozenset(i["id"] for i in closet),
        {i["id"]: i["category"] for i in closet},
        # What each item is ALLOWED to be today. app.py has already normalized these
        # (inner closed, empty -> [category]), so this is a straight read.
        {i["id"]: (i.get("roles") or [i["category"]]) for i in closet},
        {i["id"]: i.get("group") for i in closet},
        {i["id"]: i for i in closet},
    )
