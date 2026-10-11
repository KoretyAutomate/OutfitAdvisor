"""The one fact check (check.py, 2026-10-11): what is objectively wrong with an
outfit, written for the model. Taste is the model's; these are facts."""
import check
import picks as pk
from wardrobe_fixtures import (BOOTS, CARDI, DRESS, JACKET, JEANS, KNIT_POLO, OXFORD, POLO,
                               SHORTS, SNEAK, SWEATER, TEE, UNDER, day, ids)


def kinds(picks, d):
    return {i.kind for i in check.issues(picks, d)}


def test_polo_over_polo_is_a_hard_issue():
    """The 2026-10-11 morning, as the check sees it."""
    d = day(10, POLO, KNIT_POLO, CARDI, JEANS, SNEAK)
    found = check.issues(ids(base=POLO, mid=KNIT_POLO, bottoms=JEANS, footwear=SNEAK), d)
    stacked = next(i for i in found if i.kind == "stacked")
    assert stacked.hard and "grey knit polo over navy polo shirt" in stacked.text


def test_a_cardigan_over_a_tee_and_an_open_shirt_over_a_tee_are_fine():
    d = day(10, TEE, CARDI, OXFORD, JEANS, SNEAK)
    assert "stacked" not in kinds(ids(base=TEE, mid=CARDI, bottoms=JEANS, footwear=SNEAK), d)
    assert "stacked" not in kinds(ids(base=TEE, mid=OXFORD, outer=CARDI, bottoms=JEANS, footwear=SNEAK), d)


def test_an_answer_that_cannot_be_worn_as_given():
    d = day(15, TEE, JEANS, SNEAK)
    found = kinds({"base": "i9", "bottoms": TEE["id"], "footwear": TEE["id"]}, d)
    assert {"unknown-base", "role-bottoms", f"twice-{TEE['id']}"} <= found


def test_shoes_and_trousers_only_when_they_own_them():
    owns = day(15, TEE, JEANS, SNEAK)
    assert {"no-bottoms", "no-footwear"} <= kinds(ids(base=TEE), owns)
    owns_none = day(15, TEE)
    assert not {"no-bottoms", "no-footwear"} & kinds(ids(base=TEE), owns_none)


def test_a_dress_covers_the_legs():
    d = day(20, DRESS, JEANS, SNEAK)
    assert "no-bottoms" not in kinds(ids(base=DRESS, footwear=SNEAK), d)
    assert "onepiece" in kinds(ids(base=DRESS, bottoms=JEANS, footwear=SNEAK), d)


def test_the_undershirt_alone_is_nothing_on_top():
    found = check.issues(ids(inner=UNDER, bottoms=JEANS), day(25, UNDER, JEANS))
    assert any(i.kind == "no-top" and "undershirt" in i.text for i in found)


def test_cold_only_when_something_they_own_would_fix_it():
    with_cardigan = day(6, TEE, CARDI, JEANS, SNEAK)
    assert "cold" in kinds(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), with_cardigan)
    nothing_warm = day(6, TEE, JEANS, SNEAK)
    assert "cold" not in kinds(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), nothing_warm), \
        "a wardrobe gap, not something asking again can fix"


def test_overdressed_but_trousers_with_nothing_cooler_are_the_trousers():
    hot = day(29, TEE, SWEATER, JEANS, SNEAK, hi=32)
    assert "hot-mid" in kinds(ids(base=TEE, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), hot)
    assert "hot-bottoms" not in kinds(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), hot)
    with_shorts = day(29, TEE, JEANS, SHORTS, SNEAK, hi=32)
    assert "hot-bottoms" in kinds(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), with_shorts)


def test_snow_wants_the_waterproof_boots_they_own():
    snow = day(-3, UNDER, SWEATER, JACKET, JEANS, SNEAK, BOOTS, isSnow=True)
    assert "snow-footwear" in kinds(ids(inner=UNDER, base=SWEATER, outer=JACKET, bottoms=JEANS,
                                        footwear=SNEAK), snow)
    rain = day(10, TEE, CARDI, JEANS, SNEAK, BOOTS, isRain=True, rain=93)
    assert not any(k.startswith("snow") for k in kinds(ids(base=TEE, mid=CARDI, bottoms=JEANS,
                                                             footwear=SNEAK), rain)), "rain is an umbrella"


def test_a_reroll_repeat_counts_only_when_something_else_suits():
    shown = pk.Prefs.of([], shown={"base": TEE["id"], "bottoms": JEANS["id"]})
    d = day(15, TEE, POLO, JEANS, SNEAK, prefs=shown)
    found = kinds(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d)
    assert "repeat-base" in found and "repeat-bottoms" not in found, "one pair of jeans is one pair"


def test_soft_issues_never_block():
    found = check.issues(ids(inner=UNDER, base=TEE, mid=CARDI, outer=JACKET, bottoms=JEANS, footwear=SNEAK),
                         day(16, UNDER, TEE, CARDI, JACKET, JEANS, SNEAK))
    layers = next(i for i in found if i.kind == "layers")
    assert not layers.hard


def test_missing_trousers_count_even_when_the_chosen_top_clashes_with_every_pair():
    """Raised by the pre-push reviewer, 2026-10-11: the top is the wrong choice, not
    the trousers optional."""
    ban = {"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"role": "bottoms"}}
    d = day(18, TEE, POLO, JEANS, SNEAK, prefs=pk.Prefs(rules=(ban,)))
    assert "no-bottoms" in kinds(ids(base=TEE, footwear=SNEAK), d)
