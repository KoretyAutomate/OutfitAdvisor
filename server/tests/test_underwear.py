"""inner is UNDERWEAR, and underwear is never the outermost thing (2026-08-29).

The user's instruction: "inner alone cannot be suggested. inner means underwear."

It is a plausible-looking answer for a model that has been told to drop layers as
the temperature rises — one fewer garment, and the undershirt is the lightest thing
in the wardrobe. Which is exactly the shape of mistake this project keeps deciding
to catch in code rather than hope about in prose.
"""
import prose as prose_mod
import picks as pk


def test_an_undershirt_on_its_own_is_not_an_outfit():
    assert pk._inner_left_bare({"inner": "u1"}, {})


def test_anything_worn_over_it_is_enough():
    for cover in ("base", "mid", "outer"):
        assert not pk._inner_left_bare({"inner": "u1", cover: "x1"}, {}), cover


def test_no_undershirt_is_not_a_problem():
    assert not pk._inner_left_bare({"base": "t1"}, {})
    assert not pk._inner_left_bare({}, {})


def test_bottoms_and_shoes_do_not_cover_a_torso():
    """The rule is about the TOP half. Trousers do not make an undershirt decent."""
    assert pk._inner_left_bare({"inner": "u1", "bottoms": "j1", "footwear": "s1"}, {})


def test_the_first_failure_is_retried_rather_than_repaired():
    """A regeneration can put a top back on, which is a better outfit than one
    layer fewer."""
    picks = {"inner": "u1"}
    note, _ = pk._enforce_underwear(picks, {"u1": {"label": "grey undershirt"}}, [], 0)
    assert "UNDERWEAR" in note
    assert picks["inner"] == "u1", "the first attempt must not repair"


def test_out_of_retries_the_undershirt_is_cleared():
    picks = {"inner": "u1"}
    note, banned = pk._enforce_underwear(
        picks, {"u1": {"label": "grey undershirt", "type": "undershirt",
                       "colors": ["grey"]}}, [], 1)
    assert not note
    assert picks["inner"] is None
    # And the prose that named it goes too — an empty slot with a bullet still
    # recommending the undershirt keeps the promise in the data and breaks it on
    # screen, which is the half the user reads.
    assert prose_mod._names_banned("Start with your grey undershirt.", banned)


def test_the_prompt_says_it_as_well():
    """The check is what makes it true; the prompt is what usually makes it
    unnecessary."""
    import closet as closet_mod
    prompt = closet_mod._closet_prompt(
        {"lo": 24, "hi": 33, "feelsLo": 25, "feelsHi": 35, "desc": "Hot", "rain": 0,
         "wind": 2, "morning": 26, "midday": 32, "evening": 28, "swing": 9,
         "isRain": False, "isSnow": False, "code": 0},
        "man", "casual",
        [{"id": "itm-u-0001", "label": "undershirt", "category": "inner",
          "group": "underwear", "type": "undershirt", "roles": ["inner"],
          "colors": ["grey"], "warmth": 1, "formality": ["casual"],
          "waterproof": False, "availableCount": 2}])
    assert "UNDERWEAR RULE" in prompt
    assert "never worn on its own" in prompt


def test_a_repair_that_strips_the_last_layer_is_caught():
    """The one check whose subject other repairs can CREATE.

    An outfit of inner + an under-warm outer passed the underwear check, the warmth
    repair then removed the outer, and the bare undershirt was returned as valid. So
    it runs last, after everything that can take a torso layer away. Raised by the
    pre-push reviewer, 2026-08-29.
    """
    import closet as closet_mod
    picks = {"inner": "u1", "outer": "thin"}
    by = {"u1": {"label": "undershirt", "type": "undershirt", "colors": []},
          "thin": {"label": "thin shell", "type": "rainwear", "colors": [], "warmth": 2}}
    wd = pk.Wardrobe(frozenset(by), {"u1": "inner", "thin": "outer"},
                     {"u1": ["inner"], "thin": ["outer"]},
                     {"u1": "underwear", "thin": "outerwear"}, by)
    cold = {"lo": 2, "hi": 9, "morning": 4, "feelsLo": 0, "feelsHi": 7, "desc": "Cold",
            "rain": 0, "wind": 2, "midday": 8, "evening": 5, "swing": 7,
            "isRain": False, "isSnow": False, "code": 3}
    closet_mod._hold_to_the_rules(picks, cold, pk.Prefs(), wd, set(), 1)
    assert picks["outer"] is None, "the thin outer should have been cleared"
    assert picks["inner"] is None, "and the undershirt with it"
    assert not pk._inner_left_bare(picks, {})
