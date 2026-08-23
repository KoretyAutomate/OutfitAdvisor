"""
vocab.py — the taxonomy every other module agrees on.

Extracted 2026-08-14 when llm.py was split: these names are needed by the module
that CLASSIFIES a garment (llm.classify_image) and by the one that DRESSES the
user from the wardrobe (closet.py). Leaving them in either would have forced a
circular import, and duplicating them is how two halves of a system quietly stop
agreeing on what a "base" layer is.

Nothing here imports anything of ours, deliberately — it is the bottom of the
dependency graph.

THREE AXES, and there are three because collapsing any two of them is what
produced every bug this file has been amended for:

    group   which folder the garment lives in      what it IS, coarse
    type    which kind of garment it is            what it IS, fine
    roles   which layers it can be worn as         how it is WORN

`inner` is a ROLE, never a garment. An undershirt is `underwear/undershirt`
playing the `inner` role; it is not a Top. Consolidated 2026-08-20 from two
branches that had each built half of this and never met.
"""

# The LAYERING SLOTS an outfit has. Also the vocabulary for an item's `roles`.
#
# Deliberately NOT given an eighth slot for one-piece garments. A dress is handled
# by giving it the `base` role and clearing `bottoms` (see closet._onepiece_conflicts)
# because widening this tuple ripples through the picks schema, engine.py, the outfit
# card and the Kotlin push path — and the failure mode of getting that wrong is the
# morning notification not arriving.
CATEGORIES = ("inner", "base", "mid", "outer", "bottoms", "footwear", "accessories")
STYLES = ("casual", "smart", "active")

# What a garment IS, independent of the layer it happens to play today (user
# request 2026-08-10). Deliberately separate from CATEGORIES: an oxford shirt is a
# Top whether it is the outer layer in July or a base under a coat in November, so
# grouping the wardrobe by layering role would fight the seasonal behaviour below.
#
# 2026-08-20: `knitwear` dissolved into `tops`, `onepiece` added.
#
# Knitwear was a boundary the classifier had to re-litigate on every photo — is a
# merino polo knitwear or a top, is a quilted vest knitwear or outerwear — and that
# re-litigation is what made the folders inconsistent, which was the user's
# complaint. Sweater/cardigan/hoodie/fleece survive as TYPES of `tops`, which is the
# level where the distinction was always meaningful: the folder moved down one level
# rather than disappearing.
GROUPS = ("underwear", "tops", "outerwear", "bottoms", "onepiece", "footwear", "accessories")

# Groups that no longer exist, and what they became. Old phones and old saved
# closets keep sending these; the value is translated, never rejected.
GROUP_ALIASES = {"knitwear": "tops"}

# Back-compat for closets saved before `group` existed: derive it from the item's
# primary category so old items still land in a sensible folder. `mid` maps to
# `tops` now that knitwear is gone — a mid-layer garment is a sweater, and a
# sweater is a Top.
GROUP_FROM_CATEGORY = {
    "inner": "underwear", "base": "tops", "mid": "tops", "outer": "outerwear",
    "bottoms": "bottoms", "footwear": "footwear", "accessories": "accessories",
}

# ── the second level ────────────────────────────────────────────────────────────
#
# "Tops > Polo shirt" (user, 2026-08-14; re-asked 2026-08-20). The subdivision
# follows the World Customs Organization's HARMONIZED SYSTEM — chapters 61/62
# (apparel, knitted / not knitted), 64 (footwear), 65 (headgear) — not somebody's
# taste. The point of an external source is that "is a hoodie knitwear?" has an
# answer someone else has already argued about; TYPE_LABEL below names the heading
# each type is drawn from.
#
# Departures, because a wardrobe is not a customs declaration: HS splits by
# knitted-vs-woven and by the wearer's sex, and it has no jumpsuit heading (that
# one falls to the residual 6114/6211 "other garments", and says so).
#
# Type sits BESIDE the layering role, not above it. A type says what a garment IS;
# a role says what it can be worn AS. Same shirt, always a shirt, base in winter
# and outer in July.
TYPES: dict[str, tuple[str, ...]] = {
    "underwear": ("undershirt", "thermal", "briefs", "bra", "sleepwear"),
    "tops": ("t_shirt", "shirt", "polo", "blouse", "tank",
             "sweater", "cardigan", "hoodie", "fleece", "waistcoat"),
    "outerwear": ("jacket", "blazer", "coat", "puffer", "rainwear"),
    "bottoms": ("trousers", "jeans", "shorts", "skirt", "leggings"),
    "onepiece": ("dress", "jumpsuit", "overalls"),
    "footwear": ("sneakers", "dress_shoes", "boots", "sandals", "loafers", "socks"),
    "accessories": ("scarf", "gloves", "hat", "belt", "tie", "umbrella"),
}

# Human wording, and the HS heading each type is drawn from.
TYPE_LABEL = {
    # underwear — HS 6107/6207 (men's), 6108/6208 (women's), 6212
    "undershirt": "Undershirt / singlet",     # 6109, 6207 singlets and other vests
    "thermal": "Thermal / base layer",        # 6107, 6207 similar articles
    "briefs": "Underpants / briefs",          # 6107, 6108, 6207, 6208
    "bra": "Bra / lingerie",                  # 6212 brassieres, corsets
    "sleepwear": "Pyjamas / nightwear",       # 6107, 6108 nightshirts, pyjamas
    # tops — HS 6105/6205 (men's shirts), 6106/6206 (women's blouses), 6109, 6110
    "t_shirt": "T-shirt",                     # 6109 T-shirts
    "shirt": "Shirt",                         # 6105, 6205 shirts
    "polo": "Polo shirt",                     # 6105, 6205 (collared knit shirt)
    "blouse": "Blouse",                       # 6106, 6206 blouses, shirt-blouses
    "tank": "Tank top / vest",                # 6109 singlets and other vests
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
    "leggings": "Leggings / tights",          # 6115 tights
    # onepiece — added 2026-08-20; `dress` was previously filed under bottoms,
    # which the packing prompt read as a pair of trousers
    "dress": "Dress",                         # 6104, 6204 dresses
    "jumpsuit": "Jumpsuit",                   # 6114, 6211 other garments (residual)
    "overalls": "Dungarees / overalls",       # 6103, 6203 bib and brace overalls
    # footwear — HS chapter 64; socks are 6115 but live here, see NON_SLOT_TYPES
    "sneakers": "Sneakers / trainers",        # 6404 footwear with textile uppers
    "dress_shoes": "Dress shoes",             # 6403 footwear with leather uppers
    "boots": "Boots",                         # 6401, 6402, 6403 boots
    "sandals": "Sandals",                     # 6402, 6403 sandals
    "loafers": "Loafers / flats",             # 6403 footwear with leather uppers
    "socks": "Socks / hosiery",               # 6115 panty hose, stockings, socks
    # accessories — HS 6116, 6117/6214/6215, 6217, 6505, 6601
    "scarf": "Scarf / shawl",                 # 6214 shawls, scarves, mufflers
    "gloves": "Gloves",                       # 6116, 6216 gloves, mittens
    "hat": "Hat / cap",                       # 6505 hats and other headgear
    "belt": "Belt",                           # 6217 other made-up accessories
    "tie": "Tie",                             # 6215 ties, bow ties, cravats
    "umbrella": "Umbrella",                   # 6601 umbrellas
}

# Flat lookup: type -> the ONE group it belongs to. A type never appears twice.
GROUP_FROM_TYPE = {t: g for g, ts in TYPES.items() for t in ts}

# Types whose group MOVED, and where to. Here the stated group is what was wrong,
# not the type, so the usual "the group wins" tie-break is suspended: an item
# saved as bottoms/dress is a dress that predates the `onepiece` group, not a pair
# of trousers somebody mislabelled.
#
# Suspending it is not a nicety. Without the socks entry, a legacy underwear/socks
# item has its type DROPPED (socks is not a type of underwear any more), lands back
# in `underwear` with type=None, and so slips past the NON_SLOT_TYPES filter as a
# perfectly legal undershirt — the exact defect this round exists to fix, surviving
# in the migration path. Caught by test_endpoints_taxonomy, not by any unit test.
LEGACY_TYPE_GROUP = {
    ("bottoms", "dress"): "onepiece",
    ("underwear", "socks"): "footwear",
}

# Garments that are real wardrobe items but fill no OUTFIT slot.
#
# Found 2026-08-20 while merging: `underwear` maps to the `inner` role, and the
# `inner` slot means the undershirt worn under the visible top — so with socks,
# briefs, a bra and pyjamas all sitting in that group, nothing stopped the advisor
# putting wool socks in the undershirt slot. Socks moved to `footwear` (where a
# person looks for them) and these four are withheld from the OUTFIT prompt while
# staying in the closet and in the PACKING prompt: the morning advice does not need
# to name your underpants, a packing list very much does.
#
# Side effect, and a correct one: a closet holding only briefs now reports `inner`
# as an uncoverable slot, because the user genuinely owns no undershirt.
NON_SLOT_TYPES = ("briefs", "bra", "sleepwear", "socks")

# ── how the axes constrain each other ───────────────────────────────────────────
#
# The group is the ANCHOR: what a garment IS, which a photo shows plainly. The
# layering role is derived under it and can never contradict it. `inner` exists in
# exactly one group, which is what makes "underwear is never a visible layer" a
# property of the taxonomy instead of a rule three modules each have to remember.
#
# `tops` allows base/mid/outer because that IS the seasonal behaviour the
# 2026-08-10 round added — an oxford shirt is outermost in July and a base under a
# coat in November. What it never allows is `inner`.
#
# `onepiece` allows `base` only. A dress is the visible torso garment; it cannot
# also be `bottoms`, because _dedupe_picks forbids one item in two slots. Picking
# one makes the bottoms slot unnecessary rather than empty — enforced in
# closet._onepiece_conflicts, not hoped for in the prompt.
GROUP_CATEGORIES = {
    "underwear": ("inner",),
    "tops": ("base", "mid", "outer"),
    "outerwear": ("mid", "outer"),
    "bottoms": ("bottoms",),
    "onepiece": ("base",),
    "footwear": ("footwear",),
    "accessories": ("accessories",),
}

# The slot a garment falls back to when its stated category is illegal for its
# group. Never a guess between equals: a top defaults to the visible shirt, a
# coat to the outer layer.
GROUP_DEFAULT_CATEGORY = {
    "underwear": "inner", "tops": "base", "outerwear": "outer",
    "bottoms": "bottoms", "onepiece": "base", "footwear": "footwear",
    "accessories": "accessories",
}

# What a KNOWN type implies, for the fields the classifier is least reliable on.
#
#   roles      NARROWS the group's allowed set (intersection, see reconcile).
#              A `coat` is ["outer"] where `outerwear` alone would allow mid too.
#              This is the one field the type overrides, because it is a statement
#              about what the garment IS.
#   warmth     FILLED ONLY when the classifier returned nothing usable. Never
#              clamped over a stated value: a light trench is a `coat` at warmth 3,
#              and rounding it up to 4 would walk it straight past the
#              _OUTER_MIN_WARMTH floor at 4C — the exact 2026-08-10 failure,
#              reintroduced by the guard meant to prevent it.
#   formality  Filled the same way, and it is the field that finally makes the type
#              STEER a pick. The 08-14 branch could not show that it did: given a
#              polo and a tee identical in every other attribute on a smart day, the
#              model chose the tee. It would — the two prompt lines were identical
#              apart from a word in the label. A `t_shirt` that defaults to casual
#              and a `polo` that defaults to casual/smart differ in an attribute the
#              prompt already prints.
#
# Consulted in /classify ONLY, never on the /advice path, so nothing re-guesses an
# item the user has already corrected in the edit sheet.
TYPE_DEFAULTS: dict[str, dict] = {
    # underwear
    "undershirt": {"roles": ("inner",), "warmth": 2, "formality": STYLES},
    "thermal": {"roles": ("inner",), "warmth": 4, "formality": STYLES},
    "briefs": {"roles": ("inner",), "warmth": 1, "formality": STYLES},
    "bra": {"roles": ("inner",), "warmth": 1, "formality": STYLES},
    "sleepwear": {"roles": ("inner",), "warmth": 2, "formality": ("casual",)},
    # tops
    "t_shirt": {"roles": ("base",), "warmth": 1, "formality": ("casual", "active")},
    "shirt": {"roles": ("base", "mid", "outer"), "warmth": 2, "formality": ("casual", "smart")},
    "polo": {"roles": ("base", "mid", "outer"), "warmth": 2, "formality": STYLES},
    "blouse": {"roles": ("base", "mid", "outer"), "warmth": 2, "formality": ("casual", "smart")},
    "tank": {"roles": ("base",), "warmth": 1, "formality": ("casual", "active")},
    "sweater": {"roles": ("base", "mid", "outer"), "warmth": 4, "formality": ("casual", "smart")},
    "cardigan": {"roles": ("mid", "outer"), "warmth": 3, "formality": ("casual", "smart")},
    "hoodie": {"roles": ("mid", "outer"), "warmth": 3, "formality": ("casual", "active")},
    "fleece": {"roles": ("mid", "outer"), "warmth": 3, "formality": ("casual", "active")},
    "waistcoat": {"roles": ("mid",), "warmth": 2, "formality": ("casual", "smart")},
    # outerwear
    "jacket": {"roles": ("outer",), "warmth": 3, "formality": ("casual", "active")},
    "blazer": {"roles": ("mid", "outer"), "warmth": 2, "formality": ("smart",)},
    "coat": {"roles": ("outer",), "warmth": 4, "formality": ("casual", "smart")},
    "puffer": {"roles": ("outer",), "warmth": 5, "formality": ("casual", "active")},
    "rainwear": {"roles": ("outer",), "warmth": 2, "formality": ("casual", "active")},
    # bottoms
    "trousers": {"roles": ("bottoms",), "warmth": 3, "formality": ("casual", "smart")},
    "jeans": {"roles": ("bottoms",), "warmth": 3, "formality": ("casual",)},
    "shorts": {"roles": ("bottoms",), "warmth": 1, "formality": ("casual", "active")},
    "skirt": {"roles": ("bottoms",), "warmth": 2, "formality": ("casual", "smart")},
    "leggings": {"roles": ("bottoms",), "warmth": 2, "formality": ("casual", "active")},
    # onepiece
    "dress": {"roles": ("base",), "warmth": 2, "formality": ("casual", "smart")},
    "jumpsuit": {"roles": ("base",), "warmth": 2, "formality": ("casual", "smart")},
    "overalls": {"roles": ("base",), "warmth": 3, "formality": ("casual",)},
    # footwear
    "sneakers": {"roles": ("footwear",), "warmth": 2, "formality": ("casual", "active")},
    "dress_shoes": {"roles": ("footwear",), "warmth": 2, "formality": ("smart",)},
    "boots": {"roles": ("footwear",), "warmth": 4, "formality": ("casual", "smart")},
    "sandals": {"roles": ("footwear",), "warmth": 1, "formality": ("casual",)},
    "loafers": {"roles": ("footwear",), "warmth": 2, "formality": ("casual", "smart")},
    "socks": {"roles": ("footwear",), "warmth": 2, "formality": STYLES},
    # accessories
    "scarf": {"roles": ("accessories",), "warmth": 4, "formality": ("casual", "smart")},
    "gloves": {"roles": ("accessories",), "warmth": 4, "formality": STYLES},
    "hat": {"roles": ("accessories",), "warmth": 3, "formality": STYLES},
    "belt": {"roles": ("accessories",), "warmth": 1, "formality": ("casual", "smart")},
    "tie": {"roles": ("accessories",), "warmth": 1, "formality": ("smart",)},
    "umbrella": {"roles": ("accessories",), "warmth": 1, "formality": STYLES},
}


def canonical_group(group: str | None) -> str | None:
    """A group name as it is spelled TODAY, or None if it is not one of ours.

    Translating rather than rejecting is what lets a phone running an older build
    keep talking to this server: it still sends `knitwear`, and a 422 there would
    fail the whole /advice request, not just the one item.
    """
    if not group:
        return None
    g = GROUP_ALIASES.get(group, group)
    return g if g in GROUPS else None


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


def reconcile(
    category: str, group: str | None, roles: list[str] | None, type_: str | None = None
) -> tuple[str, str, str | None, list[str]]:
    """Force one garment's (category, group, type, roles) to agree, group first.

    Returns the corrected quadruple. Total — every input produces a legal item, so
    a bad guess from the classifier is repaired rather than rejected: the user
    just took that photo, and a 422 loses it.

    THE GROUP WINS on a conflict, deliberately. Both answers come from the same
    model, so the tie-break has to be the one it is more reliably right about:
    "is this a t-shirt or an undershirt" is visible in the photo, while "is this
    worn as underwear today" is a judgement about how someone dresses. Demoting
    a contradictory `inner` to the group's real slot is also the SAFE direction —
    the failure it prevents is recommending a visible tee as an undershirt, and
    the worst case in the other direction is an undershirt filed as a base, which
    the user can see and fix in the edit sheet.

    The TYPE joins that relation as of 2026-08-20 (this is the merge the 08-14 and
    08-18 branches never had). It is the narrowest true statement about a garment,
    so where it is known it NARROWS the roles the group allows.
    """
    # 1. Spell the group the way we spell it today, before anything reads it.
    canon = canonical_group(group)
    # 2. A type whose group MOVED carries the correction with it — see
    #    LEGACY_TYPE_GROUP. Done before the type is validated against the group,
    #    which is what stops `dress` being dropped on the way out of `bottoms`.
    raw_type = (
        str(type_).strip().lower().replace("-", "_").replace(" ", "_") if type_ else None
    )
    if canon and raw_type and (canon, raw_type) in LEGACY_TYPE_GROUP:
        canon = LEGACY_TYPE_GROUP[(canon, raw_type)]
    # 3. No usable group? The type names one exactly, and is a better source than
    #    the category — which is a guess about how the thing is worn.
    if canon is None:
        canon = GROUP_FROM_TYPE.get(raw_type or "") or GROUP_FROM_CATEGORY.get(category, "tops")
    grp: str = canon
    kind = normalize_type(raw_type, grp)

    # 4. The slots this garment may occupy: its group's set, narrowed by its type.
    #    Falling back to the group alone when the intersection is empty keeps the
    #    function total — a type and a group can only disagree here if one of the
    #    two tables is wrong, and an unpickable item is a worse answer than a
    #    slightly loose one.
    allowed: tuple[str, ...] = GROUP_CATEGORIES[grp]
    if kind:
        narrowed = tuple(c for c in allowed if c in TYPE_DEFAULTS[kind]["roles"])
        allowed = narrowed or allowed

    if category not in allowed:
        default = GROUP_DEFAULT_CATEGORY[grp]
        category = default if default in allowed else allowed[0]

    # 5. DEMOTE the contradictory `inner` before normalize_roles() sees it, exactly
    #    as the category was demoted above. `inner` is a CLOSED role there, so an
    #    `inner` left in the list would collapse the whole list to ["inner"] and the
    #    filter below would then delete it — costing a top that the model called
    #    inner/mid/outer its mid and outer roles, i.e. the seasonal freedom the
    #    2026-08-10 round exists for. What the model means by `inner` on a visible
    #    garment is "the layer I wear closest to the skin", which for that group is
    #    its default slot; saying so keeps the answer instead of discarding it.
    stated = [r for r in (roles or []) if r in CATEGORIES]
    if "inner" not in allowed:
        stated = [category if r == "inner" else r for r in stated]
    clean = [r for r in normalize_roles(stated, category) if r in allowed]
    # Roles that all contradicted the group leave nothing behind. The item's own
    # (now legal) category is the honest answer, not an empty role set that would
    # make the item unpickable for every slot.
    return category, grp, kind, clean or [category]


def apply_type_defaults(kind: str | None, warmth: int | None, formality: list[str] | None):
    """Fill warmth/formality from the type when the classifier gave nothing usable.

    FILL, NEVER CLAMP — see the note on TYPE_DEFAULTS. A stated value is the
    model's or the user's answer about this particular garment, and the table only
    knows about the average one.
    """
    d = TYPE_DEFAULTS.get(kind or "")
    clean_form = [f for f in (formality or []) if f in STYLES]
    if d is None:
        return (warmth if warmth in (1, 2, 3, 4, 5) else 3), (clean_form or ["casual"])
    if warmth not in (1, 2, 3, 4, 5):
        warmth = d["warmth"]
    return warmth, (clean_form or list(d["formality"]))
