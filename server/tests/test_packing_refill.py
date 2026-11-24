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
    belt = dict(item(270, "belt", "brown belt", typ="belt"), group="accessories", colors=["brown"])
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
