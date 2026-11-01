"""
relaxnotes.py — what the served outfit gives up, in words: one line per rule of
funnel.RELAX it relaxed, and the lines for a cold outfit. Split from funnel.py at the
600-line ceiling (2026-11-01); the funnel decides, this only says.
"""
NOTES = {
    "colour": "colours a little busier than usual — nothing quieter fits today",
    "belt": "the belt doesn't match the shoes — nothing matching is free today",
    "texture": "the knit and the top are not the ideal pairing — nothing better is free today",
    "wet": "nothing water-resistant to wear on your feet today — expect damp shoes in the rain",
    "register": "the trousers, shoes or coat don't match the top — nothing that does is free today",
    # Either way off — too relaxed or too dressy (pre-push gate, 2026-10-20).
    "band1": "a step off the day's usual dress level — nothing at it is free today",
    "band2": "well off the day's usual dress level — little at it is free today",
    "band3": "well off the day's usual dress level — little at it is free today",
}
# Served only when no combination is warm (search's `chilly`), and always said.
# A fact, never an instruction: "take a layer" would name what a closet-only wardrobe
# may not have (pre-push gate, 2026-10-24).
COLD = "nothing warm enough for the coldest hour goes with the rest today — expect to feel cold early on"
COLD_UNSURE = ("time ran out before a warm enough outfit was found — this one is light for the coldest "
               "hour")
TRIED_ALL = "every combination of what you can wear today was tried, and none keeps every rule"


def notes(relaxed: tuple, complete: bool = True) -> list[str]:
    """What the served outfit gives up, in words — every rule it breaks, after a line
    saying that no combination keeps them all (user, 2026-10-23: "If there is truly no
    combination ... it needs to mention that in the commentary")."""
    said = [NOTES[r] for r in reversed(relaxed) if r in NOTES]
    if not said:
        return []
    lead = (TRIED_ALL if complete else
            "time ran out before every combination was tried — none of those tried keeps every rule")
    return [lead, *said]
