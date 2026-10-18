"""A cold morning wants a coat over the knitwear (user, 2026-10-18).

The 06:31 outfit on a 2-13C day (felt -1..10C): an undershirt, a light blue polo, a
dusty rose sweater, beige cargo trousers, grey sneakers — and no coat. "Warm enough"
asks whether ANY one torso garment meets the table, which tops out at warmth 4 below
5C, so the sweater alone passed and the fallback took the coat off. Replayed against
the live model: test_results/advisor_review_2026-10-18.txt.
"""
import check
import fallback
import layers
import picks as pk
from wardrobe_fixtures import CARDI, JACKET, JEANS, POLO, SNEAK, SWEATER, UNDER, day, g, ids

COAT = g("woolcoat1", "navy wool coat", "outerwear", "coat", ["outer"], 5)
PUFFER = g("puffer001", "black puffer", "outerwear", "puffer", ["outer"], 5)
BLAZER = g("blazer001", "grey blazer", "outerwear", "blazer", ["mid", "outer"], 2)


def found(picks, d):
    return {i.kind: i for i in check.issues(picks, d)}


# ── no-coat ───────────────────────────────────────────────────────────────────

def test_the_morning_as_served_is_now_a_hard_issue_that_says_how_to_fix_it():
    d = day(-1, UNDER, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    issue = found(ids(inner=UNDER, base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)["no-coat"]
    assert issue.hard
    assert "navy wool coat" in issue.text and "outer" in issue.text and "mid" in issue.text


def test_a_sweater_filed_as_outer_is_not_the_coat():
    d = day(-1, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    assert "no-coat" in found(ids(base=POLO, outer=SWEATER, bottoms=JEANS, footwear=SNEAK), d)


def test_wearing_a_coat_answers_it():
    d = day(-1, UNDER, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    assert "no-coat" not in found(ids(inner=UNDER, base=POLO, mid=SWEATER, outer=COAT,
                                      bottoms=JEANS, footwear=SNEAK), d)


def test_owning_no_coat_is_not_something_asking_again_can_fix():
    d = day(-1, POLO, SWEATER, JEANS, SNEAK, hi=10)
    assert "no-coat" not in found(ids(base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)


def test_a_blazer_is_neither_the_coat_nor_demanded():
    only_blazer = day(-1, POLO, SWEATER, BLAZER, JEANS, SNEAK, hi=10)
    assert "no-coat" not in found(ids(base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), only_blazer)
    both = day(-1, POLO, SWEATER, BLAZER, COAT, JEANS, SNEAK, hi=10)
    assert "no-coat" in found(ids(base=POLO, mid=SWEATER, outer=BLAZER, bottoms=JEANS, footwear=SNEAK), both)


def test_a_mild_morning_asks_for_nothing():
    d = day(layers.COAT_BELOW_C, POLO, SWEATER, COAT, JEANS, SNEAK)
    assert "no-coat" not in found(ids(base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)


def test_a_banned_coat_is_never_demanded():
    ban = {"kind": "avoid_item", "a": {"type": "coat"}}
    d = day(-1, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10, prefs=pk.Prefs(rules=(ban,)))
    assert "no-coat" not in found(ids(base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)


def test_a_coat_too_warm_for_the_morning_is_never_demanded():
    """A puffer at 7C: demanding it would collide with hot-outer, and no answer could
    pass either (plan review, 2026-10-18)."""
    d = day(7, POLO, SWEATER, PUFFER, JEANS, SNEAK)
    assert check.layers.overdressed(PUFFER, "outer", d.wd, d.plan, d.peak, d.rules)
    assert "no-coat" not in found(ids(base=POLO, mid=SWEATER, bottoms=JEANS, footwear=SNEAK), d)


# ── coat-light ────────────────────────────────────────────────────────────────

def test_a_light_jacket_with_a_warm_coat_owned_is_worth_one_more_try():
    d = day(-1, POLO, SWEATER, JACKET, COAT, JEANS, SNEAK, hi=10)
    issue = found(ids(base=POLO, mid=SWEATER, outer=JACKET, bottoms=JEANS, footwear=SNEAK), d)["coat-light"]
    assert not issue.hard and "navy wool coat is warmer" in issue.text


def test_the_light_jacket_is_the_coat_when_it_is_all_they_own():
    d = day(-1, POLO, SWEATER, JACKET, JEANS, SNEAK, hi=10)
    assert not {"coat-light", "no-coat"} & set(found(ids(base=POLO, mid=SWEATER, outer=JACKET,
                                                         bottoms=JEANS, footwear=SNEAK), d))


# ── the layer budget and the undershirt ───────────────────────────────────────

def test_a_cold_morning_allows_undershirt_top_knit_and_coat():
    d = day(6, UNDER, POLO, CARDI, JACKET, JEANS, SNEAK)
    worn = ids(inner=UNDER, base=POLO, mid=CARDI, outer=JACKET, bottoms=JEANS, footwear=SNEAK)
    assert "layers" not in found(worn, d)
    assert layers.max_layers(worn, d.wd.by_item, d.plan) == 4


def test_a_dropped_undershirt_is_worth_one_more_try():
    d = day(-1, UNDER, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    issue = found(ids(base=POLO, mid=SWEATER, outer=COAT, bottoms=JEANS, footwear=SNEAK), d)["no-inner"]
    assert not issue.hard and "grey v-neck inner" in issue.text


def test_no_undershirt_is_asked_for_whose_sleeves_would_show():
    """Pre-push reviewer, 2026-10-18: a long-sleeved undershirt under a short-sleeved
    polo is what sleeve-inner forbids; asking for it made the two unsatisfiable."""
    long_under = g("thermal01", "white long-sleeve thermal", "underwear", "thermal", ["inner"], 2, sleeve="long")
    short_polo = g("polo00009", "navy short-sleeve polo", "tops", "polo", ["base"], 1, sleeve="short")
    d = day(-1, long_under, short_polo, SWEATER, COAT, JEANS, SNEAK, hi=10)
    worn = ids(base=short_polo, mid=SWEATER, outer=COAT, bottoms=JEANS, footwear=SNEAK)
    assert "no-inner" not in found(worn, d)
    assert "sleeve-inner" in found({**worn, "inner": long_under["id"]}, d), "the clash it avoids"


def test_no_undershirt_is_asked_for_where_the_budget_has_no_room():
    """15C allows two layers: polo and cardigan. Asking for the undershirt too would
    fight the layer budget (plan review, 2026-10-18)."""
    d = day(15, UNDER, POLO, CARDI, JEANS, SNEAK)
    assert "no-inner" not in found(ids(base=POLO, mid=CARDI, bottoms=JEANS, footwear=SNEAK), d)


# ── the fallback puts the coat OVER the knitwear ──────────────────────────────

def test_the_fallback_moves_the_sweater_in_and_puts_the_coat_over_it():
    """Replacing the sweater was one change and moving it two; the kept-garment rank
    makes the search keep the sweater (plan review, 2026-10-18)."""
    d = day(-1, UNDER, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    fixed, changed = fallback.fix(ids(inner=UNDER, base=POLO, outer=SWEATER, bottoms=JEANS, footwear=SNEAK), d)
    assert fixed["mid"] == SWEATER["id"] and fixed["outer"] == COAT["id"], fixed
    assert changed == {"mid": SWEATER["id"], "outer": COAT["id"]}


def test_the_fallback_never_takes_the_coat_off_a_cold_morning():
    """What 06:31 did: the coat broke a hard fact and came off. Here it is in a slot
    it cannot be worn in (mid) — the fix puts it where it goes, not on the floor."""
    d = day(-1, UNDER, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    fixed, _ = fallback.fix(ids(inner=UNDER, base=POLO, mid=COAT, outer=SWEATER, bottoms=JEANS,
                                footwear=SNEAK), d)
    assert fixed["outer"] == COAT["id"] and fixed["mid"] == SWEATER["id"], fixed


def test_a_move_is_one_step():
    """The sweater from outer to mid in one move, so the coat over it is two steps
    away rather than three — the beam keeps the path at any wardrobe size."""
    d = day(-1, POLO, SWEATER, COAT, JEANS, SNEAK, hi=10)
    start = {**dict.fromkeys(("inner", "mid", "accessories")), **ids(base=POLO, outer=SWEATER, bottoms=JEANS,
                                                                    footwear=SNEAK)}
    moved = {**start, "outer": None, "mid": SWEATER["id"]}
    assert moved in list(fallback._moves(start, d))
