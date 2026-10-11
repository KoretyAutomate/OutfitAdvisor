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


# ── raised by the pre-push reviewer, 2026-10-11 ────────────────────────────────

def test_a_too_thin_layer_is_replaced_not_only_an_empty_slot_filled():
    from wardrobe_fixtures import JACKET, OXFORD
    d = day(3, TEE, OXFORD, JACKET, SWEATER, JEANS, SNEAK)
    fixed, _ = fallback.fix(ids(base=TEE, mid=OXFORD, outer=JACKET, bottoms=JEANS, footwear=SNEAK), d)
    assert SWEATER["id"] in fixed.values(), fixed


def test_too_warm_is_better_than_no_top():
    d = day(29, SWEATER, JEANS, SNEAK, hi=32)
    fixed, _ = fallback.fix(ids(bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["base"] == SWEATER["id"] or fixed["mid"] == SWEATER["id"] or fixed["outer"] == SWEATER["id"]


def test_a_dress_put_on_late_still_takes_the_trousers_off():
    d = day(20, DRESS, JEANS, SNEAK)
    fixed, _ = fallback.fix(ids(bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["base"] == DRESS["id"] and fixed["bottoms"] is None


def test_on_snow_the_fallback_reaches_for_waterproof():
    """Raised by the pre-push reviewer, 2026-10-11."""
    from wardrobe_fixtures import BOOTS, g
    parka = g("parka0001", "waterproof parka", "outerwear", "coat", ["outer"], 5, waterproof=True)
    wool = g("woolcoat1", "wool coat", "outerwear", "coat", ["outer"], 5)
    d = day(-3, UNDER, TEE, wool, parka, JEANS, SNEAK, BOOTS, isSnow=True)
    fixed, _ = fallback.fix(ids(inner=UNDER, base=TEE, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["outer"] == parka["id"] and fixed["footwear"] == BOOTS["id"]


def test_missing_trousers_are_filled_with_what_suits_the_heat():
    """Raised by the pre-push reviewer, 2026-10-11: jeans listed first, shorts owned."""
    fixed, _ = fallback.fix(ids(base=TEE, footwear=SNEAK), day(29, TEE, JEANS, SHORTS, SNEAK, hi=32))
    assert fixed["bottoms"] == SHORTS["id"]


def test_a_dress_put_on_mid_fallback_takes_the_trousers_off_at_once():
    """Raised by the pre-push reviewer, 2026-10-11: under a dress/jeans ban, the
    trousers left on until the end blocked the shoes swap."""
    import picks as pk
    from wardrobe_fixtures import BOOTS
    ban = {"kind": "avoid_pair", "a": {"type": "dress"}, "b": {"type": "jeans"}}
    d = day(29, SWEATER, DRESS, JEANS, BOOTS, SNEAK, hi=32, prefs=pk.Prefs(rules=(ban,)))
    fixed, _ = fallback.fix(ids(base=SWEATER, bottoms=JEANS, footwear=BOOTS), d)
    assert fixed["base"] == DRESS["id"] and fixed["bottoms"] is None and fixed["footwear"] == SNEAK["id"], fixed


def test_with_no_knitwear_the_warmer_polo_replaces_the_thinner_one():
    """Raised by the pre-push reviewer, 2026-10-11: warm-up must not restore the
    stack step 4 took apart."""
    d = day(10, POLO, KNIT_POLO, JEANS, SNEAK)
    fixed, _ = fallback.fix(ids(base=POLO, mid=KNIT_POLO, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["base"] == KNIT_POLO["id"] and not fixed.get("mid"), fixed


def test_the_warmer_top_swap_respects_the_afternoon():
    """Raised by the pre-push reviewer, 2026-10-11: 10C morning, 30C afternoon."""
    fixed, _ = fallback.fix(ids(base=POLO, mid=KNIT_POLO, bottoms=JEANS, footwear=SNEAK),
                            day(10, POLO, KNIT_POLO, JEANS, SNEAK, hi=30))
    assert fixed["base"] != KNIT_POLO["id"], fixed


def test_two_shirts_stacked_lose_the_upper_one():
    """Raised by the pre-push reviewer, 2026-10-11: the check calls two of a kind
    `stacked`; the fallback must resolve exactly that."""
    from wardrobe_fixtures import OXFORD, g
    flannel = g("flannel01", "red flannel shirt", "tops", "shirt", ["base", "mid", "outer"], 2)
    fixed, _ = fallback.fix(ids(base=OXFORD, mid=flannel, bottoms=JEANS, footwear=SNEAK),
                            day(15, OXFORD, flannel, JEANS, SNEAK, CARDI))
    assert fixed["base"] == OXFORD["id"] and fixed["mid"] != flannel["id"], fixed


def test_warm_up_never_restores_two_sweaters():
    """Raised by the pre-push reviewer, 2026-10-11: the thick sweater replaces the
    thin one instead of going back on top of it."""
    from wardrobe_fixtures import g
    thin = g("thinswtr1", "thin grey sweater", "tops", "sweater", ["base", "mid", "outer"], 2)
    fixed, _ = fallback.fix(ids(base=thin, mid=SWEATER, bottoms=JEANS, footwear=SNEAK),
                            day(3, thin, SWEATER, JEANS, SNEAK))
    torso = [fixed.get(c) for c in ("base", "mid", "outer") if fixed.get(c)]
    assert torso == [SWEATER["id"]], fixed


def test_a_dress_swapped_for_a_warmer_top_gets_its_trousers_back():
    """Raised by the pre-push reviewer, 2026-10-11."""
    from wardrobe_fixtures import g
    sweater_base = g("swbase001", "chunky sweater", "tops", "sweater", ["base"], 4)
    fixed, _ = fallback.fix(ids(base=DRESS, footwear=SNEAK), day(3, DRESS, sweater_base, JEANS, SNEAK))
    assert fixed["base"] == sweater_base["id"], "the scenario: the dress gave way to warmth"
    assert fixed["bottoms"] == JEANS["id"], fixed


def test_a_dress_is_kept_when_no_trousers_could_replace_it():
    """Raised by the pre-push reviewer, 2026-10-11."""
    from wardrobe_fixtures import g
    sweater_base = g("swbase002", "chunky sweater", "tops", "sweater", ["base"], 4)
    fixed, _ = fallback.fix(ids(base=DRESS, footwear=SNEAK), day(3, DRESS, sweater_base, SNEAK))
    assert fixed["base"] == DRESS["id"], fixed


def test_cooling_never_swaps_in_a_second_top():
    """Raised by the pre-push reviewer, 2026-10-11: tee + hot sweater + jacket at
    24C — the sweater is shed, not swapped for a polo over the tee."""
    from wardrobe_fixtures import JACKET
    import check
    d = day(24, TEE, SWEATER, JACKET, POLO, JEANS, SNEAK, hi=27)
    fixed, _ = fallback.fix(ids(base=TEE, mid=SWEATER, outer=JACKET, bottoms=JEANS, footwear=SNEAK), d)
    assert "stacked" not in check.hard(check.issues(fixed, d)), fixed
