"""
check.py — the one fact check an outfit passes (2026-10-11 refactor).

The advisor (advisor.py) CHOOSES; this says what is objectively wrong with a choice,
in sentences the advisor can act on. It never changes a garment. A failed check goes
back to the model with the reasons, and only fallback.py — the last resort, when the
model has had its revisions — edits a pick.

Before this, thirteen code passes changed garments after the model answered, each
one blind to the others, and a polo went over a polo because one of them added it
(2026-10-11). Facts are checked here once; taste is the model's.

HARD issues are the ones a person would call wrong, not merely a matter of taste:
the outfit cannot be worn as given (an unknown garment, one garment in two places,
a rule they made), or it leaves them undressed, cold, overheated or wearing two tops.
A revision may never add a hard issue the first answer did not have (see
advisor._better). SOFT issues are worth one more try but never block an answer.
"""
from dataclasses import dataclass

import layers
import picks as pk
import reroll
import rules
import sleeves
import style
from llm import _peak_temp, _plan_temp

TORSO = ("base", "mid", "outer")
HOT_DAY_C = 24      # the coldest felt hour at or above this: no layer (llm._weather_flags' line)
# A top is worn ONCE. These are tops however warm they are: a knit polo is still a
# polo. A button-up `shirt` is left out on purpose — open over a tee it is a layer.
TOPS = frozenset({"t_shirt", "polo", "tank", "blouse"})


@dataclass(frozen=True)
class Issue:
    kind: str       # stable key, for comparing two answers ("no-footwear", "cold", …)
    text: str       # what the model is told
    hard: bool


@dataclass(frozen=True)
class Day:
    """Everything a check reads about today and this person."""

    w: dict
    wd: "pk.Wardrobe"
    prefs: "pk.Prefs"
    plan: float     # the coldest felt hour: warm enough for this
    peak: float     # the warmest: not overdressed for this

    @classmethod
    def of(cls, w: dict, wd: "pk.Wardrobe", prefs: "pk.Prefs") -> "Day":
        plan = _plan_temp(w)
        return cls(w, wd, prefs, plan, _peak_temp(w, plan))

    @property
    def look(self) -> "style.Look":
        look = self.prefs.look
        return look if isinstance(look, style.Look) else style.Look()

    @property
    def rules(self) -> list[dict]:
        return list(self.prefs.rules)

    def can_fill(self, slot: str, picks: dict) -> bool:
        """Do they own something unused, legal and warm enough for this slot?"""
        return pk._has_suitable_alternative(slot, {**picks, slot: None}, self.wd, self.plan, self.rules)

    def owns_for(self, slot: str, picks: dict) -> bool:
        """The same, ignoring pairing rules: a top that clashes with every pair of
        trousers they own does not make the trousers optional — it makes the top the
        wrong choice. Raised by the pre-push reviewer, 2026-10-11."""
        outright = [r for r in self.rules if not rules.is_combination(r)]
        return pk._has_suitable_alternative(slot, {**picks, slot: None}, self.wd, self.plan, outright)


def issues(picks: dict, day: Day) -> list[Issue]:
    """Everything objectively wrong with these picks, worst first."""
    wd = day.wd
    worn = {s: i for s, i in picks.items() if i and i in wd.ids}
    return [*_unknown(picks, day), *_legal(worn, day), *_dressed(worn, day),
            *_comfortable(worn, day), *_taste(worn, day)]


def _name(day: Day, iid: str) -> str:
    return str(day.wd.by_item[iid].get("label") or "that garment")


def _unknown(picks: dict, day: Day) -> list[Issue]:
    return [Issue(f"unknown-{slot}", f"{slot}: '{iid}' is not in the wardrobe — use a listed handle or null", True)
            for slot, iid in picks.items() if iid and iid not in day.wd.ids]


def _legal(worn: dict, day: Day) -> list[Issue]:
    """Can it be worn as given: once each, in a slot it fits, within their rules."""
    wd = day.wd
    out: list[Issue] = []
    where: dict[str, str] = {}
    for slot, iid in worn.items():
        if iid in where:
            out.append(Issue(f"twice-{iid}", f"{_name(day, iid)} is in both {where[iid]} and {slot} — "
                             "one garment, one slot", True))
        where.setdefault(iid, slot)
        if slot not in (wd.by_roles.get(iid) or ()):
            out.append(Issue(f"role-{slot}", f"{_name(day, iid)} cannot be worn as {slot} (it can be: "
                             f"{'/'.join(wd.by_roles.get(iid) or [])})", True))
    out += [Issue(f"rule-{v['slot']}", f"breaks their rule: {v['why']}", True)
            for v in rules.violations(day.rules, worn, wd.by_item)]
    if wd.by_group.get(worn.get("base")) == "onepiece" and worn.get("bottoms"):
        out.append(Issue("onepiece", f"{_name(day, worn['base'])} covers the legs — leave bottoms empty", True))
    return out


def _dressed(worn: dict, day: Day) -> list[Issue]:
    """A top, trousers (or a one-piece) and shoes — when they own them."""
    out: list[Issue] = []
    if not any(worn.get(c) for c in TORSO):
        # Only where they own a top: otherwise it is a wardrobe gap (gaps.py), and
        # asking again cannot help. An undershirt alone is always fixable — take it
        # off. Raised by the pre-push reviewer, 2026-10-11.
        if any(day.owns_for(c, worn) for c in TORSO):
            out.append(Issue("no-top", "nothing on top", True))
        elif worn.get("inner"):
            out.append(Issue("inner-alone", "the undershirt cannot be worn on its own", True))
    onepiece = day.wd.by_group.get(worn.get("base")) == "onepiece"
    for slot, what in (("bottoms", "trousers"), ("footwear", "shoes")):
        if not worn.get(slot) and not (slot == "bottoms" and onepiece) and day.owns_for(slot, worn):
            out.append(Issue(f"no-{slot}", f"no {what}, though they own suitable ones", True))
    return out


def _comfortable(worn: dict, day: Day) -> list[Issue]:
    """Warm enough for the coldest hour, not overdressed for the warmest, dry feet in
    snow. Cold only where something they own would fix it — otherwise it is a gap in
    the wardrobe (gaps.py), and asking again cannot help."""
    wd = day.wd
    out: list[Issue] = []
    torso = [worn[c] for c in TORSO if worn.get(c)]
    if torso and not layers._still_warm(worn, wd.by_item, day.plan) and not layers.too_cold_for_outfit(
            worn, wd, day.plan, day.rules, day.peak):
        out.append(Issue("cold", f"nothing on top is warm enough for the coldest hour ({day.plan:.0f}C felt) — "
                         "add knitwear or a jacket they own", True))
    out += [Issue(f"hot-{slot}", f"{_name(day, iid)} is too warm as {slot} for the warmest hour "
                  f"({day.peak:.0f}C felt)", True)
            for slot, iid in worn.items()
            if layers.overdressed(wd.by_item[iid], slot, wd, day.plan, day.peak, day.rules)]
    # A hot day wants no layer at all — not even an open shirt over the tee (user,
    # 2026-07-15: "no outer/mid recommendations when the weather is hot"). Found by
    # the live test days, 2026-10-11. The same line the prompt's hot-day flag uses.
    if day.plan >= HOT_DAY_C:
        out += [Issue(f"hot-{slot}", f"{_name(day, worn[slot])} as {slot}: no layer is needed on a hot day", True)
                for slot in ("mid", "outer") if worn.get(slot)]
    if day.w.get("isSnow"):
        out += [Issue(f"snow-{slot}", f"snow today: wear their waterproof {slot}", True)
                for slot in ("footwear", "outer")
                if not (wd.by_item.get(worn.get(slot)) or {}).get("waterproof") and any(
                    it.get("waterproof") and slot in (wd.by_roles.get(i) or ()) and i not in worn.values()
                    # a pair they have banned cannot be demanded (pre-push reviewer, 2026-10-11)
                    and not rules.violations(day.rules, {**worn, slot: i}, wd.by_item)
                    for i, it in wd.by_item.items())]
    return out


def _taste(worn: dict, day: Day) -> list[Issue]:
    """What a person would not wear: two tops stacked (hard); sleeves showing, too
    many layers, a style rule, the same garment after asking for another (soft)."""
    wd = day.wd
    out: list[Issue] = []
    torso = [worn[c] for c in TORSO if worn.get(c)]
    if stacked(worn, wd.by_item):
        out.append(Issue("stacked", " over ".join(_name(day, i) for i in reversed(torso))
                         + " — two tops stacked; warmth comes from knitwear or a jacket", True))
    out += [Issue(f"sleeve-{lo}", f"long-sleeved {_name(day, worn[lo])} under short-sleeved "
                  f"{_name(day, worn[hi])} — the cuffs show", False)
            for lo, hi in sleeves.sleeve_clashes(worn, wd.by_item)]
    n, cap = sum(1 for c in ("inner", *TORSO) if worn.get(c)), layers.max_layers(worn, wd.by_item, day.plan)
    if n > cap:
        out.append(Issue("layers", f"{n} torso layers; today needs at most {cap}", False))
    out += [Issue(f"style-{slot}", f"{slot}: {why}", False)
            for slot, why in style.violations(worn, wd.by_item, day.look)]
    out += [Issue(f"repeat-{slot}", f"{slot}: the same {_name(day, worn[slot])} as the outfit they asked to change, "
                  "though something else of theirs suits today", False)
            for slot in reroll.repeated_slots(worn, day.prefs.shown_map, wd, day.plan, day.rules, day.peak)]
    return out


def stacked(picks: dict, by_item: dict) -> bool:
    """Two tops, or two of the same kind, on the torso — THE stacking rule, shared by
    this check and the fallback so neither can undo the other."""
    worn = [by_item[picks[c]] for c in TORSO if picks.get(c) in by_item]
    kinds = [it.get("type") for it in worn if it.get("type")]
    return sum(1 for it in worn if it.get("type") in TOPS) > 1 or len(kinds) != len(set(kinds))


def hard(found: list[Issue]) -> set[str]:
    return {i.kind for i in found if i.hard}
