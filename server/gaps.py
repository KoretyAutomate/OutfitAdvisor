"""
gaps.py — which empty slots are a hole in the WARDROBE, for the shopping list.

Judged on the FINAL picks against what they own, never on the model's word alone:
a gap is kept for ninety days and ends as a purchase suggestion, so a slot the model
called empty while a legal garment sat unused would recommend buying something they
already have. The phone reads `missing` (index.html recordGaps), and COLD_GAP
("warmth") when nothing they own is warm enough for the morning.
"""
import accessories
import layers
import scale
from check import TORSO, Day
from vocab import ACCESSORY_SLOTS, CATEGORIES

COLD_GAP = "warmth"     # not a slot: nothing owned is warm enough


def missing(picks: dict, day: Day, claimed: object) -> list[str]:
    """Empty slots the wardrobe cannot fill: the ones the model said it could not
    fill, plus a missing top, trousers or shoes — each only if nothing they own,
    unused and legal, could have filled it."""
    onepiece = day.wd.by_group.get(picks.get("base")) == "onepiece"
    # An accessory slot only on a day that calls for one: a closet with no umbrella
    # is no shopping gap on a dry day (Codex plan review, 2026-11-24).
    named = {c for c in (claimed if isinstance(claimed, list) else []) if c in CATEGORIES
             and (c not in ACCESSORY_SLOTS or accessories.wanted(c, day, picks))}
    essential = {"bottoms", "footwear"} | ({"base"} if not any(picks.get(c) for c in TORSO) else set())
    candidates = {c for c in named | essential
                  if not picks.get(c) and not (c == "bottoms" and onepiece)}
    # A pairing rule ("no undershirt with the white tee") empties a slot without the
    # wardrobe lacking anything: tomorrow the undershirt goes under another shirt.
    # Only an outright ban, or owning nothing that fits, makes it a gap.
    gaps = sorted((c for c in candidates if not day.owns_for(c, picks)), key=CATEGORIES.index)
    if layers.too_cold_for_outfit(picks, day.wd, day.plan, day.rules, day.peak):
        gaps.append(COLD_GAP)
    # Summer legs worn on a cold morning because nothing warmer is owned: the slot is
    # the gap (user, 2026-11-18). Owning warmer ones is check.py's cold-legs instead.
    for slot in ("bottoms", "footwear"):
        it = day.wd.by_item.get(picks.get(slot)) or {}
        if it and scale.too_cold_for_legs(it, day.plan) and slot not in gaps and not layers.underdressed(
                it, slot, day):
            gaps.append(slot)
    return gaps
