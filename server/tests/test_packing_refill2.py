"""
The planned-morning refill, continued: what may come off or be brought in, judged
by the daily advice's own check, and what the search prefers (pre-push gate rounds,
2026-11-24). Split from test_packing_refill.py at the 600-line ceiling.
"""
import packing
from test_packing_round import days, item


def _p(*items_):
    return [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"} for i in items_]


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


def test_a_cardigan_may_take_the_place_of_a_tee_banned_with_the_boots():
    """8-11C: tee, cardigan and jeans packed, boots banned with tees: the morning wears the
    cardigan as its top with the boots (pre-push gate, 2026-11-24)."""
    tee = dict(item(690, "base", "tee", typ="t_shirt"), warmth=2)
    cardi = dict(item(691, "mid", "cardigan", typ="cardigan"), warmth=3)
    jeans = dict(item(692, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(693, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(694, "footwear", "boots", typ="boots"), warmth=3)
    closet = [tee, cardi, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = [{"id": i["id"], "category": i["category"], "label": i["label"], "qty": 1, "why": "x"}
            for i in (tee, cardi, jeans, boots)]
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 11), {})
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and not p.get("base") and cardi["id"] in (p.get("mid"), p.get("outer")), p


def test_a_planned_dress_never_simply_comes_off():
    """Boots banned with the dress and no trousers owned: the dress never vanishes for a
    cardigan alone, which would leave the legs bare (pre-push gate, 2026-11-24)."""
    dress = dict(item(700, "base", "wool dress", typ="dress"), group="onepiece", warmth=3)
    cardi = dict(item(701, "mid", "cardigan", typ="cardigan"), warmth=3)
    sandals = dict(item(702, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(703, "footwear", "boots", typ="boots"), warmth=3)
    closet = [dress, cardi, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "dress"}}]
    pack = _p(dress, cardi, boots)
    raw = [{"base": dress["id"], "mid": cardi["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 11), {})
    assert plan[0]["picks"]["base"] == dress["id"], plan


def test_a_thermal_from_home_may_replace_one_banned_with_the_boots():
    """2-5C: the packed white thermal is banned with the boots, a grey one is at home:
    the grey joins (pre-push gate, 2026-11-24)."""
    white = dict(item(710, "inner", "white thermal", typ="thermal"), group="underwear", warmth=3, colors=["white"])
    grey = dict(item(711, "inner", "grey thermal", typ="thermal"), group="underwear", warmth=3, colors=["grey"])
    shirt = dict(item(712, "base", "flannel", typ="shirt"), warmth=3)
    coat = dict(item(713, "outer", "parka", typ="coat"), group="outerwear", warmth=5)
    jeans = dict(item(714, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(715, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(716, "footwear", "boots", typ="boots"), warmth=4)
    closet = [white, grey, shirt, coat, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "thermal", "color": "white"}}]
    pack = _p(white, shirt, coat, jeans, boots)
    raw = [{"inner": white["id"], "base": shirt["id"], "outer": coat["id"], "bottoms": jeans["id"],
            "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (2, 5), {})
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and p.get("inner") == grey["id"], "a replacement before going without"


def test_a_wet_trip_looks_past_mesh_that_fits_for_a_dry_pair():
    """Rain: mesh goes with the planned tee, waterproof boots only with the packed oxford:
    the oxford and boots win (pre-push gate, 2026-11-24)."""
    tee = dict(item(720, "base", "tee", typ="t_shirt"), warmth=2)
    oxford = dict(item(721, "base", "oxford", typ="shirt"), warmth=2)
    jeans = dict(item(722, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(723, "footwear", "sandals", typ="sandals"), warmth=1, waterproof=True)
    mesh = dict(item(724, "footwear", "mesh sneakers", typ="sneakers"), warmth=2, group="footwear", material="mesh")
    boots = dict(item(725, "footwear", "rain boots", typ="boots"), warmth=3, group="footwear", waterproof=True)
    closet = [tee, oxford, jeans, sandals, mesh, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "t_shirt"}}]
    pack = _p(tee, oxford, jeans, mesh, boots)
    raw = [{"base": tee["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8),
                              {"isRain": True})
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and p["base"] == oxford["id"], p


def test_a_wet_trip_refill_prefers_dry_shoes_over_the_first_fit():
    """Rain; shorts and waterproof sandals dropped; boots banned with the jeans: chinos
    with the boots beat jeans with mesh (pre-push gate, 2026-11-24)."""
    shorts = dict(item(730, "bottoms", "shorts", typ="shorts"), warmth=1)
    sandals = dict(item(731, "footwear", "sandals", typ="sandals"), warmth=1, waterproof=True)
    jeans = dict(item(732, "bottoms", "jeans", typ="jeans"), warmth=3)
    chinos = dict(item(733, "bottoms", "chinos", typ="trousers"), warmth=3)
    mesh = dict(item(734, "footwear", "mesh sneakers", typ="sneakers"), warmth=2, group="footwear", material="mesh")
    boots = dict(item(735, "footwear", "rain boots", typ="boots"), warmth=3, group="footwear", waterproof=True)
    tee = dict(item(736, "base", "tee", typ="t_shirt"), warmth=2)
    closet = [shorts, sandals, jeans, chinos, mesh, boots, tee]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "jeans"}}]
    pack = _p(jeans, chinos, mesh, boots, tee)
    raw = [{"base": tee["id"], "bottoms": shorts["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (3, 8),
                              {"isRain": True})
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and p["bottoms"] == chinos["id"], p


def test_an_empty_undershirt_slot_may_take_a_packed_thermal():
    """8-10C: boots banned with the planned cardigan; a packed thermal under the shirt
    makes up its warmth (pre-push gate, 2026-11-24)."""
    shirt = dict(item(740, "base", "oxford", typ="shirt"), warmth=2)
    cardi = dict(item(741, "mid", "cardigan", typ="cardigan"), warmth=3)
    thermal = dict(item(742, "inner", "thermal", typ="thermal"), group="underwear", warmth=3)
    jeans = dict(item(743, "bottoms", "jeans", typ="jeans"), warmth=3)
    sandals = dict(item(744, "footwear", "sandals", typ="sandals"), warmth=1)
    boots = dict(item(745, "footwear", "boots", typ="boots"), warmth=3)
    closet = [shirt, cardi, thermal, jeans, sandals, boots]
    ban = [{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "cardigan"}}]
    pack = _p(shirt, cardi, thermal, jeans, boots)
    raw = [{"base": shirt["id"], "mid": cardi["id"], "bottoms": jeans["id"], "footwear": sandals["id"]}]
    plan = packing.keep_rules(packing.validate_plan(raw, days(1), pack, travel=False), ban, closet, pack, (8, 10), {})
    p = plan[0]["picks"]
    assert p["footwear"] == boots["id"] and p.get("inner") == thermal["id"] and not p.get("mid"), p
