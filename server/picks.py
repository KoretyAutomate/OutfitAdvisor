"""picks.py — holding an outfit to the rules, once the model has proposed one.

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

from collections.abc import Callable
from dataclasses import dataclass

import rules
import scale
from llm import log
from vocab import CATEGORIES


@dataclass(frozen=True)
class Prefs:
    """What the wearer has told us, as opposed to what the weather has.

    One object rather than a growing tail of keyword arguments: every one of these
    has to reach both the prompt and the validation, and threading them separately
    is how a flag ends up honoured in one and ignored in the other.

    rules        prohibitions, already validated by rules.clean_rules()
    closet_only  the wardrobe is COMPLETE, so never suggest a garment they do not
                 own — an unfillable slot is a gap, not a shopping hint
    """

    rules: tuple = ()
    closet_only: bool = False
    #: garments the wearer keeps choosing for a slot — a hint, never a constraint
    prefers: tuple = ()

    @classmethod
    def of(cls, rules_list: list[dict] | None, closet_only: bool = False,
           prefers: list[dict] | None = None) -> "Prefs":
        return cls(tuple(rules_list or []), closet_only, tuple(prefers or []))


def _warmth_violations(picks: dict, by_item: dict, plan_temp: float) -> list[str]:
    """Slots whose pick is too thin for the cold. Currently `outer` only."""
    iid = picks.get("outer")
    if not iid:
        return []
    return [] if scale.warm_enough(by_item.get(iid) or {}, plan_temp) else ["outer"]


def _slot_mismatches(picks: dict, by_roles: dict) -> list[str]:
    """Slots holding an item that is not allowed to play that role.

    Previously this was a fixed table keyed on the item's single `category`, which
    stopped the model demoting a tee into `inner` — but also made every item's role
    permanent. That is wrong for real clothes: an oxford shirt IS the outer layer at
    30C and a base under a coat at 8C (user, 2026-08-10). So the allowed set now
    comes from the ITEM (`roles`, assigned by /classify and user-editable) rather
    than from one global table.

    The safety property that mattered is kept by normalize_roles(), not here: only
    genuine underwear ever carries the `inner` role, and an item that carries it
    carries nothing else.
    """
    return [
        c for c, v in picks.items()
        if v and c not in (by_roles.get(v) or ())
    ]


def _relocate_mismatches(picks: dict, wrong: list, by_roles: dict) -> list:
    """Move a misfiled garment to a slot it CAN play, rather than dropping it.

    The model files a garment one slot off — a hoodie whose only role is `mid` put
    into `base` — and the old repair cleared the slot. That threw away a top the
    wearer owns and had been given: on 2026-08-29 a 15-item closet came back with
    the joggers and nothing above the waist, because the one top the model chose was
    filed as `base`, cleared for it, and never reconsidered. The user saw an outfit
    with no shirt (reported the same morning).

    Clearing is right for an item that cannot go anywhere — a bottom in a top slot
    with `bottoms` already filled. It is wrong for one that has an empty slot of its
    own waiting, which is the common case, because the mistake is a filing error and
    not a judgement about the garment.

    Every misfiled slot is emptied BEFORE any target is chosen, because the slots
    they belong in are often each other's: a mid-only hoodie in `base` and a
    base-only shirt in `mid` is one swap, and choosing targets as we went made the
    first garment see an occupied slot and be dropped for it — a real outfit lost to
    iteration order. Raised by the pre-push reviewer, 2026-08-29.

    Returns the moves made, for the log. Anything unplaceable is cleared as before.
    """
    misfiled = {c: picks[c] for c in wrong}
    for c in wrong:
        picks[c] = None
    moved = []
    for c, item in misfiled.items():
        target = next((r for r in (by_roles.get(item) or ())
                       if r in CATEGORIES and not picks.get(r)), None)
        if target:
            picks[target] = item
            moved.append((c, target))
    return moved


def _inner_left_bare(picks: dict, by_group: dict) -> bool:
    """Is the undershirt the outermost thing on the torso?

    inner is UNDERWEAR (user, 2026-08-29). An undershirt with nothing over it is not
    a lighter outfit for a hot day, it is somebody sent out in their underwear — and
    it is a plausible-looking answer for a model that has been told to drop layers
    as the temperature rises, which is exactly the shape of mistake this module
    exists to catch in code rather than hope about in prose.

    A one-piece in base covers the torso, so it satisfies this like any other top.
    """
    if not picks.get("inner"):
        return False
    return not any(picks.get(c) for c in ("base", "mid", "outer"))


def _onepiece_conflicts(picks: dict, by_group: dict) -> bool:
    """Clear `bottoms` when `base` holds a one-piece garment. True if it did.

    A dress covers the torso AND the legs, but `picks` has one item per slot and
    _dedupe_picks forbids one id in two of them, so the honest encoding is: the
    one-piece takes `base`, and `bottoms` is not needed rather than not owned.
    Mutates `picks`, like the other repairs in this module.

    In code rather than in the prompt, per plan amendment 3 — the prompt says it
    too, but "trousers under a dress" is exactly the kind of plausible-looking
    answer a model produces when the wardrobe has both.
    """
    base = picks.get("base")
    if base and picks.get("bottoms") and by_group.get(base) == "onepiece":
        log.warning("closet picks: %s is a one-piece, cleared bottoms", base)
        picks["bottoms"] = None
        return True
    return False


def _dedupe_picks(picks: dict, by_cat: dict) -> dict:
    """Keep a duplicated item in ONE slot; null it everywhere else.

    The item's own category decides which slot it keeps — a garment classified as
    `base` stays in `base` and is dropped from `inner`. When the category is not
    among the slots it was duplicated into, the first slot in CATEGORIES order
    wins, so the outcome is deterministic rather than dict-order dependent.

    A nulled slot is not a hole: app.py keeps the rule engine's generic
    recommendation for null picks (F3, 2026-07-15), so the user still gets told
    what to wear there — just not the garment they are already wearing elsewhere.
    """
    out = dict(picks)
    chosen = [v for v in out.values() if v]
    for item_id in {v for v in chosen if chosen.count(v) > 1}:
        slots = [c for c in CATEGORIES if out.get(c) == item_id]
        keep = by_cat.get(item_id) if by_cat.get(item_id) in slots else slots[0]
        for c in slots:
            if c != keep:
                out[c] = None
        log.warning("closet picks: %s was in %s, kept only %s", item_id, slots, keep)
    return out


def _enforce_underwear(picks: dict, by_item: dict, banned: list[dict],
                       attempt: int) -> tuple[str, list[dict]]:
    """Never send anybody out in their undershirt.

    Retried once — a regeneration can put a top back on, which is a better outfit
    than one layer fewer. Out of retries the undershirt is cleared instead: an empty
    inner slot is invisible under a shirt nobody is wearing either, and the bullets
    that named it go with it.
    """
    if not _inner_left_bare(picks, {}):
        return "", banned
    if attempt == 0:
        return ("Your last reply put the undershirt on its own, with nothing over "
                "it. inner is UNDERWEAR — if there is nothing to wear over it, "
                "leave inner null as well. "), banned
    item = by_item.get(picks["inner"])
    log.warning("closet picks: inner cleared — nothing was worn over it")
    picks["inner"] = None
    return "", ([*banned, item] if item else banned)


def _enforce_onepiece(picks: dict, by_group: dict, by_item: dict,
                      banned: list[dict], attempt: int) -> tuple[str, list[dict]]:
    """Trousers under a dress.

    _onepiece_conflicts REPAIRS as it tests — it clears bottoms on either attempt —
    so the picks that come out are never a dress over trousers. What the retry buys
    is the BULLETS: only a regeneration can rewrite the line that recommended the
    trousers. Out of retries, the garment joins the banned list instead, so the
    prose is held to the same standard as the picks rather than left recommending
    something that is no longer part of the outfit.
    """
    dropped = by_item.get(picks.get("bottoms")) if picks.get("bottoms") else None
    if not _onepiece_conflicts(picks, by_group):
        return "", banned
    if attempt == 0:
        return (
            "Your last reply put bottoms under a one-piece garment. A dress, "
            "jumpsuit or pair of dungarees already covers the legs — leave "
            "bottoms null and say so in its bullet. "
        ), banned
    return "", ([*banned, dropped] if dropped else banned)


def _enforce_user_rules(picks: dict, by_item: dict,
                        user_rules: list[dict] | None, attempt: int) -> tuple[str, list[dict]]:
    """Hold the outfit to the wearer's own prohibitions.

    Checked, not merely asked for. The prompt carries the rules as prose, and prose
    in a prompt is followed most of the time — which is not the same as followed.
    "This combination shall be banned" is a promise the user is entitled to see kept
    every morning, not most mornings (2026-08-24).

    Returns a corrective note to retry with on the first attempt. On the second it
    repairs instead, clearing the offending slot: an empty slot is a smaller wrong
    than a forbidden one, and the bullet still reads.
    """
    broke = rules.violations(user_rules or [], picks, by_item)
    if not broke:
        return "", []
    if attempt == 0:
        detail = "; ".join(b["why"] for b in broke)
        return (
            f"Your last reply broke rules the wearer set: {detail}. "
            "These are not preferences to balance against the weather — they are "
            "prohibitions. Choose differently, or use null for that slot. "
        ), []
    cleared = []
    for b in broke:
        iid = picks.get(b["slot"])
        item = by_item.get(iid) if iid else None
        if item:
            cleared.append(item)
        log.warning("closet picks: %s cleared — %s", b["slot"], b["why"])
        picks[b["slot"]] = None
    return "", cleared


def _enforce_one_slot_each(picks: dict, by_cat: dict, attempt: int) -> tuple[str, dict]:
    """One garment cannot fill two slots.

    The prompt says inner is an undershirt and base is the visible top, but saying
    it was never enough — with a small closet the model happily returns the same id
    for both, and checking only that ids EXIST shipped "wear your tee under your
    tee". Same class as plan amendment 3: validate in code, never hope in prose.

    Retried once, then resolved here rather than throwing away the whole closet
    answer and falling back to generic advice.
    """
    chosen = [v for v in picks.values() if v]
    dup = sorted({v for v in chosen if chosen.count(v) > 1})
    if not dup:
        return "", picks
    if attempt == 0:
        return (
            f"Your last reply put the same item in more than one slot: {dup}. "
            "One garment is worn in exactly ONE slot — an undershirt is not also "
            "the visible top. Use a different item, or null. "
        ), picks
    return "", _dedupe_picks(picks, by_cat)


# Words that name a garment, from the taxonomy the app already has. A bullet that
# uses one of these is recommending a THING to put on, as opposed to giving advice
# about the weather.
def _suitable_for(slot: str, picks: dict, wd: "Wardrobe",
                  plan_temp: float, user_rules: list[dict]) -> str | None:
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
        trial = {**picks, slot: iid}
        if slot == "base" and wd.by_group.get(iid) == "onepiece":
            trial["bottoms"] = None
        if rules.violations(user_rules, trial, wd.by_item):
            continue
        return iid
    return None


#: The layers that count as being dressed above the waist, in the order a missing
#: top is filled: the ordinary top first, then a mid layer, then a coat. Reaching
#: `outer` means the wardrobe holds nothing else — a coat over an undershirt is odd,
#: and it is still an answer rather than no top at all.
_TOP_SLOTS = ("base", "mid", "outer")


def _enforce_a_top(picks: dict, wd: "Wardrobe", plan_temp: float,
                   user_rules: list[dict]) -> tuple | None:
    """Nobody is dressed by their trousers alone.

    The user was sent out on 2026-08-29 with joggers and nothing above the waist:
    the model filed its one top as `base`, the role check cleared it for being a
    `mid`, and the undershirt went with it. _relocate_mismatches fixes that
    particular mistake; this catches the CLASS, because every repair in this module
    can empty a slot and none of them asks what is left.

    Only when the wardrobe can actually cover it. A closet with no wearable top is
    genuinely short of one, and inventing a garment is what closetOnly exists to
    stop — the empty slots are then reported as the gap they are.
    """
    if any(picks.get(c) for c in _TOP_SLOTS):
        return None
    for slot in _TOP_SLOTS:
        iid = _suitable_for(slot, picks, wd, plan_temp, user_rules)
        if iid:
            picks[slot] = iid
            return slot, iid
    return None


def _added_top_line(added: tuple, by_item: dict) -> str:
    """Say so in the prose. A garment in the picture and not in the text reads as a
    bug in the app, and this one is there precisely because the model did not put
    it there."""
    label = str((by_item.get(added[1]) or {}).get("label") or "").strip()
    return (f"{label or 'A top from your closet'} — the rest of the outfit left you "
            "with nothing above the waist.")


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


def _missing_slots(claimed: object, picks: dict, filled_before: set,
                   covered: set | None = None,
                   can_fill: Callable[[str], bool] | None = None,
                   unsuitable: set | None = None) -> list[str]:
    """Which empty slots are a GAP IN THE WARDROBE, rather than a warm day.

    Two sources, because the model only knows about one of them.

    What it claims: slots it left null because nothing suitable was listed. Filtered
    to the ones that are actually empty — a model naming a slot it then filled would
    have the phone remembering a gap that never existed.

    What VALIDATION emptied: a slot the model filled and this module then cleared —
    a duplicate, an item in a role it cannot play, a garment too thin for the cold,
    one the wearer has banned. Every one of those means the wardrobe had nothing
    legal for that slot, which is exactly a gap; and because the model believed it
    was filled, it never appears in `claimed`. Without this the slot reads "None
    needed" — the weather excused it — and the shopping list never hears about it.

    `covered` names slots emptied because something else already covers them —
    bottoms under a dress. Those are not holes in the wardrobe. It is passed in
    rather than assumed: excluding `bottoms` outright also hid a REAL bottoms gap
    whenever validation cleared a pick there for any other reason.
    """
    covered = covered or set()
    unsuitable = {c for c in (unsuitable or set()) if c not in covered}
    seq = claimed if isinstance(claimed, list) else []
    # `covered` filters BOTH sources. A slot something else already covers is not a
    # gap however it came to be named — and the model naming it anyway is the likely
    # case, not the exotic one: asked for the slots it could not fill, "bottoms"
    # under a dress is a plausible thing for it to say.
    named = [c for c in seq
             if c in CATEGORIES and not picks.get(c) and c not in covered]
    emptied = [c for c in filled_before if not picks.get(c) and c not in covered]
    # Two kinds of empty slot, and only one of them is a MISCHOICE.
    #
    # The model can pick an item for a role it cannot play, or the same garment
    # twice. Validation clears that, but another item may fill the slot perfectly
    # well — the wardrobe was never short, the choice was wrong. Those are checked
    # against what else is owned.
    #
    # The rest are judgements about the GARMENT: a shell too thin for the cold, an
    # item the wearer has banned, or the model reporting it found nothing suitable
    # at all. In every one of those the wardrobe's contents were in front of the
    # judge and were found wanting, which is exactly the gap this feature exists to
    # notice — a closet holding only a warmth-2 shell must be able to learn that it
    # needs a warmer coat, not merely that it owns no coat.
    # `can_fill` is the SAME suitability test the clearing steps use — is there an
    # unused, warm enough, legal garment for this slot. An aggregate "does anything
    # own this role" set was too coarse: one shirt that can play base OR mid, left
    # in base by the deduplicator, advertised `mid` as filled and hid a real gap.
    # Skipped when the test is unavailable, because a check that cannot run must not
    # silently pass everything.
    # The model's own claim gets the same treatment. It is a judgement, and a
    # judgement about a wardrobe this module can inspect directly: if an unused,
    # warm enough, legal garment is sitting there, the slot was misclassified — and
    # one such mistake would otherwise be kept for ninety days and end as a
    # recommendation to buy something already owned.
    #
    # `unsuitable` skips the test because it has already been through it: those
    # slots were only marked after _has_suitable_alternative found nothing.
    candidates = (set(named) | set(emptied)) - set(unsuitable)
    if can_fill is not None:
        candidates = {c for c in candidates if not can_fill(c)}
    return sorted(candidates | (set(unsuitable) & (set(named) | set(emptied))),
                  key=CATEGORIES.index)


def handles_for(closet: list[dict]) -> dict:
    """A SHORT name per wardrobe item, for the model to answer with.

    The ids the phone generates are UUIDs — `itm-e27af5ac-6454-44ed-9a7e-3ddb...`.
    Asking a model to copy one back exactly is asking it to transcribe 32 random hex
    digits, and it gets them nearly right: on 2026-08-29 and again on 2026-08-30 the
    same real garment came back as `...-9a7e-3ddb08307222` and `...-9a7a-5ed294a3f494`,
    matching for 25 characters and differing after. Both were rejected as unknown
    ids, both attempts, and the user was told their closet had nothing wearable —
    twice, on consecutive days, with fifteen items registered.

    So the prompt never shows a UUID. `i1`..`iN` in listing order, mapped back here.
    A short handle is one token, and a model that miscopies it produces something
    that is obviously not a handle rather than something that looks like an id.
    """
    return {f"i{n}": i["id"] for n, i in enumerate(closet, 1)}


def resolve_handles(picks: dict, handles: dict, ids: frozenset | set) -> dict:
    """Handles back to real ids, for everything downstream.

    A real id is passed through untouched: the model may answer with one from the
    prefers block or from its own memory of the conversation, and rejecting an id
    that names the right garment would be a validation error of our own making.
    Anything that is neither stays as it is, to be caught by _unknown_ids and
    reported to the model in the handle vocabulary it was given.
    """
    out = {}
    for slot, v in picks.items():
        key = str(v).strip() if v else v
        out[slot] = handles.get(key, v) if key and key not in ids else v
    return out


def _unknown_ids(picks: dict, valid_ids: frozenset | set) -> str:
    """A corrective note naming ids that are not in the wardrobe, or "" if all are.

    An id the model invented cannot be looked up, so every check after this one
    would be reading an empty dict and quietly passing.
    """
    bad = [v for v in picks.values() if v is not None and v not in valid_ids]
    if not bad:
        return ""
    return (f"Your last reply used ids not present in the wardrobe: {bad}. "
            "Use ONLY listed ids or null. ")


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
