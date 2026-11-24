"""
The seasonal closet against the rest of the ranking, the gaps and the shopping list:
rules before layering, the actual weather before the season, the alternatives a
summer dress or summer trousers have (pre-push gate rounds, 2026-11-24). Split from
test_season.py at the 600-line ceiling.
"""
import pytest
from fastapi.testclient import TestClient

import app as srv
import funnel
import layers
import picks as pk
import season
from test_season import CHINOS, TOKYO, advise
from wardrobe_fixtures import OXFORD, SHORTS, SNEAK, TEE, g, weather


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    return TestClient(srv.app)


def test_a_rule_given_up_outranks_the_knit_under_the_coat():
    """The layering the weather asks for is a soft preference: it never buys a broken
    pairing rule (pre-push gate, 2026-11-24: fit.layering had moved ahead of the
    relaxation cost)."""
    import funnel
    from test_funnel import CHINOS, LOAFERS, PARKA
    from wardrobe_fixtures import UNDER, day, g
    shirt = g("chkshirt1", "checked shirt", "tops", "shirt", ["base", "mid", "outer"], 2, pattern="checked")
    knit = g("strknit01", "striped sweater", "tops", "sweater", ["base", "mid", "outer"], 4, pattern="striped")
    d = day(3, UNDER, shirt, knit, PARKA, CHINOS, LOAFERS, hi=8)
    c = funnel.Ctx(d, funnel.target_level(d.look), frozenset({"colour"}))
    base = {"inner": UNDER["id"], "base": shirt["id"], "outer": PARKA["id"], "bottoms": CHINOS["id"],
            "footwear": LOAFERS["id"]}
    shapes = [(("base", "mid", "outer"), {**base, "mid": knit["id"]}), (("base", "outer"), base)]
    today = frozenset(base) | {"mid"}
    got = sorted(funnel._evaluate(c, shapes, funnel.priority_for(c), today), key=lambda o: o.rank)
    assert got and got[0].picks.get("mid") is None and got[0].relaxed == (), [(o.picks.get("mid"), o.rank) for o in got]


def test_the_rain_outranks_the_season():
    """Rainy 15-20C on a normal 9-17C day: leather loafers kept for warm months beat
    in-season mesh sneakers, which would give up the wet rule (pre-push gate,
    2026-11-24)."""
    from test_funnel import CHINOS, LOAFERS, MESH, prefs, run
    from wardrobe_fixtures import OXFORD, UNDER
    summer = {**LOAFERS, "season": "warm"}
    _, r = run(15, UNDER, OXFORD, CHINOS, MESH, summer, hi=20, rain=80, isRain=True,
               p=prefs(normal=season.Normal(9, 17)))
    o = r.outfits[0]
    assert o.picks["footwear"] == LOAFERS["id"] and "wet" not in o.relaxed, (o.picks, o.relaxed)
    _, r = run(15, UNDER, OXFORD, CHINOS, MESH, summer, hi=20, p=prefs(normal=season.Normal(9, 17)))
    assert r.outfits[0].picks["footwear"] == MESH["id"], "dry: the season decides"


def test_the_rain_outranks_the_season_when_the_in_season_pair_cannot_be_worn():
    """An in-season leather pair banned with the only trousers is no dry option; the
    summer loafers are (pre-push gate, 2026-11-24)."""
    from test_funnel import CHINOS, LOAFERS, MESH, prefs, run
    from wardrobe_fixtures import OXFORD, UNDER, g
    derbies = g("derbies01", "black derbies", "footwear", "dress_shoes", ["footwear"], 2, colors=["black"])
    ban = [{"kind": "avoid_pair", "a": {"type": "dress_shoes"}, "b": {"type": "trousers"}}]
    summer = {**LOAFERS, "season": "warm"}
    _, r = run(15, UNDER, OXFORD, CHINOS, MESH, summer, derbies, hi=20, rain=80, isRain=True,
               p=prefs(normal=season.Normal(9, 17), rules=tuple(ban)))
    o = r.outfits[0]
    assert o.picks["footwear"] == LOAFERS["id"] and "wet" not in o.relaxed, (o.picks, o.relaxed)


def test_dry_feet_before_the_day_s_level():
    """User, 2026-11-24 ("dry feet first"): on a wet office day, drawstring trousers a
    level down with leather loafers beat chinos with mesh sneakers."""
    from test_funnel import CHINOS, DRAWSTR, LOAFERS, MESH, WHITE_OX, prefs, run
    from wardrobe_fixtures import UNDER
    ban = [{"kind": "avoid_pair", "a": {"type": "loafers"}, "b": {"type": "trousers", "color": "navy"}}]
    _, r = run(14, UNDER, WHITE_OX, CHINOS, DRAWSTR, MESH, LOAFERS, hi=19, rain=80, isRain=True,
               p=prefs("office", rules=tuple(ban)))
    o = r.outfits[0]
    assert o.picks["footwear"] == LOAFERS["id"] and o.picks["bottoms"] == DRAWSTR["id"], (o.picks, o.relaxed)
    assert "wet" not in o.relaxed


def test_unavoidable_mesh_is_noted_never_held_aside():
    """Mesh the only shoes on a wet day: the rain note says so, but nothing dry exists
    to hold out for, so the outfit is not held aside (pre-push gate, 2026-11-24: the
    ladder walked every combination for a dry outfit that cannot exist), and it is no
    season note."""
    from test_funnel import CHINOS, MESH, prefs, run
    from wardrobe_fixtures import OXFORD, UNDER
    d, r = run(15, UNDER, OXFORD, CHINOS, MESH, hi=20, rain=80, isRain=True, p=prefs(normal=season.Normal(9, 17)))
    o = r.outfits[0]
    assert "wet" in o.relaxed and o.rank[0] == 0 and not season.held(d, o.picks), (o.relaxed, o.rank)
    assert r.exact == 0, "no exhaustive walk"


def test_a_rainy_morning_in_mesh_says_so_and_never_blames_the_season(api, monkeypatch):
    """Mesh the only shoes on a wet November day: the note is the rain's, not "nothing
    in season" (the weather now shares the season's tier, funnel._evaluate)."""
    import relaxnotes
    from test_funnel import MESH
    clean = {k: v for k, v in MESH.items() if k != "availableCount"}
    closet = [{k: v for k, v in i.items() if k != "availableCount"} for i in (TEE, OXFORD, CHINOS)] + [clean]
    out = advise(api, monkeypatch, weather(15, 20, rain=80, isRain=True, date="2026-11-20"), closet, TOKYO)
    assert out["picks"]["footwear"] == MESH["id"]
    assert relaxnotes.SEASON not in out["outfit_text"] and relaxnotes.SEASON_UNSURE not in out["outfit_text"], \
        out["outfit_text"]


def test_the_rain_outranks_any_number_of_styling_steps(monkeypatch):
    """Summer loafers that cost two styling steps still beat mesh that costs only the
    wet rule (pre-push gate, 2026-11-24): the weather is ahead of the rules given up."""
    from test_funnel import CHINOS, LOAFERS, MESH, prefs
    from wardrobe_fixtures import OXFORD, UNDER, day, g
    summer = {**LOAFERS, "season": "warm"}
    # An in-season leather pair banned with the trousers: the loafers really count as
    # out of season (season._fits), so both outfits share the tier.
    derbies = g("derbies01", "black derbies", "footwear", "dress_shoes", ["footwear"], 2, colors=["black"])
    ban = ({"kind": "avoid_pair", "a": {"type": "dress_shoes"}, "b": {"type": "trousers"}},)
    d = day(14, UNDER, OXFORD, CHINOS, MESH, summer, derbies, hi=19, rain=80, isRain=True,
            prefs=prefs(normal=season.Normal(9, 17), rules=ban))
    c = funnel.Ctx(d, funnel.target_level(d.look), frozenset(funnel.RELAX))
    monkeypatch.setattr(funnel, "needed",
                        lambda ctx, p: ("colour", "texture") if p.get("footwear") == LOAFERS["id"] else ("wet",))
    base = {"inner": UNDER["id"], "base": OXFORD["id"], "bottoms": CHINOS["id"]}
    found = [(("base",), {**base, "footwear": MESH["id"]}), (("base",), {**base, "footwear": LOAFERS["id"]})]
    got = sorted(funnel._evaluate(c, found, funnel.priority_for(c), frozenset(base) | {"footwear"}),
                 key=lambda o: o.rank)
    assert all(o.rank[0] == 1 for o in got), [o.rank for o in got]
    assert got[0].picks["footwear"] == LOAFERS["id"], [(o.picks["footwear"], o.rank) for o in got]


def test_a_summer_dress_on_a_cold_morning_is_a_leg_gap():
    """The only dress is warmth 1 on an 8-12C day: no warmer one exists, so the check
    lets it through, and the shopping list hears of it (pre-push gate, 2026-11-24)."""
    import gaps
    from wardrobe_fixtures import day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    coat = g("wcoat0001", "wool coat", "outerwear", "coat", ["outer"], 4)
    d = day(8, dress, coat, SNEAK, hi=12)
    picks = {"base": dress["id"], "outer": coat["id"], "footwear": SNEAK["id"]}
    assert gaps.LEGS_GAP in gaps.missing(picks, d, []) and "base" not in gaps.missing(picks, d, [])


def test_a_legs_gap_reaches_shopping_as_leg_cover():
    """"legs" stays itself at /shopping (a phone of any age may send it), never a 422."""
    import schemas
    assert schemas.Gap(slot="legs").slot == "legs"
    assert schemas.Gap(slot="warmth").slot == "outer"


def test_shorts_give_way_to_a_warm_dress():
    """Shorts and a wearable warm dress at 8-12C: the shorts are underdressed, so no
    false bottoms gap (pre-push gate, 2026-11-24)."""
    from wardrobe_fixtures import day
    dress = g("wooldress", "wool dress", "onepiece", "dress", ["base"], 3)
    d = day(8, SHORTS, dress, TEE, SNEAK, hi=12)
    assert layers.underdressed(SHORTS, "bottoms", d)


def test_leg_cover_evidence_buys_trousers_or_a_dress_never_a_tee(monkeypatch):
    import asyncio

    import shopping
    gaps_ = [{"slot": "legs", "n": 5, "loC": 6, "hiC": 12}]
    reply = {"suggestions": [{"what": "warm wool trousers", "slot": "bottoms", "why": "x", "priority": 1},
                             {"what": "knit sweater dress", "slot": "base", "why": "x", "priority": 1},
                             {"what": "white crew tee", "slot": "base", "why": "x", "priority": 2}],
             "verdict": "v"}

    async def chat(*a, **k):
        import json
        return json.dumps(reply)
    monkeypatch.setattr(shopping, "_chat", chat)
    out = asyncio.run(shopping.shopping_list([], gaps_, [], {"tempOffset": 0}))
    assert [s["what"] for s in out["suggestions"]] == ["warm wool trousers", "knit sweater dress"], out


def test_a_summer_dress_gives_way_to_warm_trousers_and_a_top():
    """8-12C with a sundress, a tee and warm jeans: the jeans and tee are worn, and no
    leg gap is recorded (pre-push gate, 2026-11-24)."""
    import gaps
    from test_funnel import run
    from wardrobe_fixtures import JEANS, day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    coat = g("wcoat0001", "wool coat", "outerwear", "coat", ["outer"], 4)
    d, r = run(8, dress, TEE, JEANS, coat, SNEAK, hi=12)
    p = r.outfits[0].picks
    assert p["base"] == TEE["id"] and p["bottoms"] == JEANS["id"], p
    d = day(8, dress, TEE, JEANS, coat, SNEAK, hi=12)
    assert gaps.LEGS_GAP not in gaps.missing({"base": dress["id"], "outer": coat["id"], "footwear": SNEAK["id"]}, d, [])


def test_warm_trousers_with_no_top_to_wear_are_no_alternative_to_the_dress():
    """Two sundresses and warm jeans, but no top: the jeans cannot be worn, so the dress
    is what they have, and the leg gap is real."""
    import gaps
    from wardrobe_fixtures import JEANS, day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    dress2 = g("sumdress2", "cotton sundress", "onepiece", "dress", ["base"], 1, colors=["white"])
    coat = g("wcoat0001", "wool coat", "outerwear", "coat", ["outer"], 4)
    d = day(8, dress, dress2, JEANS, coat, SNEAK, hi=12)
    assert not layers.underdressed(dress, "base", d)
    assert gaps.LEGS_GAP in gaps.missing({"base": dress["id"], "outer": coat["id"], "footwear": SNEAK["id"]}, d, [])


def test_a_dress_shirt_is_no_leg_cover():
    import shopping
    assert shopping._one_piece("knit sweater dress") and shopping._one_piece("wool jumpsuit")
    assert not shopping._one_piece("warm flannel dress shirt") and not shopping._one_piece("dress shoes")


def test_out_of_season_shorts_give_way_to_an_in_season_dress():
    """19-24C actual, 9-17C normal: the shorts are out of season while an in-season
    dress could be worn, so they count and are held aside (pre-push gate, 2026-11-24)."""
    from test_funnel import run
    from wardrobe_fixtures import day
    dress = g("cotdress1", "cotton dress", "onepiece", "dress", ["base"], 2)
    p = pk.Prefs(normal=season.Normal(9, 17))
    d = day(19, SHORTS, TEE, dress, SNEAK, hi=24, prefs=p)
    assert season.counts(d, "bottoms", SHORTS["id"])
    _, r = run(19, SHORTS, TEE, dress, SNEAK, hi=24, p=__import__("test_funnel").prefs(normal=season.Normal(9, 17)))
    assert r.outfits[0].picks["base"] == dress["id"] and not r.outfits[0].picks.get("bottoms"), r.outfits[0].picks


def test_a_cardigan_worn_as_the_top_makes_jeans_an_alternative_to_the_dress():
    """Sundress, jeans, a mid/outer cardigan: cardigan and jeans dress them, so the dress
    is underdressed and no leg gap is recorded (pre-push gate, 2026-11-24)."""
    import gaps
    from wardrobe_fixtures import CARDI, JEANS, day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    d = day(8, dress, JEANS, CARDI, SNEAK, hi=12)
    assert layers.underdressed(dress, "base", d)
    assert gaps.LEGS_GAP not in gaps.missing({"base": dress["id"], "footwear": SNEAK["id"]}, d, [])


def test_the_season_memo_lives_on_the_request_not_the_module():
    """No wardrobe outlives its request (README: the server stores nothing)."""
    from wardrobe_fixtures import day
    assert not [k for k, v in vars(season).items() if k.isupper() and isinstance(v, dict)]
    p = pk.Prefs(normal=season.Normal(1, 10))
    d1, d2 = day(3, SHORTS, CHINOS, TEE, SNEAK, prefs=p), day(3, SHORTS, TEE, SNEAK, prefs=p)
    assert season.counts(d1, "bottoms", SHORTS["id"]) and not season.counts(d2, "bottoms", SHORTS["id"])
    assert d1.memo and d1.memo is not d2.memo


def test_trousers_and_a_cardigan_hold_an_out_of_season_dress_aside():
    """19-24C actual, 9-17C normal: a summer dress counts as out of season beside
    in-season jeans and a cardigan worn as the top (pre-push gate, 2026-11-24)."""
    from wardrobe_fixtures import day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    jeans = g("ljeans001", "light jeans", "bottoms", "jeans", ["bottoms"], 2)
    cardi = g("lcardi001", "light cardigan", "tops", "cardigan", ["mid", "outer"], 2)
    p = pk.Prefs(normal=season.Normal(9, 17))
    d = day(19, dress, jeans, cardi, SNEAK, hi=24, prefs=p)
    assert season.counts(d, "base", dress["id"])
    d = day(19, dress, cardi, SNEAK, hi=24, prefs=p)
    assert not season.counts(d, "base", dress["id"]), "no trousers: the dress is what they have"


def test_a_tee_alone_is_no_alternative_to_an_out_of_season_dress():
    """Sundress, tee, sneakers and no trousers: only the dress covers the legs, so it
    is not counted out of season, nor searched past (pre-push gate, 2026-11-24)."""
    from test_funnel import prefs, run
    from wardrobe_fixtures import day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    d = day(19, dress, TEE, SNEAK, hi=24, prefs=pk.Prefs(normal=season.Normal(9, 17)))
    assert not season.counts(d, "base", dress["id"])
    _, r = run(19, dress, TEE, SNEAK, hi=24, p=prefs(normal=season.Normal(9, 17)))
    o = r.outfits[0]
    assert o.picks["base"] == dress["id"] and o.rank[0] == 0 and r.exact == 0, (o.picks, o.rank, r.exact)


def test_snow_boots_outrank_the_season():
    """Snowy 2-8C, winter normals: waterproof boots banned with the jeans but fine with
    summer-only chinos beat sneakers with the jeans (pre-push gate, 2026-11-24)."""
    from test_funnel import PARKA, prefs, run
    from wardrobe_fixtures import BOOTS, JEANS, UNDER
    summer = {**CHINOS, "season": "warm"}
    ban = ({"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "jeans"}},)
    _, r = run(2, UNDER, TEE, PARKA, JEANS, summer, SNEAK, BOOTS, hi=8, isSnow=True,
               p=prefs(normal=season.Normal(1, 10), rules=ban))
    o = r.outfits[0]
    assert o.picks["footwear"] == BOOTS["id"] and o.picks["bottoms"] == CHINOS["id"], (o.picks, o.relaxed, o.rank)


def test_an_outer_only_cardigan_is_a_top_beside_a_dress():
    """A cardigan filed only as outer is still the top: with warm chinos it is an
    alternative to a summer dress, for the cold check and for the season (pre-push
    gate, 2026-11-24). A coat alone is not."""
    import gaps
    from test_funnel import PARKA
    from wardrobe_fixtures import day
    dress = g("sumdress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    cardi = g("ocardi001", "outer cardigan", "tops", "cardigan", ["outer"], 3)
    d = day(8, dress, CHINOS, cardi, SNEAK, hi=12)
    assert layers.underdressed(dress, "base", d)
    assert gaps.LEGS_GAP not in gaps.missing({"base": dress["id"], "footwear": SNEAK["id"]}, d, [])
    assert not layers.underdressed(dress, "base", day(8, dress, CHINOS, PARKA, SNEAK, hi=12)), "a coat is no top"
    light = g("lcardi002", "light outer cardigan", "tops", "cardigan", ["outer"], 2)
    p = pk.Prefs(normal=season.Normal(9, 17))
    lchinos = g("lchinos01", "light chinos", "bottoms", "trousers", ["bottoms"], 2)
    assert season.counts(day(19, dress, lchinos, light, SNEAK, hi=24, prefs=p), "base", dress["id"])


def test_a_worn_garment_keeps_its_line_when_its_slot_is_a_gap():
    """Summer trousers worn on a cold morning are a 'bottoms' gap; the fallback's plain
    lines still name them, never 'nothing in your closet' (pre-push gate, 2026-11-24)."""
    import advisor
    from wardrobe_fixtures import day
    d = day(8, SHORTS, TEE, SNEAK, hi=12)
    picks = {"base": TEE["id"], "bottoms": SHORTS["id"], "footwear": SNEAK["id"]}
    lines = advisor._plain_lines(advisor.Answer({"lines": {}}, picks, []), picks, d, ["bottoms"])
    assert lines["bottoms"] == SHORTS["label"], lines


def test_a_worn_cold_leg_slot_is_no_hole_for_the_chooser():
    """Only shorts at 8-12C: the gap is shopping evidence, but the chooser is not asked
    to suggest trousers for a slot the shorts fill (pre-push gate, 2026-11-24)."""
    import advisor
    import gaps
    from wardrobe_fixtures import day
    d = day(8, SHORTS, TEE, SNEAK, hi=12)
    picks = {"base": TEE["id"], "bottoms": SHORTS["id"], "footwear": SNEAK["id"]}
    assert "bottoms" in gaps.missing(picks, d, [])
    assert "bottoms" not in advisor._holes(picks, d)


def test_an_in_season_knit_worn_as_the_top_holds_a_summer_shirt_aside():
    """14-18C on a 9-17C normal: a summer-only shirt counts as out of season beside an
    in-season sweater filed only as mid (pre-push gate, 2026-11-24)."""
    from wardrobe_fixtures import day
    shirt = {**g("sumshirt1", "linen shirt", "tops", "shirt", ["base"], 2), "season": "warm"}
    knit = g("midknit01", "merino sweater", "tops", "sweater", ["mid"], 3)
    p = pk.Prefs(normal=season.Normal(9, 17))
    d = day(14, shirt, knit, CHINOS, SNEAK, hi=18, prefs=p)
    assert season.counts(d, "base", shirt["id"])


def test_a_coat_worn_in_the_mid_slot_gives_up_no_coat():
    """An outerwear coat a rule puts in the mid slot is the coat (check._coat looks in
    every torso slot): no 'coat' given up (pre-push gate, 2026-11-24)."""
    from wardrobe_fixtures import day
    coat = g("midcoat01", "wool coat", "outerwear", "coat", ["mid", "outer"], 4)
    d = day(6, TEE, coat, CHINOS, SNEAK, hi=10)
    c = funnel.Ctx(d, funnel.target_level(d.look))
    picks = {"base": TEE["id"], "mid": coat["id"], "outer": None, "bottoms": CHINOS["id"], "footwear": SNEAK["id"]}
    assert "coat" not in funnel.needed(c, picks)
    assert "coat" in funnel.needed(c, {**picks, "mid": None}), "no coat at all is given up"
    assert "coat" not in funnel.needed(c, {"base": TEE["id"], "outer": None}), "the torso is not decided yet"


def test_waterproof_summer_sandals_are_no_snow_gear():
    """Snowy 6-10C, waterproof warmth-1 sandals and plain warmth-3 boots: the sandals
    are too cold, so the boots are not refused for want of snow gear (pre-push gate,
    2026-11-24)."""
    import check
    from test_funnel import run
    from wardrobe_fixtures import JACKET, UNDER
    sandals = g("wpsandal1", "waterproof sandals", "footwear", "sandals", ["footwear"], 1, waterproof=True)
    boots = g("plboots01", "leather boots", "footwear", "boots", ["footwear"], 3)
    d, r = run(6, UNDER, TEE, JACKET, CHINOS, sandals, boots, hi=10, isSnow=True)
    o = r.outfits[0]
    assert o.picks["footwear"] == boots["id"], (o.picks, o.relaxed)
    assert not check.hard(check.issues(o.picks, d))


def test_a_dress_with_trailing_words_is_still_a_dress():
    import shopping
    assert shopping._one_piece("Wool dress with long sleeves") and shopping._one_piece("knit dress, midi length")
    assert not shopping._one_piece("dress shirt with a spread collar")


def test_the_last_resort_prefers_fewer_cold_slots():
    """8-12C: warm jeans banned with the only tee, so the shorts come back; the warm
    sneakers beat the sandals rather than tying with them (pre-push gate, 2026-11-24)."""
    from test_funnel import run
    from wardrobe_fixtures import JEANS
    sandals = g("csandal01", "sandals", "footwear", "sandals", ["footwear"], 1)
    ban = ({"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "t_shirt"}},)
    from test_funnel import prefs
    _, r = run(8, TEE, SHORTS, JEANS, sandals, SNEAK, hi=12, p=prefs(rules=ban))
    assert r.outfits[0].picks["footwear"] == SNEAK["id"], [(o.picks.get("footwear"), o.rank[:3]) for o in r.outfits]
    assert all(o.picks["footwear"] == SNEAK["id"] for o in r.outfits if o.rank[0] == r.outfits[0].rank[0]
               and o.rank[1] == r.outfits[0].rank[1])
