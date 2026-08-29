"""Which empty slots mean the wardrobe is genuinely SHORT of a garment.

Split out of test_shopping.py on 2026-08-27, when it crossed the line ceiling.
These cover picks._missing_slots and picks._has_suitable_alternative: the
difference between a slot nothing was put in and a slot nothing FITS, which is what
separates evidence from noise in the purchase suggestions.
"""


from fastapi.testclient import TestClient

import app as app_mod
import closet as closet_mod
import picks as picks_mod


def _wd(by_item, by_roles, by_group=None):
    """The lookups these checks read, as the one object they now take."""
    return picks_mod.Wardrobe(frozenset(by_item), {}, by_roles,
                              by_group or {}, by_item)

BY_ITEM = {"shell": {"id": "shell", "warmth": 2, "label": "thin shell",
                     "type": "rainwear", "colors": []},
           "coat": {"id": "coat", "warmth": 5, "label": "wool coat",
                    "type": "coat", "colors": []},
           "tee": {"id": "tee", "warmth": 1, "label": "tee",
                   "type": "t_shirt", "colors": []}}

BY_ROLES = {"shell": ["outer"], "coat": ["outer"], "tee": ["base"]}


client = TestClient(app_mod.app)

ITEM = {"id": "itm-tee-0001", "label": "white t-shirt", "category": "base",
        "group": "tops", "type": "t_shirt", "roles": ["base"], "colors": ["white"],
        "warmth": 1, "formality": ["casual"], "waterproof": False, "availableCount": 2}
COLD = {"lo": 2, "hi": 9, "feelsLo": 0, "feelsHi": 7, "desc": "Cold", "rain": 10,
        "wind": 4, "morning": 3, "midday": 8, "evening": 5, "swing": 7,
        "isRain": False, "isSnow": False, "code": 3}

def test_a_slot_we_cleared_ourselves_counts_as_missing():
    """The model only knows about the gaps IT left.

    A slot it filled and this module then cleared — a duplicate, an item in a role
    it cannot play, a garment too thin for the cold, one the wearer has banned —
    means the wardrobe had nothing legal for that slot. That is exactly a gap, and
    because the model believed the slot was filled it never appears in `missing`.
    Without this the slot reads "None needed", the weather takes the blame, and the
    shopping list never hears about it. Raised by the pre-push reviewer, 2026-08-27.
    """
    got = picks_mod._missing_slots(["outer"], {"outer": None, "mid": None, "base": "x"},
                                    {"mid", "base"})
    assert got == ["mid", "outer"]


def test_a_slot_the_model_claims_but_then_fills_is_not_a_gap():
    """Otherwise the phone remembers a hole that was never there, for weeks."""
    assert picks_mod._missing_slots(["base"], {"base": "x"}, set()) == []


def test_bottoms_cleared_under_a_dress_is_not_a_gap():
    """A dress covers the legs. That is a dress, not a hole in the wardrobe."""
    assert picks_mod._missing_slots([], {"bottoms": None, "base": "d1"},
                                     {"bottoms", "base"}, {"bottoms"}) == []


def test_bottoms_cleared_for_ANY_OTHER_reason_IS_a_gap():
    """Excluding the slot outright hid a real one.

    Validation clears a bottoms pick for a role it cannot play, or because the
    wearer banned it — and the model, believing the slot filled, never names it. A
    blanket exclusion meant that gap could never reach the shopping evidence.
    Raised by the pre-push reviewer, 2026-08-27.
    """
    assert picks_mod._missing_slots([], {"bottoms": None, "base": "t1"},
                                     {"bottoms", "base"}, set()) == ["bottoms"]


def test_the_slots_come_back_in_wearing_order():
    """The phone lists them; inner-outwards is the order everything else uses."""
    got = picks_mod._missing_slots(["footwear", "inner", "outer"],
                                    {"inner": None, "outer": None, "footwear": None}, set())
    assert got == ["inner", "outer", "footwear"]


def test_junk_from_the_model_is_ignored():
    assert picks_mod._missing_slots(["elbow", None, 7], {"outer": None}, set()) == []
    assert picks_mod._missing_slots(None, {"outer": None}, set()) == []


def test_a_tip_naming_something_unowned_goes_too():
    """The tip is the line the notification shows."""
    out = {"bullets": ["Blue jeans work today."], "tip": "Bring a wool overcoat."}
    text = picks_mod._assemble_text(out, [], closet_mod.Prefs(closet_only=True),
                                     {"bottoms": "i2"}, {"i2": {"label": "blue jeans"}})
    assert "overcoat" not in text


def test_a_correctly_chosen_dress_does_not_record_a_bottoms_gap():
    """The model can get it right first time: dress in base, bottoms already null.

    Nothing is cleared then, so a version that keyed coverage on the CLEARING
    recorded a false bottoms gap for ninety days on exactly the outfits that were
    correct. Coverage is read off the garment in `base`. Raised by the reviewer.
    """
    assert picks_mod._missing_slots(["bottoms"], {"base": "d1", "bottoms": None},
                                     set(), {"bottoms"}) == []


def test_a_garment_owned_but_UNSUITABLE_is_still_a_gap():
    """Owning something for the slot is not the test.

    A closet holding only a warmth-2 shell must be able to learn that it needs a
    warmer coat, not merely that it owns no coat. The warmth check and the rule
    repair are judgements about the GARMENT — the wardrobe was in front of the judge
    and was found wanting — so the alternatives filter must not apply to them.
    Raised by the pre-push reviewer, 2026-08-27.
    """
    # `unsuitable` bypasses the alternatives test — that is its purpose.
    assert picks_mod._missing_slots([], {"outer": None, "base": "tee"},
                                     {"outer", "base"}, set(),
                                     lambda slot: True, {"outer"}) == ["outer"]


def test_a_cleared_pick_is_not_a_gap_when_something_else_fits():
    """A slot nothing got put in is not a slot nothing FITS.

    The model can choose a warmth-2 jacket while a warmth-5 coat sits in the
    wardrobe, or use an item in a role it cannot play while another plays it fine.
    Validation clears the pick either way — and calling that an ownership gap has
    the shopping list recommending a coat the person already owns. Raised by the
    pre-push reviewer, 2026-08-27.
    """
    # No `unsuitable` — the pick was cleared for being a MISCHOICE (wrong role, or a
    # duplicate), and another item fills the slot fine. The predicate is the same
    # one the clearing steps use: unused, warm enough, legal.
    assert picks_mod._missing_slots([], {"outer": None, "base": "tee1"},
                                     {"outer", "base"}, set(),
                                     lambda slot: slot == "outer", set()) == []


def test_it_IS_a_gap_when_nothing_in_the_wardrobe_can_fill_it():
    assert picks_mod._missing_slots([], {"outer": None, "base": "tee1"},
                                     {"outer", "base"}, set(),
                                     lambda slot: False, set()) == ["outer"]


def test_a_check_that_cannot_run_does_not_pass_everything():
    """Without the roles to hand the filter is skipped, not assumed satisfied."""
    assert picks_mod._missing_slots(["outer"], {"outer": None}, set(), set(), None) \
        == ["outer"]


def test_a_warm_coat_sitting_unused_means_the_wardrobe_is_not_short():
    """The model picking the thin shell is a mischoice, not a missing coat.

    Recording it would eventually recommend buying the coat they already own.
    Raised by the pre-push reviewer, 2026-08-27.
    """
    assert picks_mod._has_suitable_alternative("outer", {"base": "tee"}, _wd(BY_ITEM, BY_ROLES), 4.0, [])


def test_when_the_only_outer_layer_is_too_thin_it_IS_a_gap():
    by_item = {k: v for k, v in BY_ITEM.items() if k != "coat"}
    assert not picks_mod._has_suitable_alternative(
        "outer", {"base": "tee"},
        _wd(by_item, {"shell": ["outer"], "tee": ["base"]}), 4.0, [])


def test_an_alternative_the_wearer_has_banned_does_not_count():
    """It has to be one the generator could legitimately have picked."""
    ban = [{"kind": "avoid_item", "a": {"type": "coat"}}]
    assert not picks_mod._has_suitable_alternative("outer", {"base": "tee"}, _wd(BY_ITEM, BY_ROLES), 4.0, ban)


def test_a_garment_already_worn_elsewhere_is_not_an_alternative():
    """One garment fills one slot; it cannot rescue a second."""
    assert not picks_mod._has_suitable_alternative(
        "outer", {"base": "tee", "mid": "coat"},
        _wd(BY_ITEM, {**BY_ROLES, "coat": ["outer", "mid"]}), 4.0, [])


def test_warmth_only_constrains_the_outer_layer():
    """A thin base is not a gap; the warmth rule is about what is outermost."""
    assert picks_mod._has_suitable_alternative("base", {}, _wd(BY_ITEM, BY_ROLES), 4.0, [])


def test_one_shirt_playing_two_roles_does_not_hide_the_second_gap():
    """The aggregate role set was too coarse.

    A single shirt that can play base OR mid, left in base by the deduplicator, made
    `mid` look filled — so a real mid gap never reached the shopping evidence. The
    predicate asks whether an UNUSED garment can fill the slot. Raised by the
    pre-push reviewer, 2026-08-27.
    """
    by_item = {"shirt": {"id": "shirt", "warmth": 2, "label": "oxford",
                         "type": "shirt", "colors": []}}
    by_roles = {"shirt": ["base", "mid"]}
    # The shirt is worn in base, so nothing is left for mid.
    assert not picks_mod._has_suitable_alternative("mid", {"base": "shirt"}, _wd(by_item, by_roles), 12.0, [])
    assert picks_mod._missing_slots(
        [], {"base": "shirt", "mid": None}, {"base", "mid"}, set(),
        lambda slot: picks_mod._has_suitable_alternative(
            slot, {"base": "shirt", "mid": None}, _wd(by_item, by_roles), 12.0, []),
        set()) == ["mid"]


def test_the_models_own_claim_is_checked_against_the_wardrobe():
    """It is a judgement, and one this module can check directly.

    If an unused, warm enough, legal garment is sitting there, the slot was
    misclassified — and one such mistake would be kept for ninety days and end as a
    recommendation to buy something already owned. Raised by the pre-push reviewer,
    2026-08-27.
    """
    assert picks_mod._missing_slots(["outer"], {"outer": None}, set(), set(),
                                     lambda slot: True, set()) == []
    assert picks_mod._missing_slots(["outer"], {"outer": None}, set(), set(),
                                     lambda slot: False, set()) == ["outer"]


def test_a_slot_already_proven_short_skips_the_test_it_has_passed():
    """`unsuitable` is only ever set after _has_suitable_alternative found nothing."""
    assert picks_mod._missing_slots(["outer"], {"outer": None}, set(), set(),
                                     lambda slot: True, {"outer"}) == ["outer"]


def test_a_warmer_coat_can_be_suggested_to_someone_who_owns_a_coat():
    """The invariant that makes this safe, and the reason type-matching is refused.

    A slot only enters the evidence when picks._missing_slots found nothing in the
    wardrobe that could fill it. So owning a coat AND having an outer gap means the
    coat is not up to the weather — and "a wool overcoat" is precisely what should
    be said. Blocking it because the person owns something of type `coat` would
    leave them with a gap the advisor can see, has evidence for, and may not name.

    A reviewer asked for that block on 2026-08-27; this is the reason it was not
    added, pinned so the next reader does not have to reconstruct it.
    """
    thin = {"acme": {"id": "acme", "warmth": 2, "label": "Acme", "type": "coat",
                     "colors": []}}
    roles = {"acme": ["outer"]}
    assert not picks_mod._has_suitable_alternative("outer", {}, _wd(thin, roles), 4.0, [])

    warm = {"acme": {**thin["acme"], "warmth": 5}}
    assert picks_mod._has_suitable_alternative("outer", {}, _wd(warm, roles), 4.0, [])
    # With an adequate coat there is no outer gap, so nothing is suggested for it.
    assert picks_mod._missing_slots([], {"outer": None}, {"outer"}, set(),
                                    lambda s: True, set()) == []
