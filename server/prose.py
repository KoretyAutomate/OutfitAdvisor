"""prose.py — holding the WORDS to the same rules as the picks.

Since the 2026-10-11 refactor: only the closet-complete test — does a line
recommend a garment they do not own (advisor._finish). The rest went with the
repairs that changed garments behind the model's words.

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


