"""The funnel (funnel.py, user 2026-10-20): code narrows the wardrobe, the model only
chooses among the survivors. The three logged failures are pinned first."""
import asyncio
from dataclasses import replace

import advisor
import check
import fake_model
import funnel
import picks as pk
import style
from wardrobe_fixtures import (CARDI, DRESS, JACKET, JEANS, OXFORD, POLO, SHORTS, SNEAK, SWEATER, TEE, UNDER,
                               day, g, weather)

INNER_LS = g("innerls01", "white long-sleeve crewneck", "underwear", "thermal", ["inner"], 2, colors=["white"],
             sleeve="long")
WHITE_OX = g("whiteox01", "white oxford shirt", "tops", "shirt", ["base", "mid", "outer"], 2, colors=["white"])
MERINO = g("merino001", "navy merino crew sweater", "tops", "sweater", ["base", "mid", "outer"], 3)
ROSE = g("rosecrew1", "dusty rose crew-neck sweater", "tops", "sweater", ["base", "mid", "outer"], 4,
         colors=["dusty rose"])
REINDEER = g("reindeer1", "navy reindeer sweater", "tops", "sweater", ["base", "mid", "outer"], 4)
RAINJKT = g("rainjkt01", "navy rain jacket", "outerwear", "rainwear", ["outer"], 3, waterproof=True)
PARKA = g("parka0001", "olive parka", "outerwear", "coat", ["outer"], 4, colors=["olive"])
DRAWSTR = g("drawstr01", "beige drawstring pants", "bottoms", "trousers", ["bottoms"], 3, colors=["beige"],
            formality=["casual", "smart"])
CHINOS = g("chinos001", "navy chinos", "bottoms", "trousers", ["bottoms"], 3, formality=["casual", "smart"])
MESH = g("meshsnk01", "grey mesh sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["grey"])
LOAFERS = g("loafers01", "brown leather loafers", "footwear", "loafers", ["footwear"], 2, colors=["brown"])
BROWN_BELT = g("bbelt0001", "brown leather belt", "accessories", "belt", ["accessories"], 1, colors=["brown"])
BLACK_BELT = g("kbelt0001", "black leather belt", "accessories", "belt", ["accessories"], 1, colors=["black"])
SCARF = g("scarf0001", "grey wool scarf", "accessories", "scarf", ["accessories"], 4, colors=["grey"])


def prefs(occasion="", style_="casual", **kw):
    return replace(pk.Prefs(**kw), look=style.Look(style_, "man", occasion))


def run(t, *items, hi=None, p=None, **w):
    d = day(t, *items, hi=hi, prefs=p or prefs(), **w)
    return d, funnel.search(funnel.Ctx(d, funnel.target_level(d.look)))


def worn(o, *slots):
    return {s: o.picks.get(s) for s in slots}


def assert_valid(d, result):
    assert result.outfits, "something survives"
    for o in result.outfits:
        assert not check.hard(check.issues(o.picks, d)), (o.picks, check.hard(check.issues(o.picks, d)))


OFFICE = [UNDER, WHITE_OX, MERINO, RAINJKT, DRAWSTR, CHINOS, MESH, LOAFERS, BROWN_BELT, BLACK_BELT]


def test_2026_10_20_office_wet_morning_drawstring_and_mesh_never_survive():
    d, r = run(6, *OFFICE, hi=19, p=prefs("office"), rain=80, isRain=True)
    assert_valid(d, r)
    for o in r.outfits:
        assert o.picks["bottoms"] == CHINOS["id"], "drawstring is below an office day"
        assert o.picks["footwear"] == LOAFERS["id"], "mesh soaks through on a wet commute"
        assert o.picks["accessories"] in (None, BROWN_BELT["id"]), "a belt matches the shoes"
        assert not o.relaxed


def test_2026_10_18_1035_a_long_sleeve_never_goes_under_a_tee():
    closet = [INNER_LS, UNDER, TEE, REINDEER, PARKA, JEANS, SNEAK]
    d, r = run(3, *closet, hi=12)
    assert_valid(d, r)
    for o in r.outfits:
        assert not (o.picks.get("inner") == INNER_LS["id"] and o.picks.get("base") == TEE["id"])


def test_2026_10_18_1029_a_polo_never_goes_under_a_sweater():
    closet = [UNDER, POLO, ROSE, REINDEER, MERINO, PARKA, CHINOS, SNEAK]
    d, r = run(3, *closet, hi=12)
    assert_valid(d, r)
    for o in r.outfits:
        if o.picks.get("base") == POLO["id"]:
            assert o.picks.get("mid") is None, o.picks


def test_drawstring_only_is_served_with_a_note_not_refused():
    closet = [UNDER, WHITE_OX, MERINO, RAINJKT, DRAWSTR, LOAFERS]
    d, r = run(10, *closet, hi=19, p=prefs("office"))
    assert_valid(d, r)
    assert r.outfits[0].picks["bottoms"] == DRAWSTR["id"]
    assert r.outfits[0].relaxed and funnel.notes(r.outfits[0].relaxed)


def test_mesh_only_on_a_wet_day_is_served_with_a_note():
    closet = [UNDER, WHITE_OX, CHINOS, MESH]
    d, r = run(14, *closet, hi=20, rain=90, isRain=True)
    assert r.outfits[0].picks["footwear"] == MESH["id"]
    assert "wet" in r.outfits[0].relaxed
    assert any("damp" in n for n in funnel.notes(r.outfits[0].relaxed))


def test_a_dry_day_never_mentions_shoes():
    d, r = run(14, UNDER, WHITE_OX, CHINOS, MESH, hi=20)
    assert "wet" not in r.outfits[0].relaxed


def test_a_hot_day_has_no_layer_and_a_cold_one_has_knit_and_coat():
    _, hot = run(27, UNDER, TEE, OXFORD, CARDI, JACKET, SHORTS, JEANS, SNEAK, hi=31)
    for o in hot.outfits:
        assert not o.picks.get("mid") and not o.picks.get("outer"), o.picks
    d, cold = run(2, UNDER, TEE, OXFORD, SWEATER, PARKA, JEANS, SNEAK, hi=9)
    assert_valid(d, cold)
    best = cold.outfits[0].picks
    assert best["mid"] == SWEATER["id"] and best["outer"] == PARKA["id"], best
    # Under the oxford an undershirt; under the tee none (user, 2026-10-24).
    assert best["inner"] == (None if best["base"] == TEE["id"] else UNDER["id"]), best


def test_accessories_only_for_a_reason():
    _, warm = run(18, UNDER, OXFORD, CHINOS, SNEAK, SCARF, hi=24)
    assert warm.outfits[0].picks["accessories"] is None, "no scarf on a mild day"
    _, belt = run(18, UNDER, OXFORD, CHINOS, SNEAK, BROWN_BELT, hi=24)
    assert belt.outfits[0].picks["accessories"] == BROWN_BELT["id"]


def test_a_dress_clears_the_trousers_and_a_lone_cardigan_still_dresses_them():
    d, r = run(18, UNDER, DRESS, SNEAK, hi=24)
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == DRESS["id"] and not r.outfits[0].picks["bottoms"]
    d, r = run(14, CARDI, JEANS, SNEAK, hi=18)
    assert_valid(d, r)
    assert r.outfits[0].picks["mid"] == CARDI["id"] or r.outfits[0].picks["outer"] == CARDI["id"]


def test_a_partial_closet_is_dressed_where_it_can_be():
    d, r = run(14, UNDER, OXFORD, JEANS, hi=18)
    assert_valid(d, r)
    assert r.outfits[0].picks["footwear"] is None and r.outfits[0].picks["base"] == OXFORD["id"]


def test_a_reroll_moves_every_slot_it_can():
    closet = [UNDER, OXFORD, WHITE_OX, CHINOS, JEANS, SNEAK, LOAFERS]
    _, first = run(16, *closet, hi=22)
    shown = {s: i for s, i in first.outfits[0].picks.items() if i}
    _, again = run(16, *closet, hi=22, p=prefs(shown=shown))
    best = again.outfits[0].picks
    for slot in ("base", "bottoms", "footwear"):
        assert best[slot] != shown[slot], (slot, best, shown)


def test_rotation_prefers_what_was_not_worn_lately():
    a = {**OXFORD, "_ago": 1}
    b = {**WHITE_OX, "_ago": 6}
    _, r = run(16, UNDER, a, b, CHINOS, LOAFERS, hi=22)
    assert r.outfits[0].picks["base"] == WHITE_OX["id"]


def test_the_search_is_deterministic():
    picks1 = [o.picks for o in run(6, *OFFICE, hi=19, p=prefs("office"))[1].outfits]
    picks2 = [o.picks for o in run(6, *OFFICE, hi=19, p=prefs("office"))[1].outfits]
    assert picks1 == picks2


def test_their_rules_are_never_relaxed():
    """A ban on loafers stands on a wet day, though the only other shoes soak through."""
    import rules
    clean = rules.clean_rules([{"kind": "avoid_item", "a": {"type": "loafers"}}])
    assert clean
    d, r = run(14, UNDER, OXFORD, CHINOS, LOAFERS, MESH, hi=20, p=prefs(rules=tuple(clean)), rain=90, isRain=True)
    assert r.outfits and all(o.picks.get("footwear") == MESH["id"] for o in r.outfits)
    assert "wet" in r.outfits[0].relaxed


# ── through advisor.dress ─────────────────────────────────────────────────────────

def dress(monkeypatch, closet, w, p, choices, recent=None):
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    seen = fake_model.install(monkeypatch, [], choices=choices)
    return asyncio.run(advisor.dress(w, closet, p, recent)), seen


def test_the_model_chooses_among_survivors_and_writes_the_words(monkeypatch):
    out, seen = dress(monkeypatch, OFFICE, weather(6, 19, rain=80, isRain=True), prefs("office"),
                      [fake_model.choice(1, tip="Jacket off at the desk.", bottoms="navy chinos — sharp")])
    assert len(seen["chooser"]) == 1 and "OUTFIT 1" in seen["chooser"][0]
    assert out["byModel"] is True and out["picks"]["bottoms"] == CHINOS["id"]
    assert "Jacket off at the desk." in out["text"]
    assert seen["calls"] == 0, "the whole-wardrobe advisor was never asked"


def test_model_unreachable_still_serves_the_funnels_first(monkeypatch):
    out, _ = dress(monkeypatch, OFFICE, weather(6, 19, rain=80, isRain=True), prefs("office"), [None])
    assert out["byModel"] is False and out["picks"]["footwear"] == LOAFERS["id"]
    assert out["text"], "plain lines"


def test_none_of_them_runs_the_funnel_once_more_without_them(monkeypatch):
    out, seen = dress(monkeypatch, OFFICE, weather(6, 19), prefs("office"),
                      [fake_model.choice(0, reason="all too plain"), fake_model.choice(1)])
    assert len(seen["chooser"]) == 2
    first = seen["chooser"][0]
    assert out["byModel"] is True
    assert first != seen["chooser"][1], "different outfits the second time"


def test_a_bad_answer_costs_the_words_only(monkeypatch):
    out, _ = dress(monkeypatch, OFFICE, weather(10, 19), prefs("office"), ['{"choice": 9}'])
    assert out["byModel"] is False and out["picks"]["base"]


def test_a_relaxed_rule_is_said_in_the_tip(monkeypatch):
    out, _ = dress(monkeypatch, [UNDER, WHITE_OX, CHINOS, MESH], weather(14, 20, rain=90, isRain=True), prefs(),
                   [fake_model.choice(1, tip="")])
    assert "damp shoes" in out["tip"]


def test_production_default_is_the_funnel(monkeypatch):
    monkeypatch.delenv("OUTFIT_ENGINE", raising=False)
    assert advisor.engine() == "funnel"
    monkeypatch.setenv("OUTFIT_ENGINE", "model")
    assert advisor.engine() == "model"


def test_source_says_funnel_when_no_model_wrote_it(monkeypatch):
    from fastapi.testclient import TestClient

    import app as srv

    async def wet(lat, lon, day_):
        return weather(6, 19, rain=80, isRain=True)
    monkeypatch.setattr(srv.weather, "fetch_weather", wet)
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    fake_model.install(monkeypatch, [], choices=[None])
    r = TestClient(srv.app).post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": OFFICE, "occasion": "office"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "funnel" and body["closetUsed"] is True
    assert body["picks"]["footwear"] == LOAFERS["id"]


# ── each guard on its own (each one mutation-checked) ─────────────────────────────

def strict(t, *items, hi=None, p=None, **w):
    d = day(t, *items, hi=hi, prefs=p or prefs(), **w)
    return funnel.Ctx(d, funnel.target_level(d.look))


def test_the_occasion_band_removes_weekend_trousers_on_an_office_day():
    ctx = strict(6, *OFFICE, hi=19, p=prefs("office"))
    cands, removed = funnel.candidates(ctx, funnel.priority_for(ctx))
    assert DRAWSTR["id"] not in cands["bottoms"] and CHINOS["id"] in cands["bottoms"]
    assert removed.get("occasion")


def test_the_wet_filter_removes_mesh_only_when_it_is_wet():
    wet = strict(6, *OFFICE, hi=19, p=prefs("casual"), rain=80, isRain=True)
    assert MESH["id"] not in funnel.candidates(wet, funnel.priority_for(wet))[0]["footwear"]
    dry = strict(6, *OFFICE, hi=19, p=prefs("casual"))
    assert MESH["id"] in funnel.candidates(dry, funnel.priority_for(dry))[0]["footwear"]


def test_utility_trousers_never_go_with_a_collar_even_on_a_casual_day():
    _, r = run(18, UNDER, POLO, TEE, DRAWSTR, SNEAK, hi=24)
    assert r.outfits
    for o in r.outfits:
        assert not (o.picks["base"] == POLO["id"] and o.picks["bottoms"] == DRAWSTR["id"]), o.picks


def test_the_pairing_check_refuses_a_long_sleeve_under_a_tee_by_itself():
    ctx = strict(3, INNER_LS, TEE, hi=12)
    assert funnel.clash(ctx, {"inner": INNER_LS["id"], "base": TEE["id"]}) == "stack"


def test_no_tie_on_a_casual_day():
    tie = g("tie000001", "navy tie", "accessories", "tie", ["accessories"], 1)
    _, r = run(16, UNDER, OXFORD, CHINOS, SNEAK, tie, hi=22)
    assert r.outfits[0].picks["accessories"] is None


def test_a_reroll_moves_even_to_something_worn_yesterday():
    """Lexicographic: a shown slot that can change does, whatever the rotation says."""
    shown_ox = {**OXFORD, "_ago": None}
    worn_yday = {**WHITE_OX, "_ago": 0}
    closet = [UNDER, shown_ox, worn_yday, CHINOS, LOAFERS]
    _, r = run(16, *closet, hi=22, p=prefs(shown={"base": OXFORD["id"]}))
    assert r.outfits[0].picks["base"] == WHITE_OX["id"]
    # …even when the rotation scores the shown one far higher: a repeat ranks first.
    ctx = strict(16, *closet, hi=22, p=prefs(shown={"base": OXFORD["id"]}))
    r = funnel.search(ctx, lambda i, s: 100.0 if i == OXFORD["id"] else 0.0)
    assert r.outfits[0].picks["base"] == WHITE_OX["id"]


def test_the_chooser_s_number_is_the_outfit_served(monkeypatch):
    w, p = weather(10, 19), prefs("office")
    d = day(10, *OFFICE, hi=19, prefs=p)
    want = funnel.search(funnel.Ctx(d, funnel.target_level(d.look))).outfits
    assert len(want) >= 2
    out, _ = dress(monkeypatch, OFFICE, w, p, [fake_model.choice(2)])
    assert out["picks"] == want[1].picks


def test_snow_wants_their_waterproof_boots_unless_they_banned_them():
    from wardrobe_fixtures import BOOTS
    d, r = run(-3, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, BOOTS, hi=1, isSnow=True)
    assert_valid(d, r)
    assert all(o.picks["footwear"] == BOOTS["id"] for o in r.outfits)
    import rules
    ban = tuple(rules.clean_rules([{"kind": "avoid_item", "a": {"type": "boots"}}]))
    d, r = run(-3, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, BOOTS, hi=1, isSnow=True, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].picks["footwear"] == SNEAK["id"], "a banned boot is no boot: the sneakers stay"


def test_an_open_shirt_goes_over_a_tee_never_over_a_polo():
    ctx = strict(16, POLO, TEE, OXFORD, hi=20)
    assert funnel.clash(ctx, {"base": POLO["id"], "outer": OXFORD["id"]}) == "texture"
    assert funnel.clash(ctx, {"base": TEE["id"], "outer": OXFORD["id"]}) is None


def test_a_lone_cardigan_is_knitwear_in_mid_not_a_coat():
    _, r = run(9, UNDER, POLO, CARDI, JEANS, SNEAK, hi=14)
    best = r.outfits[0].picks
    assert best["mid"] == CARDI["id"] and not best["outer"], best


def test_the_chooser_is_only_offered_outfits_with_the_undershirt_when_one_fits():
    d, r = run(6, *OFFICE, hi=19, p=prefs("office"), rain=80, isRain=True)
    assert all(o.picks["inner"] == UNDER["id"] for o in r.outfits), [o.picks for o in r.outfits]


def test_the_same_garments_in_other_slots_are_one_option():
    _, r = run(12, UNDER, POLO, CARDI, JEANS, SNEAK, hi=16)
    looks = [frozenset(o.picks.values()) for o in r.outfits]
    assert len(looks) == len(set(looks)), [o.picks for o in r.outfits]


def test_every_option_differs_in_something_you_would_see():
    for args in ((6, *OFFICE), (12, UNDER, POLO, CARDI, JEANS, SNEAK, BROWN_BELT)):
        _, r = run(*args, hi=19, p=prefs("office"))
        for i, a in enumerate(r.outfits):
            for b in r.outfits[i + 1:]:
                assert any(a.picks.get(s) != b.picks.get(s) for s in funnel.VISIBLE), (a.picks, b.picks)


def test_a_black_belt_never_goes_with_brown_shoes():
    ctx = strict(14, LOAFERS, BLACK_BELT, BROWN_BELT, hi=20)
    assert funnel.clash(ctx, {"footwear": LOAFERS["id"], "accessories": BLACK_BELT["id"]}) == "belt"
    assert funnel.clash(ctx, {"footwear": LOAFERS["id"], "accessories": BROWN_BELT["id"]}) is None


def test_an_outfit_without_the_undershirt_is_not_offered_when_one_fits():
    """The oxford takes the thermal under it, so every oxford outfit wears it; a tee
    never does (user, 2026-10-24: "No undershirt rule is for T-shirt and not shirts")."""
    _, r = run(3, INNER_LS, TEE, OXFORD, MERINO, PARKA, CHINOS, LOAFERS, hi=9)
    assert r.outfits
    for o in r.outfits:
        assert o.picks["inner"] == (None if o.picks["base"] == TEE["id"] else INNER_LS["id"]), o.picks
