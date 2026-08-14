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

# ── Second level: what KIND of garment, within its group (user, 2026-08-14) ──
#
# "Tops > T-shirt, Shirt, Polo" — GROUPS alone was too coarse to tell a polo from
# a tee, which is a difference the user can see and the model cannot express.
#
# SOURCE. This subdivision is not invented here. It follows the World Customs
# Organization's HARMONIZED SYSTEM, the internationally agreed goods nomenclature
# every customs authority classifies clothing with — chapter 61 (articles of
# apparel, knitted or crocheted), chapter 62 (the same, not knitted), chapter 64
# (footwear) and chapter 65 (headgear). The heading each type comes from is named
# beside it, so the taxonomy is checkable against the standard instead of taste:
#   https://www.wcoomd.org/en/topics/nomenclature/instrument-and-tools/hs-nomenclature-2022-edition.aspx
#
# TWO DELIBERATE DEPARTURES from the standard, both because a wardrobe is not a
# customs declaration:
#   - HS splits almost every garment by knitted vs not knitted (6105 shirt vs 6205
#     shirt) and by the wearer's sex (6103 vs 6104). Neither changes what you wear
#     on a cold morning, so the two chapters are folded together here.
#   - HS has no notion of a LAYERING role. That stays with `CATEGORIES`/`roles`,
#     which is the axis the recommender actually reasons over. A type says what a
#     garment IS; a role says what it can be worn AS. Both are needed: an oxford
#     shirt is always a shirt, and it is a base layer in winter and the outer layer
#     in July.
TYPES: dict[str, tuple[str, ...]] = {
    "underwear": ("undershirt", "thermal", "briefs", "bra", "socks", "sleepwear"),
    "tops": ("t_shirt", "shirt", "polo", "blouse", "tank"),
    "knitwear": ("sweater", "cardigan", "hoodie", "fleece", "waistcoat"),
    "outerwear": ("jacket", "blazer", "coat", "puffer", "rainwear"),
    "bottoms": ("trousers", "jeans", "shorts", "skirt", "dress", "leggings"),
    "footwear": ("sneakers", "dress_shoes", "boots", "sandals", "loafers"),
    "accessories": ("scarf", "gloves", "hat", "belt", "tie", "umbrella"),
}

# Human wording, and the HS heading each type is drawn from.
TYPE_LABEL = {
    # underwear — HS 6107/6207 (men's), 6108/6208 (women's), 6212, 6115
    "undershirt": "Undershirt / singlet",     # 6109, 6207 singlets and other vests
    "thermal": "Thermal / base layer",        # 6107, 6207 similar articles
    "briefs": "Underpants / briefs",          # 6107, 6108, 6207, 6208
    "bra": "Bra / lingerie",                  # 6212 brassieres, corsets
    "socks": "Socks / hosiery",               # 6115 panty hose, stockings, socks
    "sleepwear": "Pyjamas / nightwear",       # 6107, 6108 nightshirts, pyjamas
    # tops — HS 6105/6205 (men's shirts), 6106/6206 (women's blouses), 6109
    "t_shirt": "T-shirt",                     # 6109 T-shirts
    "shirt": "Shirt",                         # 6105, 6205 shirts
    "polo": "Polo shirt",                     # 6105, 6205 (collared knit shirt)
    "blouse": "Blouse",                       # 6106, 6206 blouses, shirt-blouses
    "tank": "Tank top / vest",                # 6109 singlets and other vests
    # knitwear — HS 6110
    "sweater": "Sweater / pullover",          # 6110 jerseys, pullovers
    "cardigan": "Cardigan",                   # 6110 cardigans
    "hoodie": "Hoodie / sweatshirt",          # 6110 similar articles
    "fleece": "Fleece",                       # 6110 similar articles
    "waistcoat": "Waistcoat",                 # 6110 waistcoats
    # outerwear — HS 6101/6201, 6102/6202 (coats, anoraks), 6103/6203 (jackets),
    # 6113/6210 (garments of impregnated or coated fabric)
    "jacket": "Jacket / windbreaker",         # 6101, 6201 anoraks, wind-jackets
    "blazer": "Blazer / suit jacket",         # 6103, 6203 jackets and blazers
    "coat": "Coat",                           # 6101, 6102, 6201, 6202 overcoats
    "puffer": "Padded / down jacket",         # 6101, 6201 similar articles
    "rainwear": "Raincoat / shell",           # 6113, 6210 coated-fabric garments
    # bottoms — HS 6103/6203 (men's), 6104/6204 (women's), 6115
    "trousers": "Trousers / chinos",          # 6103, 6104, 6203, 6204 trousers
    "jeans": "Jeans",                         # 6103, 6203 trousers (denim)
    "shorts": "Shorts",                       # 6103, 6104, 6203, 6204 shorts
    "skirt": "Skirt",                         # 6104, 6204 skirts, divided skirts
    "dress": "Dress",                         # 6104, 6204 dresses
    "leggings": "Leggings / tights",          # 6115 tights
    # footwear — HS chapter 64
    "sneakers": "Sneakers / trainers",        # 6404 footwear with textile uppers
    "dress_shoes": "Dress shoes",             # 6403 footwear with leather uppers
    "boots": "Boots",                         # 6401, 6402, 6403 boots
    "sandals": "Sandals",                     # 6402, 6403 sandals
    "loafers": "Loafers / flats",             # 6403 footwear with leather uppers
    # accessories — HS 6116, 6117/6214/6215, 6505, 6601
    "scarf": "Scarf / shawl",                 # 6214 shawls, scarves, mufflers
    "gloves": "Gloves",                       # 6116, 6216 gloves, mittens
    "hat": "Hat / cap",                       # 6505 hats and other headgear
    "belt": "Belt",                           # 6217 other made-up accessories
    "tie": "Tie",                             # 6215 ties, bow ties, cravats
    "umbrella": "Umbrella",                   # 6601 umbrellas
}

# Flat lookup: type -> the ONE group it belongs to. A type never appears twice.
GROUP_FROM_TYPE = {t: g for g, ts in TYPES.items() for t in ts}


def normalize_type(type_: str | None, group: str | None) -> str | None:
    """The garment's type, or None when it has none we recognise.

    Absent is legitimate and always will be: closets saved before this existed
    have no type, and an item nobody has bothered to detail is still a perfectly
    good wardrobe entry. So an unknown or group-mismatched value is DROPPED rather
    than rejected — the same posture as normalize_roles(), and the reason /classify
    returning a plausible-but-wrong type can never 422 a photo the user just took.
    """
    if not type_:
        return None
    t = str(type_).strip().lower().replace("-", "_").replace(" ", "_")
    if group and t in TYPES.get(group, ()):
        return t
    # A type that belongs to a DIFFERENT group is a disagreement between the two
    # levels, not a value to keep: the group is what files the item in a folder.
    return None


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
