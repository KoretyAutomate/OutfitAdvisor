"""prose.py — holding the WORDS to the same rules as the picks.

Split out of picks.py on 2026-08-29, when it crossed the 600-line ceiling. The
division is the one the module already had in its own docstring: everything else in
picks.py judges which garment may sit in which slot, and this judges the sentences
that describe them.

They are held to the same standard for the same reason. Prose is what the user
actually reads, in the app and in the notification, so a ban kept in the picks and
broken in the bullets is a ban the user watches being broken.
"""

import re

from vocab import TYPE_LABEL

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


def _assemble_text(out: dict, banned: list[dict], closet_only: bool,
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
    if closet_only:
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
                or (closet_only and _names_something_unowned(tip, owned))):
        tip = ""
    return f"{text}\n\n💡 {tip}" if tip else text
