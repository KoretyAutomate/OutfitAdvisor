"""Which empty slots mean the wardrobe is genuinely SHORT of a garment.

Split out of test_shopping.py on 2026-08-27, when it crossed the line ceiling.
These cover picks._missing_slots and picks._has_suitable_alternative: the
difference between a slot nothing was put in and a slot nothing FITS, which is what
separates evidence from noise in the purchase suggestions.
"""


from fastapi.testclient import TestClient

import app as app_mod
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


