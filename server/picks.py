"""picks.py — holding an outfit to the rules, once the model has proposed one.

Split out of closet.py on 2026-08-27, when it crossed the 600-line ceiling. The
division is the one the module already had: closet.py builds the prompt and runs
the conversation, and everything here judges the ANSWER — which items may sit in
which slots, whether the outer layer is warm enough, whether the wearer's own bans
are kept, whether the prose says the same thing the picks do, and which empty slots
mean the wardrobe is genuinely short of a garment.

The through-line, from the PPK week onwards: a model is asked, and then checked.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

import rules
from llm import log
from vocab import CATEGORIES, TYPE_LABEL


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


_OUTER_MIN_WARMTH = ((5, 4), (12, 3), (18, 2))


def _min_outer_warmth(plan_temp: float) -> int:
    for below, need in _OUTER_MIN_WARMTH:
        if plan_temp < below:
            return need
    return 1


def _warmth_violations(picks: dict, by_item: dict, plan_temp: float) -> list[str]:
    """Slots whose pick is too thin for the cold. Currently `outer` only."""
    iid = picks.get("outer")
    if not iid:
        return []
    item = by_item.get(iid) or {}
    return ["outer"] if (item.get("warmth") or 3) < _min_outer_warmth(plan_temp) else []


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


def _ban_terms(item: dict) -> list[list[str]]:
    """Ways the prose might name this garment. Each entry is a set of words that
    must ALL appear for a bullet to be about it.

    The label alone is not enough. A user labels an item "Airism" and the model
    writes "your white V-neck undershirt" — same garment, no shared word, and the
    line survives to recommend what was just banned. So the garment's own validated
    attributes are used as well: colour plus type is a description of the thing
    rather than a name for it, and it is what a model reaches for when the label is
    a brand.

    Requiring BOTH words keeps it honest — "white" alone would delete a bullet about
    white trainers, and an outfit missing lines it should have kept is its own bug.
    """
    terms: list[list[str]] = []
    label = str(item.get("label") or "").strip().lower()
    if len(label) >= 3:
        terms.append([label])
    kind = str(item.get("type") or "").strip().lower()
    words = [w for w in re.split(r"[^a-z]+", TYPE_LABEL.get(kind, kind).lower()) if len(w) > 2]
    colors = [str(c).strip().lower() for c in (item.get("colors") or []) if str(c).strip()]
    for word in words[:2]:
        for c in colors[:3]:
            terms.append([c, word])
    if terms:
        return terms
    # Nothing above fired: a label too short to be distinctive ("PJ") on an item
    # with no colours recorded. Falling through with an EMPTY list would leave the
    # prose free to recommend the very garment just cleared, which is the one thing
    # this function exists to prevent — so the garment's kind is used on its own.
    # Broader than the paired test, and deliberately: with the slot cleared nothing
    # of that kind is being worn, so a line naming one is about the item that went.
    fallback = words[:1] or [w for w in re.split(r"[^a-z]+",
                                                 str(item.get("group") or "").lower())
                             if len(w) > 2][:1]
    # Last resort, when a garment has no usable label, type or group left: match the
    # short label as a whole WORD, so "PJ" cannot fire inside "PJs are fine" by
    # accident of spelling while still catching the standalone mention.
    return [fallback] if fallback else ([[label]] if label else [])


def _term_hit(term: list[str], low: str) -> bool:
    """Every word in the term must appear. Short ones must appear as whole words."""
    return all(
        (re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low) is not None)
        if len(w) < 3 else (w in low)
        for w in term
    )


def _drop_banned_bullets(bullets: list[str], banned: list[dict]) -> list[str]:
    """Remove lines that still recommend a garment we had to clear.

    The bullets are what the user actually reads — in the app and in the morning
    notification. Nulling the structured pick and leaving the prose saying "the
    white undershirt under your white tee" would keep the ban's promise in the data
    and break it on screen, which is the half that matters.

    A bullet is free text, not keyed to a slot, so a line is judged by whether it
    NAMES the garment — see _ban_terms. Where that leaves the advice shorter, a line
    explains the gap rather than letting it look like an oversight.
    """
    if not banned:
        return bullets
    kept = [b for b in bullets if not _names_banned(b, banned)]
    if len(kept) != len(bullets):
        kept.append("Left a layer out — it broke one of your own rules.")
    return kept


def _names_banned(line: str, banned: list[dict]) -> bool:
    """Does this line recommend one of the garments we had to clear?"""
    low = line.lower()
    return any(_term_hit(t, low) for item in banned for t in _ban_terms(item))


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
_GARMENT_WORDS = frozenset(
    w for label in TYPE_LABEL.values()
    for w in re.split(r"[^a-z]+", label.lower()) if len(w) > 3
) | {"coat", "jacket", "shirt", "layer", "shoes", "boots", "trousers", "pants",
     "sweater", "knit", "vest", "gilet", "parka", "anorak", "mac"}


def _names_something_unowned(line: str, owned: list[tuple[str, bool]]) -> bool:
    """Does this line recommend a garment that is not in the wardrobe?

    Only asked when the wearer has declared their closet COMPLETE. Then a bullet
    naming a garment none of whose words match anything they own is, by their own
    statement, a recommendation to put on something that does not exist. The
    structured picks already say the slot is empty; leaving the prose saying "add a
    light shell" keeps the promise in the data and breaks it in the words — and the
    words are what the notification shows.

    A line that names no garment at all ("the wind will bite this morning") is
    advice, not a recommendation, and is kept.

    The test errs towards dropping. "Layer up as it warms" is advice and goes, and
    that is the right way round to be wrong: a lost hint costs a sentence, while a
    kept one costs the promise the tickbox makes. Whatever is dropped, the reader is
    told the advice is shorter and why.
    """
    low = line.lower()
    # What the line says about garments they DO own is struck out first, and the
    # question is asked of what is left.
    #
    # Asking whether an owned label appears anywhere let one mention exempt the
    # whole sentence: "Add a wool overcoat over your white t-shirt" contains an
    # owned t-shirt, so the overcoat rode along — the one recommendation the tickbox
    # exists to suppress, in the line the notification shows.
    for phrase, is_label in sorted(owned, key=lambda o: len(o[0]), reverse=True):
        if not phrase:
            continue
        if is_label:
            # The name they gave it. Unambiguous wherever it appears.
            low = low.replace(phrase, " ")
        else:
            # A KIND of garment, which is only a reference to theirs when the
            # sentence points at it: "your white undershirt" is the one they are
            # wearing, "add a wool shirt" is a recommendation for one they are not.
            # Removing the kind unconditionally let every "a wool shirt" through on
            # the strength of an owned oxford.
            low = re.sub(rf"\b(your|the|that|this)\s+(?:[\w-]+\s+){{0,2}}{re.escape(phrase)}\b",
                         " ", low)
    # Substring, not whole token: the taxonomy has "coat", the model writes
    # "overcoat", and a token-exact test waved that straight through. Every word
    # tested is four characters or more, which keeps it clear of the accidents a
    # short one invites — "top" inside "laptop", "tie" inside "tights".
    return any(w in low for w in _GARMENT_WORDS if len(w) >= 4)


def _assemble_text(out: dict, banned: list[dict], prefs: Prefs,
                   picks: dict, by_item: dict) -> str:
    """The bullets and the tip, held to the same rules as the picks.

    Prose is what the user actually reads, in the app and in the notification, so
    every constraint enforced on `picks` has to reach it too — otherwise the outfit
    is right and the advice is wrong.
    """
    bullets = [str(b).strip() for b in out.get("bullets") or [] if str(b).strip()]
    bullets = _drop_banned_bullets(bullets, banned)
    # Every way the prose might refer to a garment they are actually wearing: the
    # label they gave it, and the kind of thing it is. A user labels an item
    # "Airism" and the model writes "your white undershirt" — strike out only the
    # label and the line reads as a recommendation for something unowned.
    # (phrase, is_label). A LABEL is the name they gave the garment and means it
    # wherever it appears; a KIND is a common noun and only means theirs when the
    # sentence points at it — see _names_something_unowned.
    owned: list[tuple[str, bool]] = []
    for iid in picks.values():
        if not iid:
            continue
        item = by_item.get(iid) or {}
        label = str(item.get("label") or "").lower().strip()
        if label:
            owned.append((label, True))
        kind = str(item.get("type") or "").lower()
        for word in re.split(r"[^a-z]+", TYPE_LABEL.get(kind, kind).lower()):
            if len(word) > 3:
                owned.append((word, False))
    if prefs.closet_only:
        kept = [b for b in bullets if not _names_something_unowned(b, owned)]
        if len(kept) != len(bullets):
            kept.append("Left some slots empty — nothing you own suits them today.")
        bullets = kept
    if not bullets:
        return ""
    text = "\n".join(f"• {b.lstrip('•- ')}" for b in bullets)
    # The tip is prose like the bullets and just as visible — "bring the white tee"
    # undoes a ban as thoroughly as a bullet would. Dropped rather than rewritten: a
    # tip is one sentence, and there is nothing left of it once the garment is out.
    tip = str(out.get("tip") or "").strip()
    if tip and (_names_banned(tip, banned)
                or (prefs.closet_only and _names_something_unowned(tip, owned))):
        tip = ""
    return f"{text}\n\n💡 {tip}" if tip else text


def _has_suitable_alternative(slot: str, picks: dict, by_item: dict, by_roles: dict,
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
    for iid, item in by_item.items():
        if iid in picks.values():
            continue                              # already worn somewhere else
        if slot not in (by_roles.get(iid) or ()):
            continue
        if slot == "outer" and (item.get("warmth") or 3) < _min_outer_warmth(plan_temp):
            continue
        trial = {**picks, slot: iid}
        if rules.violations(user_rules, trial, by_item):
            continue
        return True
    return False


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
