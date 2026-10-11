"""
gaps.py — which empty slots are a hole in the WARDROBE, for the shopping list.

Judged on the FINAL picks against what they own, never on the model's word alone:
a gap is kept for ninety days and ends as a purchase suggestion, so a slot the model
called empty while a legal garment sat unused would recommend buying something they
already have. The phone reads `missing` (index.html recordGaps), and COLD_GAP
("warmth") when nothing they own is warm enough for the morning.
"""
import layers
import picks as pk
import rules
from check import TORSO, Day
from vocab import CATEGORIES

COLD_GAP = "warmth"     # not a slot: nothing owned is warm enough


def missing(picks: dict, day: Day, claimed: object, emptied: set) -> list[str]:
    """Empty slots the wardrobe cannot fill: the ones the model said it could not
    fill or the fallback had to empty, plus a missing top, trousers or shoes — each
    only if nothing they own, unused and legal, could have filled it."""
    onepiece = day.wd.by_group.get(picks.get("base")) == "onepiece"
    named = {c for c in (claimed if isinstance(claimed, list) else []) if c in CATEGORIES}
    essential = {"bottoms", "footwear"} | ({"base"} if not any(picks.get(c) for c in TORSO) else set())
    candidates = {c for c in named | set(emptied) | essential
                  if not picks.get(c) and not (c == "bottoms" and onepiece)}
    # A pairing rule ("no undershirt with the white tee") empties a slot without the
    # wardrobe lacking anything: tomorrow the undershirt goes under another shirt.
    # Only an outright ban, or owning nothing that fits, makes it a gap.
    outright = [r for r in day.rules if not rules.is_combination(r)]

    def owned(slot: str) -> bool:
        return pk._has_suitable_alternative(slot, {**picks, slot: None}, day.wd, day.plan, outright)
    gaps = sorted((c for c in candidates if not owned(c)), key=CATEGORIES.index)
    if layers.too_cold_for_outfit(picks, day.wd, day.plan, day.rules, day.peak):
        gaps.append(COLD_GAP)
    return gaps
