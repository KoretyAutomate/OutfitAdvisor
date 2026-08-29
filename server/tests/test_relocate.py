"""A garment filed one slot off is moved, not thrown away (2026-08-29).

The user's own closet, 15 items, came back with the joggers and nothing above the
waist: the one top the model chose was filed as `base`, cleared for being a `mid`,
and never reconsidered. The clearing was right about the filing and wrong about the
garment.
"""
import picks as pk

BY_ROLES = {
    "itm-hoodie-01": ["mid"],
    "itm-jeans-001": ["bottoms"],
    "itm-oxford-01": ["base", "mid"],
    "itm-coat-0001": ["outer"],
}


def _empty(**kw):
    p = {c: None for c in ("inner", "base", "mid", "outer",
                           "bottoms", "footwear", "accessories")}
    p.update(kw)
    return p


def test_a_misfiled_top_moves_to_the_slot_it_can_play():
    picks = _empty(base="itm-hoodie-01", bottoms="itm-jeans-001")
    moved = pk._relocate_mismatches(picks, ["base"], BY_ROLES)
    assert moved == [("base", "mid")]
    assert picks["mid"] == "itm-hoodie-01"
    assert picks["base"] is None
    # and the outfit still has a top, which is the whole point
    assert any(picks[c] for c in ("base", "mid", "outer"))


def test_an_item_with_nowhere_to_go_is_still_cleared():
    """The target slot is taken, so the filing error cannot be resolved by moving."""
    picks = _empty(base="itm-jeans-001", bottoms="itm-jeans-001")
    moved = pk._relocate_mismatches(picks, ["base"], BY_ROLES)
    assert moved == []
    assert picks["base"] is None
    assert picks["bottoms"] == "itm-jeans-001"


def test_the_first_free_role_wins_and_only_one_slot_is_taken():
    picks = _empty(inner="itm-oxford-01")
    moved = pk._relocate_mismatches(picks, ["inner"], BY_ROLES)
    assert moved == [("inner", "base")]
    assert picks["base"] == "itm-oxford-01" and picks["mid"] is None
    assert picks["inner"] is None


def test_two_misfiled_items_do_not_land_on_the_same_slot():
    picks = _empty(inner="itm-oxford-01", accessories="itm-hoodie-01")
    moved = pk._relocate_mismatches(picks, ["inner", "accessories"], BY_ROLES)
    assert picks["base"] == "itm-oxford-01"
    assert picks["mid"] == "itm-hoodie-01"
    assert len(moved) == 2


def test_an_unknown_item_is_cleared_rather_than_moved_anywhere():
    picks = _empty(base="itm-nothing-0")
    assert pk._relocate_mismatches(picks, ["base"], BY_ROLES) == []
    assert picks["base"] is None


def test_a_relocation_keeps_the_undershirt_covered():
    """The two repairs run in order, and this is the pairing that produced the
    bug: with the top cleared instead of moved, the underwear rule then stripped
    the inner too and the answer had nothing above the waist at all."""
    by_group = {"itm-under-001": "underwear", "itm-hoodie-01": "tops"}
    picks = _empty(inner="itm-under-001", base="itm-hoodie-01")
    pk._relocate_mismatches(picks, ["base"], BY_ROLES)
    assert not pk._inner_left_bare(picks, by_group)


# ── nobody is dressed by their trousers alone ────────────────────────────────

BY_ITEM = {
    "itm-hoodie-01": {"label": "grey hoodie", "warmth": 3},
    "itm-jeans-001": {"label": "blue jeans", "warmth": 2},
    "itm-shell-001": {"label": "thin shell", "warmth": 1},
    "itm-under-001": {"label": "airism", "warmth": 1},
}


def test_a_repair_that_strips_every_top_puts_one_back():
    picks = _empty(bottoms="itm-jeans-001")
    added = pk._enforce_a_top(picks, BY_ITEM, BY_ROLES, 22.0, [])
    assert added == ("mid", "itm-hoodie-01")
    assert picks["mid"] == "itm-hoodie-01"


def test_an_outfit_that_already_has_a_top_is_left_alone():
    for slot in ("base", "mid", "outer"):
        picks = _empty(bottoms="itm-jeans-001", **{slot: "itm-oxford-01"})
        assert pk._enforce_a_top(picks, BY_ITEM, BY_ROLES, 22.0, []) is None


def test_base_is_preferred_over_a_coat():
    by_item = {"itm-coat-0001": {"label": "wool coat", "warmth": 4},
               "itm-oxford-01": {"label": "oxford", "warmth": 2}}   # coat listed first
    picks = _empty()
    added = pk._enforce_a_top(picks, by_item, {"itm-oxford-01": ["base"],
                                               "itm-coat-0001": ["outer"]}, 22.0, [])
    assert added == ("base", "itm-oxford-01")
    assert picks["outer"] is None


def test_a_wardrobe_with_no_top_is_left_empty_rather_than_invented():
    """closetOnly exists to stop a garment being suggested that they do not own;
    the empty slots are then reported as the gap they are."""
    picks = _empty(bottoms="itm-jeans-001")
    assert pk._enforce_a_top(picks, {"itm-jeans-001": BY_ITEM["itm-jeans-001"]},
                             {"itm-jeans-001": ["bottoms"]}, 22.0, []) is None
    assert not any(picks[c] for c in ("base", "mid", "outer"))


def test_a_banned_garment_is_not_what_gets_put_on():
    ban = [{"kind": "avoid_item", "a": {"type": "hoodie"}}]
    by_item = {"itm-hoodie-01": {"label": "grey hoodie", "type": "hoodie", "warmth": 3},
               "itm-oxford-01": {"label": "oxford", "type": "shirt", "warmth": 2}}
    picks = _empty()
    added = pk._enforce_a_top(picks, by_item, BY_ROLES, 22.0, ban)
    assert added == ("base", "itm-oxford-01")


def test_a_coat_too_thin_for_the_cold_is_not_the_answer_either():
    """The last resort still respects the warmth floor it would be cleared by."""
    by_roles = {"itm-shell-001": ["outer"]}
    picks = _empty()
    assert pk._enforce_a_top(picks, BY_ITEM, by_roles, 2.0, []) is None
    assert pk._enforce_a_top(picks, BY_ITEM, by_roles, 25.0, []) == ("outer", "itm-shell-001")


def test_the_prose_names_what_was_added():
    line = pk._added_top_line(("mid", "itm-hoodie-01"), BY_ITEM)
    assert "grey hoodie" in line
    assert pk._added_top_line(("mid", "itm-nothing"), BY_ITEM).startswith("A top")


def test_two_garments_in_each_others_slots_both_move():
    """A swap, not a casualty. Choosing targets as we went made the first garment
    see an occupied slot and be dropped for it — the outfit lost a top to iteration
    order. Raised by the pre-push reviewer, 2026-08-29."""
    by_roles = {"itm-hoodie-01": ["mid"], "itm-tshirt-01": ["base"]}
    picks = _empty(base="itm-hoodie-01", mid="itm-tshirt-01")
    moved = pk._relocate_mismatches(picks, ["base", "mid"], by_roles)
    assert picks["mid"] == "itm-hoodie-01"
    assert picks["base"] == "itm-tshirt-01"
    assert sorted(moved) == [("base", "mid"), ("mid", "base")]


def test_two_garments_wanting_one_slot_keep_the_first_and_clear_the_other():
    by_roles = {"itm-hoodie-01": ["mid"], "itm-fleece-01": ["mid"]}
    picks = _empty(base="itm-hoodie-01", outer="itm-fleece-01")
    moved = pk._relocate_mismatches(picks, ["base", "outer"], by_roles)
    assert moved == [("base", "mid")]
    assert picks["mid"] == "itm-hoodie-01"
    assert picks["base"] is None and picks["outer"] is None


def test_a_dress_added_as_the_top_clears_the_trousers_under_it():
    """_enforce_a_top runs AFTER the one-piece check, which therefore cannot have
    seen what it put on. The answer went out as trousers under a dress. Raised by
    the pre-push reviewer, 2026-08-29."""
    import closet as closet_mod
    by = {"dress": {"label": "green dress", "type": "dress", "colors": [], "warmth": 2},
          "jeans": {"label": "blue jeans", "type": "jeans", "colors": [], "warmth": 2}}
    wd = pk.Wardrobe(frozenset(by), {"dress": "base", "jeans": "bottoms"},
                     {"dress": ["base"], "jeans": ["bottoms"]},
                     {"dress": "onepiece", "jeans": "bottoms"}, by)
    mild = {"lo": 15, "hi": 24, "morning": 17, "feelsLo": 14, "feelsHi": 25,
            "desc": "Clear", "rain": 0, "wind": 2, "midday": 23, "evening": 19,
            "swing": 9, "isRain": False, "isSnow": False, "code": 0}
    picks = {c: None for c in ("inner", "base", "mid", "outer",
                               "bottoms", "footwear", "accessories")}
    picks["bottoms"] = "jeans"
    _, _, covered, _, added = closet_mod._hold_to_the_rules(
        picks, mild, pk.Prefs(), wd, set(), 1)
    assert added == ("base", "dress")
    assert picks["bottoms"] is None, "no trousers under the dress"
    assert "bottoms" in covered, "and that empty slot is covered, not a gap"
