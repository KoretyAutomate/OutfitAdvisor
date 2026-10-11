"""The last resort (fallback.py, 2026-10-11): what the advisor's best answer still
gets wrong after its revisions — and only that."""
import fallback
from wardrobe_fixtures import (CARDI, DRESS, JEANS, KNIT_POLO, POLO, SHORTS, SNEAK, SWEATER, TEE,
                               UNDER, day, ids)


def test_polo_over_polo_loses_the_upper_polo_and_gains_knitwear():
    """What a person would do: take the second polo off, put a cardigan on."""
    d = day(10, POLO, KNIT_POLO, CARDI, JEANS, SNEAK)
    fixed, changed = fallback.fix(ids(base=POLO, mid=KNIT_POLO, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["base"] == POLO["id"] and fixed["mid"] == CARDI["id"]
    assert changed == {"mid": CARDI["id"]}


def test_missing_shoes_and_trousers_are_put_on():
    fixed, changed = fallback.fix(ids(base=TEE), day(18, TEE, JEANS, SNEAK))
    assert fixed["bottoms"] == JEANS["id"] and fixed["footwear"] == SNEAK["id"]
    assert set(changed) == {"bottoms", "footwear"}


def test_far_too_warm_a_layer_comes_off_and_trousers_swap_for_cooler_ones():
    d = day(29, TEE, SWEATER, JEANS, SHORTS, SNEAK, hi=32)
    fixed, _ = fallback.fix(ids(base=TEE, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["mid"] is None and fixed["bottoms"] == SHORTS["id"]


def test_trousers_with_nothing_cooler_stay_on():
    d = day(29, TEE, JEANS, SNEAK, hi=32)
    fixed, changed = fallback.fix(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["bottoms"] == JEANS["id"] and changed == {}


def test_a_dress_takes_the_trousers_off():
    fixed, changed = fallback.fix(ids(base=DRESS, bottoms=JEANS, footwear=SNEAK), day(20, DRESS, JEANS, SNEAK))
    assert fixed["bottoms"] is None and changed == {"bottoms": None}


def test_an_undershirt_with_no_top_owned_is_taken_off():
    fixed, _ = fallback.fix(ids(inner=UNDER, bottoms=JEANS), day(20, UNDER, JEANS))
    assert fixed["inner"] is None


def test_unknown_and_twice_used_garments_are_dropped_before_anything_is_added():
    d = day(18, TEE, JEANS, SNEAK)
    fixed, _ = fallback.fix({"base": TEE["id"], "mid": TEE["id"], "bottoms": "i99", "footwear": SNEAK["id"]}, d)
    assert fixed["mid"] is None and fixed["bottoms"] == JEANS["id"]
