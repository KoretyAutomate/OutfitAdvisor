"""The closet taxonomy — group, type and role, and the rules tying them together.

Consolidated 2026-08-20 from two branches that each built half of this and never
met: `TYPES` (2026-08-14) and `reconcile()` (2026-08-18). Every case below is a
property somebody has already been burned by, not a hypothetical:

  - a visible tee offered as an undershirt        user, 2026-08-18
  - wool socks legal for the undershirt slot      found while merging, 2026-08-20
  - trousers picked under a dress                 one item cannot fill two slots
  - a photo the user just took, rejected          reconcile() must be TOTAL
  - a type silently vanishing on the way out      the two levels must agree

The parity table in `app/tests/closet_types.test.js` covers the phone-side twins
of these functions; if one side is edited alone the two suites disagree, which is
the point.
"""

import pytest

import vocab


# ── the shape of the vocabulary ────────────────────────────────────────────────

def test_every_type_belongs_to_exactly_one_group():
    """GROUP_FROM_TYPE is only meaningful if a type is never in two groups."""
    seen: dict[str, str] = {}
    for group, types in vocab.TYPES.items():
        for t in types:
            assert t not in seen, f"{t} is in both {seen.get(t)} and {group}"
            seen[t] = group
    assert seen == vocab.GROUP_FROM_TYPE


def test_every_type_has_a_label_and_defaults():
    """A type with no label prints as a raw slug; one with no defaults cannot
    narrow roles, which is the whole reason the second level exists."""
    for t in vocab.GROUP_FROM_TYPE:
        assert t in vocab.TYPE_LABEL, f"{t} has no human wording"
        assert t in vocab.TYPE_DEFAULTS, f"{t} has no defaults"


def test_type_default_roles_are_reachable_from_the_group():
    """A type whose roles do not intersect its group's would be silently widened
    back to the group in reconcile() — a table bug that looks like working code."""
    for t, group in vocab.GROUP_FROM_TYPE.items():
        allowed = set(vocab.GROUP_CATEGORIES[group])
        assert allowed & set(vocab.TYPE_DEFAULTS[t]["roles"]), t


def test_every_group_is_covered_by_the_relation_tables():
    for g in vocab.GROUPS:
        assert g in vocab.GROUP_CATEGORIES
        assert g in vocab.GROUP_DEFAULT_CATEGORY
        assert g in vocab.TYPES
        assert vocab.GROUP_DEFAULT_CATEGORY[g] in vocab.GROUP_CATEGORIES[g]


def test_inner_exists_in_exactly_one_group():
    """This is what makes "underwear is never a visible layer" a property of the
    taxonomy rather than a rule three modules each have to remember."""
    owners = [g for g, cats in vocab.GROUP_CATEGORIES.items() if "inner" in cats]
    assert owners == ["underwear"]


# ── normalize_type ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,group,want", [
    ("polo", "tops", "polo"),
    ("Polo", "tops", "polo"),
    ("dress-shoes", "footwear", "dress_shoes"),
    ("dress shoes", "footwear", "dress_shoes"),
    ("polo", "outerwear", None),      # right type, wrong group -> dropped
    ("nonsense", "tops", None),
    (None, "tops", None),
    ("", "tops", None),
    ("polo", None, None),
])
def test_normalize_type(raw, group, want):
    assert vocab.normalize_type(raw, group) == want


# ── reconcile: the group is the anchor ─────────────────────────────────────────

def test_a_visible_top_can_never_carry_the_inner_role():
    """The 2026-08-18 complaint, as a test. The classifier answering group=tops and
    category=inner in one breath used to store both verbatim, and closet.py picks by
    ROLE, so that tee was a legal candidate for the undershirt slot."""
    cat, grp, kind, roles = vocab.reconcile("inner", "tops", ["inner", "base"], "t_shirt")
    assert grp == "tops"
    assert cat != "inner"
    assert "inner" not in roles


def test_a_demoted_inner_keeps_the_items_other_roles():
    """Dropping rather than demoting would cost a shirt its mid and outer roles —
    the seasonal freedom the 2026-08-10 round exists for."""
    _, _, _, roles = vocab.reconcile("base", "tops", ["inner", "mid", "outer"], "shirt")
    assert roles == ["base", "mid", "outer"]


def test_underwear_stays_closed():
    cat, grp, _, roles = vocab.reconcile("base", "underwear", ["base", "mid"], "undershirt")
    assert (cat, grp, roles) == ("inner", "underwear", ["inner"])


def test_reconcile_is_total_over_junk():
    """A 422 on a photo the user just took loses the photo. Every input must yield
    a legal item instead."""
    for args in [
        ("nonsense", "nonsense", ["nonsense"], "nonsense"),
        ("base", None, None, None),
        ("footwear", "", [], ""),
    ]:
        cat, grp, kind, roles = vocab.reconcile(*args)
        assert grp in vocab.GROUPS
        assert cat in vocab.CATEGORIES
        assert kind is None or kind in vocab.TYPES[grp]
        assert roles and all(r in vocab.GROUP_CATEGORIES[grp] for r in roles)


def test_the_type_names_the_group_when_the_group_is_missing():
    """A type is an exact statement about what the garment is; a category is a guess
    about how it is worn. The type is the better fallback."""
    _, grp, kind, _ = vocab.reconcile("base", None, None, "puffer")
    assert (grp, kind) == ("outerwear", "puffer")


# ── reconcile: the type narrows the group ──────────────────────────────────────

def test_a_known_type_narrows_the_roles_its_group_allows():
    """`outerwear` alone allows mid and outer. A coat is outer."""
    _, _, _, group_only = vocab.reconcile("outer", "outerwear", ["mid", "outer"], None)
    assert group_only == ["mid", "outer"]
    _, _, _, typed = vocab.reconcile("outer", "outerwear", ["mid", "outer"], "coat")
    assert typed == ["outer"]


def test_a_blazer_keeps_both_layers_it_can_play():
    _, _, _, roles = vocab.reconcile("outer", "outerwear", ["mid", "outer"], "blazer")
    assert roles == ["mid", "outer"]


def test_narrowing_never_leaves_an_item_unpickable():
    """If the two tables ever disagree, a slightly loose item beats one that can
    fill no slot at all — so the intersection falls back to the group."""
    for t, g in vocab.GROUP_FROM_TYPE.items():
        for cat in vocab.CATEGORIES:
            _, _, _, roles = vocab.reconcile(cat, g, [cat], t)
            assert roles, (t, g, cat)


# ── migration: nobody's closet starts over ─────────────────────────────────────

def test_knitwear_becomes_tops_and_keeps_its_type():
    """Knitwear dissolved on 2026-08-20; sweater/cardigan/hoodie/fleece became TYPES
    of Tops. An old phone still sends the old group, and the item must survive it."""
    cat, grp, kind, roles = vocab.reconcile("mid", "knitwear", ["mid", "outer"], "sweater")
    assert (grp, kind) == ("tops", "sweater")
    assert cat == "mid" and roles == ["mid", "outer"]


def test_canonical_group_translates_rather_than_rejects():
    assert vocab.canonical_group("knitwear") == "tops"
    assert vocab.canonical_group("tops") == "tops"
    assert vocab.canonical_group("nonsense") is None
    assert vocab.canonical_group(None) is None


def test_a_dress_saved_under_bottoms_moves_to_onepiece():
    """Here the GROUP is what was wrong, not the type, so "the group wins" is
    suspended for the types that moved — otherwise the dress would simply lose its
    type on the way out of bottoms."""
    cat, grp, kind, roles = vocab.reconcile("bottoms", "bottoms", ["bottoms"], "dress")
    assert (grp, kind) == ("onepiece", "dress")
    assert cat == "base" and roles == ["base"]


def test_legacy_socks_move_to_footwear_and_stay_withholdable():
    """Socks left `underwear` on 2026-08-20. Without the LEGACY_TYPE_GROUP entry the
    type is DROPPED (socks is no longer a type of underwear), the item lands back in
    `underwear` with type=None, and so slips past the NON_SLOT_TYPES filter as a
    perfectly legal undershirt — this round's own defect, surviving in migration."""
    cat, grp, kind, roles = vocab.reconcile("inner", "underwear", ["inner"], "socks")
    assert (grp, kind) == ("footwear", "socks")
    assert cat == "footwear" and roles == ["footwear"]
    assert kind in vocab.NON_SLOT_TYPES


@pytest.mark.parametrize("group,kind", list(vocab.LEGACY_TYPE_GROUP))
def test_every_legacy_regroup_lands_on_a_group_that_owns_that_type(group, kind):
    """A regroup pointing at a group whose TYPES lack the type would drop it again,
    silently, which is the bug the table exists to prevent."""
    dest = vocab.LEGACY_TYPE_GROUP[(group, kind)]
    assert kind in vocab.TYPES[dest]
    assert vocab.reconcile("base", group, None, kind)[2] == kind


def test_no_type_is_invented_for_an_untyped_item():
    """Nothing in a pre-2026-08-14 record says whether a "top" is a tee or a polo,
    and a wrong type would enter the prompt as fact."""
    _, _, kind, _ = vocab.reconcile("base", "tops", ["base"], None)
    assert kind is None


# ── apply_type_defaults: fill, never clamp ─────────────────────────────────────

def test_defaults_fill_when_the_classifier_gave_nothing():
    warmth, formality = vocab.apply_type_defaults("puffer", None, [])
    assert warmth == 5
    assert formality == ["casual", "active"]


def test_defaults_never_overwrite_a_stated_value():
    """A light trench is a `coat` at warmth 3. Rounding it up to the table's 4 would
    walk it past the _OUTER_MIN_WARMTH floor at 4C — the exact 2026-08-10 failure,
    reintroduced by the guard meant to prevent it."""
    warmth, formality = vocab.apply_type_defaults("coat", 3, ["casual"])
    assert warmth == 3
    assert formality == ["casual"]


def test_defaults_for_an_unknown_type_are_the_old_fallbacks():
    assert vocab.apply_type_defaults(None, None, []) == (3, ["casual"])
    assert vocab.apply_type_defaults("nonsense", 4, ["smart"]) == (4, ["smart"])


def test_a_tee_and_a_polo_differ_in_the_field_the_prompt_prints():
    """The 08-14 branch shipped the type level and could not show it steering a
    pick: given a polo and a tee identical in every other attribute on a smart day,
    the model chose the tee. Formality is the lever — and it is already printed on
    every wardrobe line."""
    _, tee = vocab.apply_type_defaults("t_shirt", None, [])
    _, polo = vocab.apply_type_defaults("polo", None, [])
    assert "smart" not in tee
    assert "smart" in polo
