"""
vocab.py — the taxonomy every other module agrees on.

Extracted 2026-08-14 when llm.py was split: these names are needed by the module
that CLASSIFIES a garment (llm.classify_image) and by the one that DRESSES the
user from the wardrobe (closet.py). Leaving them in either would have forced a
circular import, and duplicating them is how two halves of a system quietly stop
agreeing on what a "base" layer is.

Nothing here imports anything of ours, deliberately — it is the bottom of the
dependency graph.
"""

# The LAYERING SLOTS an outfit has. Also the vocabulary for an item's `roles`.
CATEGORIES = ("inner", "base", "mid", "outer", "bottoms", "footwear", "accessories")
STYLES = ("casual", "smart", "active")

# What a garment IS, independent of the layer it happens to play today (user
# request 2026-08-10). Deliberately separate from CATEGORIES: an oxford shirt is a
# Top whether it is the outer layer in July or a base under a coat in November, so
# grouping the wardrobe by layering role would fight the seasonal behaviour below.
GROUPS = ("underwear", "tops", "knitwear", "outerwear", "bottoms", "footwear", "accessories")

# Back-compat for closets saved before `group` existed: derive it from the item's
# primary category so old items still land in a sensible folder.
GROUP_FROM_CATEGORY = {
    "inner": "underwear", "base": "tops", "mid": "knitwear", "outer": "outerwear",
    "bottoms": "bottoms", "footwear": "footwear", "accessories": "accessories",
}


def normalize_roles(roles: list[str] | None, category: str) -> list[str]:
    """The layering slots an item may fill, cleaned and made safe.

    Empty/absent → just its own category, which is exactly the pre-2026-08-10
    behaviour, so an old closet keeps working unchanged.

    INNER IS A CLOSED ROLE. Underwear is never a visible layer, and a visible
    garment is never underwear — that was the user's "wear your tee under your
    tee" complaint. So an item that can be `inner` can ONLY be `inner`; everything
    else may interchange freely as the weather dictates.
    """
    clean = [r for r in (roles or []) if r in CATEGORIES]
    if not clean:
        clean = [category] if category in CATEGORIES else []
    if "inner" in clean:
        return ["inner"]
    # Preserve CATEGORIES order so the value is stable regardless of input order.
    return [c for c in CATEGORIES if c in clean]
