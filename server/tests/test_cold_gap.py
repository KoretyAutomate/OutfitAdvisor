"""The cold-morning gap: nothing owned is warm enough, told apart from a styling problem."""
import layers


def test_nothing_warm_owned_is_a_gap():
    import closet as cl
    tee = {"id": "t", "label": "tee", "category": "base", "roles": ["base"], "warmth": 1,
           "colors": ["white"], "formality": ["casual"]}
    parka = {"id": "p", "label": "parka", "category": "outer", "roles": ["outer"], "warmth": 4,
             "colors": ["black"], "formality": ["casual"]}
    wd = cl.pk._index([tee])
    assert layers.too_cold_for_outfit({"base": "t"}, wd, 3.0, [])
    wd2 = cl.pk._index([tee, parka])
    assert not layers.too_cold_for_outfit({"base": "t"}, wd2, 3.0, [])      # owned, so no gap
    assert not layers.too_cold_for_outfit({"base": "t"}, wd, 25.0, [])      # warm day


def test_no_top_at_all_is_not_a_cold_gap():
    import closet as cl
    shoes = {"id": "f", "label": "sneakers", "category": "footwear", "roles": ["footwear"],
             "warmth": 1, "colors": ["white"], "formality": ["casual"]}
    assert not layers.too_cold_for_outfit({"footwear": "f"}, cl.pk._index([shoes]), 3.0, [])


def test_too_heavy_to_wear_does_not_hide_the_gap():
    import closet as cl
    tee = {"id": "t", "label": "tee", "category": "base", "roles": ["base"], "warmth": 1,
           "colors": ["white"], "formality": ["casual"]}
    coat = {"id": "p", "label": "parka", "category": "outer", "roles": ["outer"], "warmth": 5,
            "colors": ["black"], "formality": ["casual"]}
    assert layers.too_cold_for_outfit({"base": "t"}, cl.pk._index([tee, coat]), 14.0, [])


def test_cold_gap_is_its_own_word_not_outer():
    import closet as cl
    tee = {"id": "t", "label": "tee", "category": "base", "roles": ["base"], "warmth": 1,
           "colors": ["white"], "formality": ["casual"]}
    wd = cl.pk._index([tee])
    assert cl._with_cold_gap([], {"base": "t"}, wd, 3.0, [], 3.0) == ["warmth"]
    assert cl._with_cold_gap(["outer"], {"base": "t"}, wd, 3.0, [], 3.0) == ["outer", "warmth"]
    assert cl._with_cold_gap([], {"base": "t"}, wd, 25.0, [], 25.0) == []


def test_a_forbidden_warm_garment_does_not_hide_the_gap():
    import closet as cl
    tee = {"id": "t", "label": "tee", "category": "base", "roles": ["base"], "warmth": 1,
           "colors": ["white"], "formality": ["casual"]}
    parka = {"id": "p", "label": "parka", "category": "outer", "roles": ["outer"], "warmth": 4,
             "colors": ["black"], "formality": ["casual"], "type": "parka"}
    wd = cl.pk._index([tee, parka])
    rule = [{"kind": "avoid_item", "a": {"type": "parka"}}]
    assert not layers.too_cold_for_outfit({"base": "t"}, wd, 3.0, [])
    assert layers.too_cold_for_outfit({"base": "t"}, wd, 3.0, rule)


def test_old_app_warmth_gap_reaches_shopping_as_outer():
    from schemas import Gap
    assert Gap(slot="warmth", n=1, loC=0, hiC=5).slot == "outer"


def test_a_pairing_ban_is_not_a_missing_garment():
    import closet as cl
    tee = {"id": "t", "label": "tee", "category": "base", "roles": ["base"], "warmth": 1,
           "colors": ["white"], "formality": ["casual"]}
    parka = {"id": "p", "label": "parka", "category": "outer", "roles": ["outer"], "warmth": 4,
             "colors": ["black"], "formality": ["casual"], "type": "parka"}
    rule = [{"kind": "avoid_item", "a": {"type": "parka"}}]
    wd = cl.pk._index([tee, parka])
    assert layers.too_cold_for_outfit({"base": "t"}, wd, 3.0, rule)       # banned outright
    assert not layers.too_cold_for_outfit({"base": "t"}, wd, 3.0, [])     # merely unused
