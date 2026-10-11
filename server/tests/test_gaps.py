"""Which empty slots are a hole in the WARDROBE (gaps.py, 2026-10-11) — judged on
the final picks against what they own, never on the model's word alone."""
import gaps
from wardrobe_fixtures import DRESS, JACKET, JEANS, OXFORD, SNEAK, SWEATER, TEE, day, ids


def test_a_slot_the_fallback_emptied_with_nothing_legal_owned_is_a_gap():
    d = day(18, TEE, JEANS, SNEAK)
    assert gaps.missing(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d, [], {"outer"}) == ["outer"]


def test_a_claimed_slot_that_is_filled_is_not_a_gap():
    d = day(18, TEE, JEANS, SNEAK)
    assert gaps.missing(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d, ["base"], set()) == []


def test_the_models_claim_is_checked_against_the_wardrobe():
    """It said nothing fits as outer; a jacket sits there unused."""
    d = day(14, TEE, JACKET, JEANS, SNEAK)
    assert gaps.missing(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d, ["outer"], set()) == []


def test_bottoms_under_a_dress_are_not_a_gap():
    d = day(22, DRESS, SNEAK)
    assert gaps.missing(ids(base=DRESS, footwear=SNEAK), d, ["bottoms"], {"bottoms"}) == []


def test_junk_from_the_model_is_ignored_and_order_is_wearing_order():
    d = day(18, TEE)
    got = gaps.missing(ids(base=TEE), d, ["footwear", "hat", 7, "bottoms"], set())
    assert got == ["bottoms", "footwear"]


def test_one_shirt_in_one_slot_does_not_fill_another():
    """The oxford is worn as base; nothing else can be mid."""
    d = day(18, OXFORD, JEANS, SNEAK)
    assert gaps.missing(ids(base=OXFORD, bottoms=JEANS, footwear=SNEAK), d, ["mid"], set()) == ["mid"]


def test_cold_is_its_own_word():
    d = day(3, TEE, JEANS, SNEAK)
    assert gaps.missing(ids(base=TEE, bottoms=JEANS, footwear=SNEAK), d, [], set()) == [gaps.COLD_GAP]
    warm = day(3, TEE, SWEATER, JEANS, SNEAK)
    assert gaps.missing(ids(base=TEE, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), warm, [], set()) == []
