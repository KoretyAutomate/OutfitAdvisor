"""
A planned trip morning repaired around replacement shoes: which garments may change,
come off or come from home, judged by the daily advice's own check (pre-push gate
rounds, 2026-11-24). Split from test_packing_shoes.py at the 600-line ceiling.
"""
import packing
from test_packing_round import days, item


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
    names = ["bottoms", "footwear", "base"]   # the refilled slots first
    by = {"tee": {"type": "t_shirt"}, "ox": {"type": "shirt"}, "j": {"type": "jeans"}, "b": {"type": "boots"}}
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    options = [["j", None], ["b", None], ["tee", "ox"]]
    got = packing._search(names, options, ({}, 2, {}, (None, None)), ban, by)
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


def test_a_packed_sundress_never_swaps_in_on_a_cold_trip():
    """Wool dress and sundress both packed; the wool one is banned with the boots: the
    packed sundress is too thin for 3-8C and never swaps in (pre-push gate, 2026-11-24)."""
    wool = dict(item(340, "base", "wool dress", typ="dress"), group="onepiece", warmth=3, colors=["grey"])
    sun = dict(item(341, "base", "sundress", typ="dress"), group="onepiece", warmth=1, colors=["yellow"])
    sandals = dict(item(342, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(343, "footwear", "boots", typ="boots"), warmth=3)
    closet = [wool, sun, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "dress", "color": "grey"}, "b": {"type": "boots"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (wool, sun, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"base": wool["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["base"] != sun["id"], plan


def test_the_undershirt_may_come_off_for_the_boots():
    """Boots banned with the only undershirt; shirt, coat and jeans are warm enough:
    the undershirt comes off rather than the morning going barefoot (pre-push gate,
    2026-11-24)."""
    under = dict(item(350, "inner", "undershirt", typ="undershirt"), group="underwear")
    shirt = dict(item(351, "base", "oxford", typ="shirt"), warmth=2)
    coat = dict(item(352, "outer", "wool coat", typ="coat"), group="outerwear", warmth=4)
    jeans = dict(item(353, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(354, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(355, "footwear", "boots", typ="boots"), warmth=3)
    closet = [under, shirt, coat, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "undershirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (under, shirt, coat, jeans, sandals)]
    pack = packing.top_up(pack, closet, 1, ["casual"], band=(3, 8), user_rules=ban)
    raw = [{"inner": under["id"], "base": shirt["id"], "outer": coat["id"], "bottoms": jeans["id"],
            "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and not plan[0]["picks"].get("inner"), plan


def test_packed_dry_shoes_come_before_packed_mesh():
    by = {"m": {"group": "footwear", "material": "mesh"}, "b": {"group": "footwear"}}
    pack = [{"id": "m", "category": "footwear"}, {"id": "b", "category": "footwear"}]
    got = packing._refill({"_refill": ["footwear"]}, {}, (pack, {}, None, None), [], by, 0)
    assert got == {"footwear": "b"}, got


def test_a_swapped_top_never_clashes_its_sleeves():
    """Boots banned with the tee; the only other top is long-sleeved and the planned knit
    short-sleeved: no long sleeves under the short knit, so no swap (pre-push gate,
    2026-11-24)."""
    tee = dict(item(360, "base", "tee", typ="t_shirt"), warmth=2, sleeve="short")
    longs = dict(item(361, "base", "long shirt", typ="shirt"), warmth=2, sleeve="long")
    knit = dict(item(362, "mid", "short knit", typ="sweater"), warmth=3, sleeve="short")
    jeans = dict(item(363, "bottoms", "jeans", typ="jeans"), warmth=3)
    boots = dict(item(364, "footwear", "boots", typ="boots"), warmth=3)
    by = {i["id"]: i for i in (tee, longs, knit, jeans, boots)}
    assert packing.sleeves.sleeve_clashes({"base": longs["id"], "mid": knit["id"]}, by), "the fixture clashes"
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"]} for i in (tee, longs, knit, jeans, boots)]
    picks = {"base": tee["id"], "mid": knit["id"], "bottoms": jeans["id"], "footwear": None}
    got = packing._refill({"_refill": ["footwear"]}, picks, (pack, {}, None, None), ban, by, 0)
    assert got.get("base") != longs["id"] or got.get("mid") != knit["id"], got


def test_a_swapped_coat_stays_warm_enough():
    """3-8C: boots banned with the planned grey coat; a thin jacket and a warm black
    coat are packed: the black coat comes, never the thin jacket (pre-push gate,
    2026-11-24)."""
    tee = dict(item(370, "base", "tee", typ="t_shirt"), warmth=2)
    grey = dict(item(371, "outer", "grey coat", typ="coat"), group="outerwear", warmth=4, colors=["grey"])
    thin = dict(item(372, "outer", "thin jacket", typ="jacket"), group="outerwear", warmth=1, colors=["navy"])
    black = dict(item(373, "outer", "black coat", typ="coat"), group="outerwear", warmth=4, colors=["black"])
    jeans = dict(item(374, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(375, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(376, "footwear", "boots", typ="boots"), warmth=3)
    closet = [tee, grey, thin, black, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "coat", "color": "grey"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, grey, thin, black, jeans, boots)]
    raw = [{"base": tee["id"], "outer": grey["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"] and plan[0]["picks"]["outer"] == black["id"], plan


def test_a_plan_that_already_clashes_its_sleeves_still_gets_its_shoes():
    """The planned long shirt under a short knit already clashes: the boots still come
    for the dropped sandals (pre-push gate, 2026-11-24)."""
    longs = dict(item(380, "base", "long shirt", typ="shirt"), warmth=2, sleeve="long")
    knit = dict(item(381, "mid", "short knit", typ="sweater"), warmth=3, sleeve="short")
    jeans = dict(item(382, "bottoms", "jeans", typ="jeans"), warmth=3)
    boots = dict(item(383, "footwear", "boots", typ="boots"), warmth=3)
    sandals = dict(item(384, "footwear", "sandals", typ="sandals"), warmth=1)
    closet = [longs, knit, jeans, boots, sandals]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (longs, knit, jeans, boots)]
    raw = [{"base": longs["id"], "mid": knit["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8))
    assert plan[0]["picks"]["footwear"] == boots["id"], plan


def test_a_swapped_coat_is_judged_on_its_own_scale():
    """An absolute warmth-4 coat is never swapped for a home-scale warmth-4 jacket that
    answers to a milder day (pre-push gate, 2026-11-24)."""
    coat = {"warmth": 4, "group": "outerwear"}
    home = {"warmth": 4, "group": "outerwear", "warmthScale": "home", "warmthAnchors": [0.7, 12.9, 25.6]}
    by = {"c": coat, "h": home, "t": {"warmth": 2}}
    names, options = ["outer"], [["h", "c"]]
    got = packing._search(names, options, ({"base": "t"}, 0, {"base": "t", "outer": "c"}, ((3, 8), None)), [], by)
    assert packing.scale.garment_temp(home) > packing.scale.garment_temp(coat), "the fixture: the jacket is milder"
    assert got == {"outer": "c"}, got


def test_dry_shoes_from_home_come_before_packed_mesh():
    """Packed mesh and dry loafers at home: the loafers fill a refilled slot first."""
    by = {"m": {"group": "footwear", "material": "mesh"}, "l": {"group": "footwear"}}
    got = packing._refill({"_refill": ["footwear"]}, {}, ([{"id": "m", "category": "footwear"}], {"footwear": ["l"]},
                                                          None, None), [], by, 0)
    assert got == {"footwear": "l"}, got


def test_a_swap_to_a_tee_never_keeps_the_undershirt_under_it():
    """Boots banned with the planned shirt; a packed tee is the other top: the undershirt
    comes off rather than going under the tee (pre-push gate, 2026-11-24)."""
    under = {"group": "underwear", "type": "undershirt"}
    by = {"u": under, "s": {"type": "shirt"}, "t": {"type": "t_shirt"}, "b": {"type": "boots"}}
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "shirt"}}]
    names, options = ["footwear", "base", "inner"], [["b", None], ["s", "t"], ["u", None]]
    got = packing._search(names, options, ({}, 1, {"inner": "u", "base": "s"}, (None, None)), ban, by)
    assert got == {"base": "t", "inner": None, "footwear": "b"}, got


def test_a_thermal_that_comes_off_is_made_up_with_a_packed_sweater():
    """8-10C: boots banned with the thermal; the shirt alone is colder than the plan, so
    the packed sweater goes on (pre-push gate, 2026-11-24)."""
    thermal = dict(item(390, "inner", "thermal", typ="thermal"), group="underwear", warmth=3)
    shirt = dict(item(391, "base", "oxford", typ="shirt"), warmth=2)
    sweater = dict(item(392, "mid", "sweater", typ="sweater"), warmth=3)
    jeans = dict(item(393, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(394, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(395, "footwear", "boots", typ="boots"), warmth=3)
    closet = [thermal, shirt, sweater, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "thermal"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (thermal, shirt, sweater, jeans, boots)]
    raw = [{"inner": thermal["id"], "base": shirt["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 10))
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and not p.get("inner") and p.get("mid") == sweater["id"], p


def test_a_warm_dress_may_stand_in_for_dropped_shorts():
    """8-11C: tee, shorts, sneakers planned; the shorts leave and only a wool dress can
    dress the legs: the morning becomes the dress, trousers left empty (pre-push gate,
    2026-11-24)."""
    tee = dict(item(410, "base", "tee", typ="t_shirt"), warmth=2)
    shorts = dict(item(411, "bottoms", "shorts", typ="shorts"), warmth=1)
    dress = dict(item(412, "base", "wool dress", typ="dress"), group="onepiece", warmth=3)
    sneakers = dict(item(413, "footwear", "sneakers", typ="sneakers"), warmth=2)
    closet = [tee, shorts, dress, sneakers]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, dress, sneakers)]
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sneakers["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (8, 11))
    p = plan[0]["picks"]
    assert p["base"] == dress["id"] and not p.get("bottoms") and p["footwear"] == sneakers["id"], p


def test_a_jacket_may_come_off_for_the_boots_when_the_sweater_is_enough():
    """8-11C: boots banned with the planned jacket; the sweater under it is warm enough:
    the jacket comes off (pre-push gate, 2026-11-24)."""
    sweater = dict(item(420, "base", "sweater", typ="sweater"), warmth=3)
    jacket = dict(item(421, "outer", "jacket", typ="jacket"), group="outerwear", warmth=2)
    jeans = dict(item(422, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(423, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(424, "footwear", "boots", typ="boots"), warmth=3)
    closet = [sweater, jacket, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "jacket"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (sweater, jacket, jeans, boots)]
    raw = [{"base": sweater["id"], "outer": jacket["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 11))
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and not p.get("outer"), p


def test_a_needed_jacket_never_comes_off_for_the_boots():
    """2-5C with a thin shirt under the jacket: taking the jacket off would be too cold,
    so the boots banned with it are not worn (the daily advice's judge decides)."""
    shirt = dict(item(430, "base", "thin shirt", typ="shirt"), warmth=1)
    jacket = dict(item(431, "outer", "puffer", typ="puffer"), group="outerwear", warmth=5)
    jeans = dict(item(432, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(433, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(434, "footwear", "boots", typ="boots"), warmth=3)
    closet = [shirt, jacket, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "puffer"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (shirt, jacket, jeans, boots)]
    raw = [{"base": shirt["id"], "outer": jacket["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (2, 5))
    assert plan[0]["picks"].get("outer") == jacket["id"], plan


def test_the_judge_never_lets_a_dress_go_over_trousers():
    """Shorts dropped; the packed jeans are banned with the planned tee and a wool dress
    is packed: the dress may come, but never over the jeans (check's one-piece rule)."""
    tee = dict(item(440, "base", "tee", typ="t_shirt"), warmth=2)
    shorts = dict(item(441, "bottoms", "shorts", typ="shorts"), warmth=1)
    dress = dict(item(442, "base", "wool dress", typ="dress"), group="onepiece", warmth=3)
    jeans = dict(item(443, "bottoms", "jeans", typ="jeans"), warmth=3)
    sneakers = dict(item(444, "footwear", "sneakers", typ="sneakers"), warmth=2)
    closet = [tee, shorts, dress, jeans, sneakers]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, dress, jeans, sneakers)]
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sneakers["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 11))
    p = plan[0]["picks"]
    assert not (p["base"] == dress["id"] and p.get("bottoms")), p


def test_each_slot_is_searched_once():
    """A planned undershirt, knit and coat are kept slots that may also come off: each
    is searched once, so the budget reaches the chinos that go with the boots
    (pre-push gate, 2026-11-24: duplicated slots ran the search out first)."""
    under = dict(item(450, "inner", "undershirt", typ="undershirt"), group="underwear")
    tees = [dict(item(451 + k, "base", f"shirt {k}", typ="shirt"), warmth=2) for k in range(3)]
    knits = [dict(item(455 + k, "mid", f"knit {k}", typ="sweater"), warmth=3) for k in range(3)]
    coats = [dict(item(460 + k, "outer", f"coat {k}", typ="coat"), group="outerwear", warmth=4) for k in range(3)]
    jeans = dict(item(465, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(466, "bottoms", "chinos", typ="trousers"), warmth=3)
    sandals = dict(item(467, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(468, "footwear", "boots", typ="boots"), warmth=3)
    closet = [under, *tees, *knits, *coats, jeans, chinos, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "jeans"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in closet if i is not sandals]
    raw = [{"inner": under["id"], "base": tees[0]["id"], "mid": knits[0]["id"], "outer": coats[0]["id"],
            "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8))
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and p["bottoms"] == chinos["id"], p


def test_a_snowy_trip_repair_keeps_the_feet_dry():
    """Snow on a 3-8C trip: dropped waterproof sandals are replaced by the waterproof
    boots, never the plain loafers (pre-push gate, 2026-11-24)."""
    sandals = dict(item(470, "footwear", "sandals", typ="sandals"), warmth=1, waterproof=True)
    loafers = dict(item(471, "footwear", "loafers", typ="loafers"), warmth=2, group="footwear")
    boots = dict(item(472, "footwear", "snow boots", typ="boots"), warmth=3, group="footwear", waterproof=True)
    jeans = dict(item(473, "bottoms", "jeans", typ="jeans"), warmth=3)
    tee = dict(item(474, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [sandals, loafers, boots, jeans, tee]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (loafers, jeans, tee)]
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8),
                              {"isSnow": True})
    assert plan[0]["picks"]["footwear"] == boots["id"], plan


def test_dropped_sandals_are_no_cooler_alternative_to_the_boots():
    """3-8C: warmth-5 boots replace warmth-1 sandals; the dropped sandals do not make the
    boots 'too warm' (pre-push gate, 2026-11-24)."""
    absolute = {"warmthScale": "absolute", "warmthAnchors": None}
    sandals = dict(item(480, "footwear", "sandals", typ="sandals"), warmth=1, **absolute)
    boots = dict(item(481, "footwear", "fur boots", typ="boots"), warmth=5, **absolute)
    jeans = dict(item(482, "bottoms", "jeans", typ="jeans"), warmth=3)
    tee = dict(item(483, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [sandals, boots, jeans, tee]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (boots, jeans, tee)]
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8), {})
    assert plan[0]["picks"]["footwear"] == boots["id"], plan


def test_one_of_two_refilled_slots_is_better_than_none():
    """Shorts and sandals dropped; the only warm trousers and boots are banned together:
    one of them is worn rather than neither (pre-push gate, 2026-11-24)."""
    shorts = dict(item(490, "bottoms", "shorts", typ="shorts"), warmth=1)
    sandals = dict(item(491, "footwear", "sandals", typ="sandals"), warmth=1)
    jeans = dict(item(492, "bottoms", "jeans", typ="jeans"), warmth=3)
    boots = dict(item(493, "footwear", "boots", typ="boots"), warmth=3)
    tee = dict(item(494, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [shorts, sandals, jeans, boots, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "boots"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (jeans, boots, tee)]
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8), {})
    p = plan[0]["picks"]
    assert bool(p.get("bottoms")) != bool(p.get("footwear")), p


def test_packed_socks_are_no_cooler_shoes_for_the_judge():
    """Cotton socks packed beside warmth-5 boots: the socks do not make the boots 'too
    warm' (pre-push gate, 2026-11-24)."""
    absolute = {"warmthScale": "absolute", "warmthAnchors": None}
    sandals = dict(item(500, "footwear", "sandals", typ="sandals"), warmth=1, **absolute)
    boots = dict(item(501, "footwear", "fur boots", typ="boots"), warmth=5, **absolute)
    socks = dict(item(502, "footwear", "cotton socks", typ="socks"), warmth=1, **absolute)
    jeans = dict(item(503, "bottoms", "jeans", typ="jeans"), warmth=3)
    tee = dict(item(504, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [sandals, boots, socks, jeans, tee]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (boots, socks, jeans, tee)]
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), [], closet, pack, (3, 8), {})
    assert plan[0]["picks"]["footwear"] == boots["id"], plan


def test_a_big_closet_still_finds_the_one_top_that_goes():
    """20 knits, 15 coats and 10 pairs of boots packed, every boot banned with the planned
    tee: the packed oxford is found within budget (pre-push gate, 2026-11-24)."""
    knits = [dict(item(600 + k, "mid", f"knit {k}", typ="sweater"), warmth=3) for k in range(20)]
    coats = [dict(item(630 + k, "outer", f"coat {k}", typ="coat"), group="outerwear", warmth=4) for k in range(15)]
    boots = [dict(item(650 + k, "footwear", f"boots {k}", typ="boots"), warmth=3) for k in range(10)]
    tee = dict(item(670, "base", "tee", typ="t_shirt"), warmth=2)
    oxford = dict(item(671, "base", "oxford", typ="shirt"), warmth=2)
    jeans = dict(item(672, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(673, "footwear", "sandals", typ="sandals"), warmth=1)
    closet = [*knits, *coats, *boots, tee, oxford, jeans, sandals]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in closet if i is not sandals]
    raw = [{"base": tee["id"], "mid": knits[0]["id"], "outer": coats[0]["id"], "bottoms": jeans["id"],
            "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8), {})
    p = plan[0]["picks"]
    assert p["footwear"] in {b["id"] for b in boots} and p["base"] == oxford["id"], p


def test_a_wider_search_out_of_budget_never_loses_the_first_answer(monkeypatch):
    """The first pass fills the trousers; a wider pass that runs out of budget with
    nothing must not replace it (pre-push gate, 2026-11-24)."""
    real = packing._search
    calls = []

    def search(names, options, base, rules_, by):
        calls.append(1)
        return real(names, options, base, rules_, by) if len(calls) == 1 else {}
    monkeypatch.setattr(packing, "_search", search)
    shorts = dict(item(680, "bottoms", "shorts", typ="shorts"), warmth=1)
    sandals = dict(item(681, "footwear", "sandals", typ="sandals"), warmth=1)
    jeans = dict(item(682, "bottoms", "jeans", typ="jeans"), warmth=3)
    boots = dict(item(683, "footwear", "boots", typ="boots"), warmth=3)
    tee = dict(item(684, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [shorts, sandals, jeans, boots, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (jeans, boots, tee)]
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8), {})
    assert len(calls) == 2 and plan[0]["picks"]["bottoms"] == jeans["id"], (calls, plan)
