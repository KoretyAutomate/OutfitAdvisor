"""
Trip lists repaired for a cold trip: shoes and trousers that replace dropped summer
legs go with what is packed, and every planned morning can be dressed (pre-push gate
rounds, 2026-11-24). Split from test_packing_round.py at the 600-line ceiling.
"""
import packing
from test_packing_round import days, item


def test_replacement_shoes_are_ones_the_packed_trousers_may_be_worn_with():
    """Sneakers banned with jeans: the loafers replace the sandals, not the sneakers that
    would leave every planned morning without shoes (pre-push gate, 2026-11-24)."""
    sandals = dict(item(60, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(61, "footwear", "sneakers", typ="sneakers"), warmth=2)
    loafers = dict(item(62, "footwear", "loafers", typ="loafers"), warmth=2)
    jeans = dict(item(5, "bottoms", "blue jeans", typ="jeans"), warmth=3)
    pack = [{"id": "itm-00000060", "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "blue jeans", "qty": 1, "why": "x"}]
    ban = [{"kind": "avoid_pair", "a": {"type": "sneakers"}, "b": {"type": "jeans"}}]
    out = packing.top_up([dict(p) for p in pack], [sandals, sneakers, loafers, jeans], 1, ["casual"],
                         band=(-2, 6), user_rules=ban)
    assert [p["id"] for p in out if p["category"] == "footwear"] == [loafers["id"]]
    out = packing.top_up([dict(p) for p in pack], [sandals, sneakers, loafers, jeans], 1, ["casual"], band=(-2, 6))
    assert [p["id"] for p in out if p["category"] == "footwear"] == [sneakers["id"]], "no rule: the first pair"


def test_replacement_shoes_go_with_the_whole_planned_morning():
    """Sneakers banned with the only tee: through top_up, validate_plan and keep_rules
    the planned mornings wear the loafers, never no shoes (pre-push gate, 2026-11-24)."""
    tee = dict(item(80, "base", "white tee", typ="t_shirt"), warmth=2)
    jeans = dict(item(81, "bottoms", "blue jeans", typ="jeans"), warmth=3)
    sandals = dict(item(82, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(83, "footwear", "sneakers", typ="sneakers"), warmth=2)
    loafers = dict(item(84, "footwear", "loafers", typ="loafers"), warmth=2)
    closet = [tee, jeans, sandals, sneakers, loafers]
    ban = [{"kind": "avoid_pair", "a": {"type": "sneakers"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": tee["id"], "category": "base", "label": "tee", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"},
            {"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(-2, 6), user_rules=ban)
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack)
    assert plan and plan[0]["picks"]["footwear"] == loafers["id"], (plan, pack)


def test_replacement_trousers_go_with_the_packed_shoes():
    """Shorts dropped from a cold trip: the chinos replace them, not the jeans banned
    with the only shoes, which left the planned mornings without trousers (pre-push
    gate, 2026-11-24)."""
    shorts = dict(item(90, "bottoms", "shorts", typ="shorts"), warmth=1)
    jeans = dict(item(91, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(92, "bottoms", "chinos", typ="trousers"), warmth=3)
    sneakers = dict(item(93, "footwear", "sneakers", typ="sneakers"), warmth=2)
    tee = dict(item(94, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [shorts, jeans, chinos, sneakers, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "sneakers"}}]
    pack = [{"id": shorts["id"], "category": "bottoms", "label": "shorts", "qty": 1, "why": "x"},
            {"id": sneakers["id"], "category": "footwear", "label": "sneakers", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 3, "why": "x"}]
    pack = packing.top_up(pack, closet, 3, ["casual"], band=(-2, 6), user_rules=ban)
    assert [p["id"] for p in pack if p["category"] == "bottoms"] == [chinos["id"]], pack
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sneakers["id"]}] * 3
    plan = packing.keep_rules(packing.validate_plan(raw, days(3), pack, travel=False), ban, closet, pack)
    assert plan and all(d["picks"]["bottoms"] == chinos["id"] for d in plan), plan


def test_shorts_and_sandals_both_dropped_are_replaced_together():
    """Both summer legs off a one-day cold trip, jeans banned with the only sneakers:
    the sneakers and the chinos go, and the morning is dressed (pre-push gate,
    2026-11-24: jeans were picked first, and no shoes could follow)."""
    shorts = dict(item(100, "bottoms", "shorts", typ="shorts"), warmth=1)
    sandals = dict(item(101, "footwear", "sandals", typ="sandals"), warmth=1)
    jeans = dict(item(102, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(103, "bottoms", "chinos", typ="trousers"), warmth=3)
    sneakers = dict(item(104, "footwear", "sneakers", typ="sneakers"), warmth=2)
    tee = dict(item(105, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [shorts, sandals, jeans, chinos, sneakers, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "sneakers"}}]
    pack = [{"id": shorts["id"], "category": "bottoms", "label": "shorts", "qty": 1, "why": "x"},
            {"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    assert {p["id"] for p in pack if p["category"] in ("bottoms", "footwear")} == {chinos["id"], sneakers["id"]}, pack
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack)
    assert plan and plan[0]["picks"]["bottoms"] == chinos["id"] and plan[0]["picks"]["footwear"] == sneakers["id"], plan


def test_shoes_are_chosen_for_trousers_they_own():
    """Two pairs of shoes, one banned with every pair of trousers they own: the other."""
    sandals = dict(item(110, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(111, "footwear", "sneakers", typ="sneakers"), warmth=2)
    boots = dict(item(112, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(113, "bottoms", "jeans", typ="jeans"), warmth=3)
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "sneakers"}}]
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"}]
    out = packing.top_up(pack, [sandals, sneakers, boots, jeans], 1, ["casual"], band=(3, 8), user_rules=ban)
    assert [p["id"] for p in out if p["category"] == "footwear"] == [boots["id"]], out


def test_two_pairs_of_trousers_each_get_shoes_they_go_with():
    """Sneakers banned with the jeans, boots with the chinos: both pairs are packed, and
    both planned mornings wear shoes (pre-push gate, 2026-11-24)."""
    sandals = dict(item(120, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(121, "footwear", "sneakers", typ="sneakers"), warmth=2)
    boots = dict(item(122, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(123, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(124, "bottoms", "chinos", typ="trousers"), warmth=3)
    tee = dict(item(125, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [sandals, sneakers, boots, jeans, chinos, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "sneakers"}},
           {"kind": "avoid_pair", "a": {"type": "trousers"}, "b": {"type": "boots"}}]
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"},
            {"id": chinos["id"], "category": "bottoms", "label": "chinos", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 2, "why": "x"}]
    pack = packing.top_up(pack, closet, 2, ["casual"], band=(3, 8), user_rules=ban)
    assert {p["id"] for p in pack if p["category"] == "footwear"} == {sneakers["id"], boots["id"]}, pack
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]},
           {"base": tee["id"], "bottoms": chinos["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(2), pack, travel=False), ban, closet, pack)
    assert [d["picks"]["footwear"] for d in plan] == [boots["id"], sneakers["id"]], plan


def test_shoes_kept_on_the_list_are_checked_for_every_packed_garment():
    """Sandals dropped, boots kept but banned with the jeans: loafers join for the jeans
    morning (pre-push gate, 2026-11-24)."""
    sandals = dict(item(130, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(131, "footwear", "boots", typ="boots"), warmth=3)
    loafers = dict(item(132, "footwear", "loafers", typ="loafers"), warmth=2)
    jeans = dict(item(133, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(134, "bottoms", "chinos", typ="trousers"), warmth=3)
    closet = [sandals, boots, loafers, jeans, chinos]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "boots"}}]
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": boots["id"], "category": "footwear", "label": "boots", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"},
            {"id": chinos["id"], "category": "bottoms", "label": "chinos", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, closet, 2, ["casual"], band=(3, 8), user_rules=ban)
    assert {p["id"] for p in pack if p["category"] == "footwear"} == {boots["id"], loafers["id"]}, pack
    raw = [{"bottoms": jeans["id"], "footwear": sandals["id"]}, {"bottoms": chinos["id"], "footwear": boots["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(2), pack, travel=False), ban, closet, pack)
    assert plan[0]["picks"]["footwear"] == loafers["id"], plan


def test_shoes_follow_the_trousers_added_after_them():
    """The jeans join the list after the shoes are chosen; the coverage check runs again
    for the mornings they make (pre-push gate, 2026-11-24)."""
    sandals = dict(item(150, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(151, "footwear", "sneakers", typ="sneakers"), warmth=2)
    loafers = dict(item(152, "footwear", "loafers", typ="loafers"), warmth=2)
    jeans = dict(item(153, "bottoms", "jeans", typ="jeans"), warmth=3)
    tee = dict(item(154, "base", "tee", typ="t_shirt"), warmth=2)
    ban = [{"kind": "avoid_pair", "a": {"type": "sneakers"}, "b": {"type": "jeans"}}]
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": sneakers["id"], "category": "footwear", "label": "sneakers", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, [sandals, sneakers, loafers, jeans, tee], 1, ["casual"], band=(3, 8), user_rules=ban)
    ids = {p["id"] for p in pack}
    assert jeans["id"] in ids and loafers["id"] in ids, pack


def test_replacement_shoes_are_checked_against_whole_mornings():
    """Boots kept but banned with the tee, sneakers banned with the jeans: each garment
    alone has shoes, the tee-and-jeans morning has none, so the loafers join (pre-push
    gate, 2026-11-24)."""
    sandals = dict(item(140, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(141, "footwear", "boots", typ="boots"), warmth=3)
    sneakers = dict(item(142, "footwear", "sneakers", typ="sneakers"), warmth=2)
    loafers = dict(item(143, "footwear", "loafers", typ="loafers"), warmth=2)
    tee = dict(item(144, "base", "tee", typ="t_shirt"), warmth=2)
    jeans = dict(item(145, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [sandals, boots, sneakers, loafers, tee, jeans]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}},
           {"kind": "avoid_pair", "a": {"type": "sneakers"}, "b": {"type": "jeans"}}]
    # Boots and sneakers both stay on the list: each garment has a pair, the morning none.
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": boots["id"], "category": "footwear", "label": "boots", "qty": 1, "why": "x"},
            {"id": sneakers["id"], "category": "footwear", "label": "sneakers", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    assert loafers["id"] in {p["id"] for p in pack if p["category"] == "footwear"}, pack
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack)
    assert plan[0]["picks"]["footwear"] == loafers["id"], plan


def test_a_banned_morning_gets_no_shoes_of_its_own():
    """The tee and the jeans are banned together: no morning wears both, so the boots
    banned with the tee need no second pair beside them."""
    sandals = dict(item(160, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(161, "footwear", "boots", typ="boots"), warmth=3)
    loafers = dict(item(162, "footwear", "loafers", typ="loafers"), warmth=2)
    tee = dict(item(163, "base", "tee", typ="t_shirt"), warmth=2)
    jeans = dict(item(164, "bottoms", "jeans", typ="jeans"), warmth=3)
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}},
           {"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "jeans"}}]
    pack = [{"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"},
            {"id": boots["id"], "category": "footwear", "label": "boots", "qty": 1, "why": "x"},
            {"id": tee["id"], "category": "base", "label": "tee", "qty": 1, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"}]
    out = packing.top_up(pack, [sandals, boots, loafers, tee, jeans], 1, ["casual"], band=(3, 8), user_rules=ban)
    assert [p["id"] for p in out if p["category"] == "footwear"] == [boots["id"]], out


def test_a_planned_morning_may_change_its_shoes_to_keep_its_trousers():
    """Planned shorts and boots; the warm jeans packed in their place are banned with the
    boots: the packed loafers come in too, rather than no trousers (pre-push gate,
    2026-11-24)."""
    shorts = dict(item(170, "bottoms", "shorts", typ="shorts"), warmth=1)
    boots = dict(item(171, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(172, "bottoms", "jeans", typ="jeans"), warmth=3)
    loafers = dict(item(173, "footwear", "loafers", typ="loafers"), warmth=2)
    closet = [shorts, boots, jeans, loafers]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "boots"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (shorts, boots, loafers)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    assert {jeans["id"], loafers["id"]} <= {p["id"] for p in pack}, pack
    raw = [{"bottoms": shorts["id"], "footwear": boots["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack)
    assert plan[0]["picks"] == {**plan[0]["picks"], "bottoms": jeans["id"], "footwear": loafers["id"]}, plan


def test_a_planned_pair_that_goes_is_kept():
    shorts = dict(item(180, "bottoms", "shorts", typ="shorts"), warmth=1)
    boots = dict(item(181, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(182, "bottoms", "jeans", typ="jeans"), warmth=3)
    loafers = dict(item(183, "footwear", "loafers", typ="loafers"), warmth=2)
    closet = [shorts, boots, jeans, loafers]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (shorts, loafers, boots)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8))
    raw = [{"bottoms": shorts["id"], "footwear": boots["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack)
    assert plan[0]["picks"]["footwear"] == boots["id"], "the planned boots stay when nothing rules them out"


def test_a_planned_morning_brings_its_own_shoes_when_nothing_packed_goes():
    """Boots kept on the list but banned with the planned coat: the loafers join the
    list for that morning, checked against all of it (pre-push gate, 2026-11-24)."""
    sandals = dict(item(190, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(191, "footwear", "boots", typ="boots"), warmth=3)
    loafers = dict(item(192, "footwear", "loafers", typ="loafers"), warmth=2)
    coat = dict(item(193, "outer", "wool coat", typ="coat"), warmth=4)
    tee = dict(item(194, "base", "tee", typ="t_shirt"), warmth=2)
    jeans = dict(item(195, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [sandals, boots, loafers, coat, tee, jeans]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "coat"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (sandals, boots, coat, tee, jeans)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": tee["id"], "outer": coat["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == loafers["id"], plan
    assert loafers["id"] in {p["id"] for p in pack}, "and it is on the list"
    fresh = [dict(p) for p in pack if p["id"] != loafers["id"]]
    unbanded = packing.keep_rules(packing.validate_plan(raw, days(1), fresh, travel=False), ban, closet, fresh)
    assert unbanded[0]["picks"]["footwear"] is None, "without the trip's range nothing unpacked is assumed suitable"


def test_a_kept_pair_may_give_way_to_shoes_still_at_home():
    """Planned shorts and boots; the packed jeans are banned with the boots and no other
    shoes are packed: suitable loafers at home complete the morning (pre-push gate,
    2026-11-24)."""
    shorts = dict(item(200, "bottoms", "shorts", typ="shorts"), warmth=1)
    boots = dict(item(201, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(202, "bottoms", "jeans", typ="jeans"), warmth=3)
    loafers = dict(item(203, "footwear", "loafers", typ="loafers"), warmth=2)
    closet = [shorts, boots, jeans, loafers]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "boots"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (boots, jeans)]
    raw = [{"bottoms": shorts["id"], "footwear": boots["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["bottoms"] == jeans["id"] and plan[0]["picks"]["footwear"] == loafers["id"], plan
    assert loafers["id"] in {p["id"] for p in pack}


def test_a_morning_of_only_summer_legs_is_refilled_not_dropped():
    """A planned morning of shorts and sandals alone: both leave the list, the
    replacements are packed, and the morning is kept and dressed (pre-push gate,
    2026-11-24)."""
    shorts = dict(item(210, "bottoms", "shorts", typ="shorts"), warmth=1)
    sandals = dict(item(211, "footwear", "sandals", typ="sandals"), warmth=1)
    jeans = dict(item(212, "bottoms", "jeans", typ="jeans"), warmth=3)
    sneakers = dict(item(213, "footwear", "sneakers", typ="sneakers"), warmth=2)
    closet = [shorts, sandals, jeans, sneakers]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (shorts, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8))
    raw = [{"bottoms": shorts["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8))
    assert len(plan) == 1 and plan[0]["picks"]["bottoms"] == jeans["id"] \
        and plan[0]["picks"]["footwear"] == sneakers["id"], plan


def test_socks_never_replace_the_shoes():
    """Sandals dropped from a cold trip: the boots replace them, never the socks filed
    under footwear, though the socks stay packable (pre-push gate, 2026-11-24)."""
    socks = dict(item(220, "footwear", "wool socks", typ="socks"), warmth=3)
    sandals = dict(item(221, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(222, "footwear", "boots", typ="boots"), warmth=3)
    jeans = dict(item(223, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [socks, sandals, boots, jeans]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (socks, sandals, jeans)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8))
    assert boots["id"] in {p["id"] for p in pack} and socks["id"] in {p["id"] for p in pack}, pack
    raw = [{"bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"], plan
    assert [i["id"] for i in packing.wearable_for(closet, "footwear", 3, 8)] == [boots["id"]]


def test_thin_socks_stay_on_a_cold_trip_list():
    """Cotton socks are worn inside the boots: the leg floor never takes them off the
    list (pre-push gate, 2026-11-24)."""
    socks = dict(item(230, "footwear", "cotton socks", typ="socks"), warmth=1)
    boots = dict(item(231, "footwear", "boots", typ="boots"), warmth=3)
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (socks, boots)]
    assert packing.too_thin(pack, [socks, boots], 3, 8) == []
    out = packing.top_up([dict(p) for p in pack], [socks, boots], 1, ["casual"], band=(3, 8))
    assert socks["id"] in {p["id"] for p in out}


def test_underwear_still_counts_for_the_trip():
    """Briefs never fill an outfit slot, but they pack, and count, as underwear."""
    briefs = dict(item(240, "inner", "briefs", count=8, typ="briefs"), group="underwear")
    assert [i["id"] for i in packing.wearable_for([briefs], "inner", 3, 8)] == [briefs["id"]]


def test_a_planned_morning_may_change_its_top_to_wear_the_replacement_shoes():
    """Tee, oxford, jeans and sandals packed; boots replace the sandals but are banned
    with tees: the morning wears the oxford with the boots (pre-push gate, 2026-11-24)."""
    tee = dict(item(250, "base", "tee", typ="t_shirt"), warmth=2)
    oxford = dict(item(251, "base", "oxford", typ="shirt"), warmth=2)
    jeans = dict(item(252, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(253, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(254, "footwear", "boots", typ="boots"), warmth=3)
    closet = [tee, oxford, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, oxford, jeans, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and plan[0]["picks"]["base"] == oxford["id"], plan


def test_a_changed_top_is_never_a_dress_over_the_trousers():
    """Sneakers replace sandals but are banned with the planned tee; a dress is packed:
    the morning never becomes the dress with the jeans (pre-push gate, 2026-11-24)."""
    tee = dict(item(260, "base", "tee", typ="t_shirt"), warmth=2)
    dress = dict(item(261, "base", "wool dress", typ="dress"), group="onepiece", warmth=3)
    jeans = dict(item(262, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(263, "footwear", "sandals", typ="sandals"), warmth=1)
    sneakers = dict(item(264, "footwear", "sneakers", typ="sneakers"), warmth=2)
    closet = [tee, dress, jeans, sandals, sneakers]
    ban = [{"kind": "avoid_pair", "a": {"type": "sneakers"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, dress, jeans, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    p = plan[0]["picks"]
    assert not (p["base"] == dress["id"] and p.get("bottoms")), p


def test_a_planned_belt_comes_off_for_the_only_boots():
    """Sandals dropped; the packed black boots are banned with the planned brown belt:
    the belt comes off rather than the morning going barefoot (pre-push gate, 2026-11-24)."""
    belt = dict(item(270, "accessories", "brown belt", typ="belt"), group="accessories", colors=["brown"])
    sandals = dict(item(271, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(272, "footwear", "black boots", typ="boots"), warmth=3, colors=["black"])
    jeans = dict(item(273, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [belt, sandals, boots, jeans]
    ban = [{"kind": "avoid_pair", "a": {"type": "belt", "color": "brown"}, "b": {"type": "boots", "color": "black"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (belt, sandals, boots, jeans)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    slot = belt["category"]
    raw = [{"bottoms": jeans["id"], "footwear": sandals["id"], slot: belt["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and not plan[0]["picks"].get(slot), plan


def test_a_dress_may_swap_for_another_dress_to_wear_the_boots():
    """Red and blue wool dresses, boots banned only with the red one: the planned red
    dress swaps for the blue rather than going barefoot (pre-push gate, 2026-11-24)."""
    red = dict(item(280, "base", "red wool dress", typ="dress"), group="onepiece", warmth=3, colors=["red"])
    blue = dict(item(281, "base", "blue wool dress", typ="dress"), group="onepiece", warmth=3, colors=["blue"])
    sandals = dict(item(282, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(283, "footwear", "boots", typ="boots"), warmth=3)
    closet = [red, blue, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "dress", "color": "red"}, "b": {"type": "boots"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (red, blue, sandals, boots)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": red["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["base"] == blue["id"] and plan[0]["picks"]["footwear"] == boots["id"], plan


def test_replacement_shoes_keep_the_wet_out():
    """Sandals dropped: waterproof boots replace them before mesh sneakers (pre-push
    gate, 2026-11-24: mesh came on a rainy cold trip while the boots stayed home)."""
    sandals = dict(item(290, "footwear", "sandals", typ="sandals"), warmth=1, waterproof=True)
    mesh = dict(item(291, "footwear", "mesh sneakers", typ="sneakers"), warmth=2, group="footwear", material="mesh")
    boots = dict(item(292, "footwear", "rain boots", typ="boots"), warmth=3, group="footwear", waterproof=True)
    jeans = dict(item(293, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [sandals, mesh, boots, jeans]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (sandals, jeans)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8))
    assert [p["id"] for p in pack if p["category"] == "footwear"] == [boots["id"]], pack


def test_a_top_from_home_lets_the_morning_wear_the_boots():
    """Three tees packed, boots banned with tees, an oxford at home: the oxford joins the
    list for the morning rather than it going barefoot (pre-push gate, 2026-11-24)."""
    tee = dict(item(300, "base", "tee", count=3, typ="t_shirt"), warmth=2)
    oxford = dict(item(301, "base", "oxford", typ="shirt"), warmth=2)
    jeans = dict(item(302, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(303, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(304, "footwear", "boots", typ="boots"), warmth=3)
    closet = [tee, oxford, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": tee["id"], "category": "base", "label": "tee", "qty": 3, "why": "x"},
            {"id": jeans["id"], "category": "bottoms", "label": "jeans", "qty": 1, "why": "x"},
            {"id": sandals["id"], "category": "footwear", "label": "sandals", "qty": 1, "why": "x"}]
    pack = packing.top_up(pack, closet, 2, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and plan[0]["picks"]["base"] == oxford["id"], plan
    assert oxford["id"] in {p["id"] for p in pack}


def test_a_planned_undershirt_may_change_for_the_boots():
    """Boots banned with the planned white undershirt; a grey one is packed: the morning
    swaps undershirts rather than going barefoot (pre-push gate, 2026-11-24)."""
    white = dict(item(310, "inner", "white undershirt", typ="undershirt"), group="underwear", colors=["white"])
    grey = dict(item(311, "inner", "grey undershirt", typ="undershirt"), group="underwear", colors=["grey"])
    tee = dict(item(312, "base", "tee", typ="t_shirt"), warmth=2)
    jeans = dict(item(313, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(314, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(315, "footwear", "boots", typ="boots"), warmth=3)
    closet = [white, grey, tee, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "undershirt", "color": "white"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (white, grey, tee, jeans, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"inner": white["id"], "base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and plan[0]["picks"]["inner"] == grey["id"], plan


def test_the_refill_stays_fast_when_nothing_can_fill_it():
    """A big wardrobe where every pair of boots is banned with every pair of trousers:
    the repair gives up quickly rather than walking every top and layer (pre-push
    gate, 2026-11-24: nine seconds, blocking the server)."""
    import time
    tops = [dict(item(400 + k, "base", f"top {k}", typ="shirt"), warmth=2) for k in range(30)]
    mids = [dict(item(450 + k, "mid", f"knit {k}", typ="sweater"), warmth=3) for k in range(20)]
    outers = [dict(item(480 + k, "outer", f"coat {k}", typ="coat"), warmth=4) for k in range(15)]
    legs = [dict(item(500 + k, "bottoms", f"trousers {k}", typ="trousers"), warmth=3) for k in range(15)]
    boots = [dict(item(520 + k, "footwear", f"boots {k}", typ="boots"), warmth=3) for k in range(14)]
    sandals = dict(item(540, "footwear", "sandals", typ="sandals"), warmth=1)
    closet = [*tops, *mids, *outers, *legs, *boots, sandals]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "trousers"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"} for i in closet]
    raw = [{"base": tops[0]["id"], "mid": mids[0]["id"], "outer": outers[0]["id"], "bottoms": legs[0]["id"],
            "footwear": sandals["id"]}]
    plan = packing.validate_plan(raw, days(1), [p for p in pack if p["id"] != sandals["id"]], travel=False)
    t0 = time.monotonic()
    out = packing.keep_rules(plan, ban, closet, [p for p in pack if p["id"] != sandals["id"]], (3, 8))
    assert time.monotonic() - t0 < 1.0
    assert out and out[0]["picks"]["footwear"] is None and out[0]["picks"]["bottoms"] == legs[0]["id"]


def test_a_cut_branch_never_ends_the_search():
    """With the planned tee only one of two refilled slots can be filled; with the
    oxford, tried later, both can. The cut of a worse branch must not stop the walk
    before the oxford is tried."""
    names = ["base", "bottoms", "footwear"]
    by = {"tee": {"type": "t_shirt"}, "ox": {"type": "shirt"}, "j": {"type": "jeans"}, "b": {"type": "boots"}}
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    options = [["tee", "ox"], ["j", None], ["b", None]]
    got = packing._search(names, options, ({}, 1), ban, by)
    assert got == {"base": "ox", "bottoms": "j", "footwear": "b"}, got


def test_a_sundress_never_replaces_a_wool_dress_on_a_cold_trip():
    """The wool dress is banned with the replacement boots; a sundress at home is too
    thin for 3-8C, so it is never brought in (pre-push gate, 2026-11-24)."""
    wool = dict(item(320, "base", "wool dress", typ="dress"), group="onepiece", warmth=3)
    sun = dict(item(321, "base", "sundress", typ="dress"), group="onepiece", warmth=1)
    sandals = dict(item(322, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(323, "footwear", "boots", typ="boots"), warmth=3)
    closet = [wool, sun, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "dress"}, "b": {"type": "boots"}}]
    assert not packing.suits(sun, "base", 3, 8) and packing.suits(wool, "base", 3, 8)
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (wool, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": wool["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["base"] != sun["id"], plan


def test_a_dry_pair_joins_when_only_mesh_is_left():
    """Waterproof sandals dropped, mesh sneakers already packed, waterproof boots at
    home: the boots join too (pre-push gate, 2026-11-24)."""
    sandals = dict(item(330, "footwear", "sandals", typ="sandals"), warmth=1, waterproof=True)
    mesh = dict(item(331, "footwear", "mesh sneakers", typ="sneakers"), warmth=2, group="footwear", material="mesh")
    boots = dict(item(332, "footwear", "rain boots", typ="boots"), warmth=3, group="footwear", waterproof=True)
    jeans = dict(item(333, "bottoms", "jeans", typ="jeans"), warmth=3)
    closet = [sandals, mesh, boots, jeans]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (sandals, mesh, jeans)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8))
    assert boots["id"] in {p["id"] for p in pack}, pack
