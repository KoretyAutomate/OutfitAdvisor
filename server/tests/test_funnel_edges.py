"""The funnel's edge cases, from the code reviews of 2026-10-20 (Codex thread
01a15c48 and the pre-push gate) — each one reproduced first. Split from
test_funnel.py at the 600-line ceiling; the shared garments and helpers live there."""
import asyncio
from dataclasses import replace

import fake_model
import funnel
import picks as pk
import style
from test_funnel import (CHINOS, LOAFERS, MESH, OFFICE, PARKA,
                         REINDEER, WHITE_OX, assert_valid, dress, prefs, run, strict)
from wardrobe_fixtures import (CARDI, DRESS, JACKET, JEANS, OXFORD, POLO, SNEAK, SWEATER, TEE, UNDER, g,
                               weather)

# ── code review, 2026-10-20 (Codex thread 01a15c48) ───────────────────────────────

def test_an_empty_optional_slot_is_no_gap_and_a_dress_gets_no_trousers_line(monkeypatch):
    out, seen = dress(monkeypatch, [OXFORD, CHINOS, LOAFERS], weather(18, 24), prefs(),
                      [fake_model.choice(1, mid="a cardigan (not in your closet yet)")])
    assert out["missing"] == [], "inner, mid, outer, accessories: nothing to buy on a mild day"
    assert "cardigan" not in out["text"]
    out, _ = dress(monkeypatch, [UNDER, DRESS, SNEAK], weather(18, 24), prefs(),
                   [fake_model.choice(1, bottoms="black tights (not in your closet yet)")])
    assert out["picks"]["base"] == DRESS["id"] and "tights" not in out["text"]
    assert "bottoms" not in out["missing"]


def test_a_real_gap_still_gets_its_generic_line(monkeypatch):
    out, seen = dress(monkeypatch, [UNDER, OXFORD, CHINOS], weather(18, 24), prefs(),
                      [fake_model.choice(1, footwear="white leather sneakers (not in your closet yet)")])
    assert "footwear" in out["missing"] and "Nothing they can wear today fits: footwear" in seen["chooser"][0]
    assert "(not in your closet yet)" in out["text"]


def test_snow_boots_banned_only_with_the_jeans_leave_the_sneakers_wearable():
    import rules
    from wardrobe_fixtures import BOOTS
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "boots"}, "b": {"type": "jeans"}}]))
    assert ban
    d, r = run(-3, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, BOOTS, hi=1, isSnow=True, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].picks["footwear"] == SNEAK["id"]


def test_a_cap_never_loses_the_one_legal_outfit():
    """Six white tees banned with the only jeans, a seventh navy one that is not."""
    import rules
    whites = [g(f"wtee{n:05d}", f"white tee {n}", "tops", "t_shirt", ["base"], 1, colors=["white"]) for n in range(6)]
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt", "color": "white"},
                                    "b": {"type": "jeans"}}]))
    assert ban
    d, r = run(20, *whites, navy, JEANS, SNEAK, hi=24, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == navy["id"]


def test_a_reroll_moves_even_when_the_slots_are_full(monkeypatch):
    # Caps small enough that the search's limits, not the wardrobe, decide.
    monkeypatch.setattr(funnel, "CHECKED_CAP", 3)
    monkeypatch.setattr(funnel, "WIDTHS", ((6, 8),))
    tops = [g(f"shirt{n:04d}", f"shirt {n}", "tops", "shirt", ["base", "mid", "outer"], 2) for n in range(6)]
    legs = [g(f"chino{n:04d}", f"chinos {n}", "bottoms", "trousers", ["bottoms"], 3) for n in range(6)]
    shoes = [g(f"loafr{n:04d}", f"loafers {n}", "footwear", "loafers", ["footwear"], 2) for n in range(6)]
    shown = {"base": tops[0]["id"], "bottoms": legs[0]["id"], "footwear": shoes[0]["id"]}
    closet = [{**tops[0], "_ago": None}, *[{**t, "_ago": 0} for t in tops[1:]], *legs, *shoes]
    _, r = run(18, *closet, hi=24, p=prefs(shown=shown))
    assert r.outfits
    for o in r.outfits:
        assert all(o.picks[s] != shown[s] for s in shown), o.picks


def test_midday_sheds_only_what_the_day_lets_go_and_never_the_only_top():
    d, r = run(9, CARDI, JEANS, SNEAK, hi=20)
    assert r.outfits[0].picks.get("base") is None and r.outfits[0].sheds == ()
    d, r = run(2, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, hi=4)
    assert r.outfits[0].sheds == (), "a cold, flat day keeps everything on"
    d, r = run(6, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, hi=19)
    assert set(r.outfits[0].sheds) == {"outer", "mid"}


def test_a_number_without_words_is_not_text_the_model_wrote(monkeypatch):
    out, _ = dress(monkeypatch, OFFICE, weather(10, 19), prefs("office"), ['{"choice": 1}'])
    assert out["byModel"] is False


def test_the_chooser_never_outlives_its_budget(monkeypatch):
    import time as _t

    import chooser

    async def slow(*a, **kw):
        await asyncio.sleep(30)
    monkeypatch.setattr(chooser, "_chat", slow)
    d, r = run(10, *OFFICE, hi=19, p=prefs("office"))
    t = _t.monotonic()
    assert asyncio.run(chooser.choose(d, r, [], left=3)) is None
    assert _t.monotonic() - t < 5


def test_stated_fits_tags_constrain_a_stated_level_too():
    import garment
    assert garment.level({"type": "trousers", "group": "bottoms", "level": 4, "formality": ["active"]}) == 1
    assert garment.level({"type": "trousers", "group": "bottoms", "level": 1, "formality": ["smart"]}) == 3


def test_a_chunky_knit_never_goes_over_a_polo_or_a_blouse():
    blouse = g("blouse001", "white blouse", "tops", "blouse", ["base", "mid", "outer"], 2, colors=["white"])
    ctx = strict(6, POLO, blouse, TEE, REINDEER, hi=12)
    tank = g("tank00001", "white tank", "tops", "tank", ["base"], 1, colors=["white"])
    ctx = strict(6, POLO, blouse, TEE, REINDEER, tank, DRESS, hi=12)
    for under in (POLO, blouse, tank):
        assert funnel.clash(ctx, {"base": under["id"], "mid": REINDEER["id"]}) == "texture"
    assert funnel.clash(ctx, {"base": DRESS["id"], "mid": REINDEER["id"]}) != "texture", "a jumper over a dress"
    assert funnel.clash(ctx, {"base": TEE["id"], "mid": REINDEER["id"]}) is None


def test_a_search_that_finds_nothing_ends_empty_and_fast():
    """Their rule bans the only top with the only trousers: every outfit misses one of
    them while owning it — so every pass, every width, finds nothing."""
    import time as _t

    import rules
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "jeans"}}]))
    assert ban
    t = _t.monotonic()
    _, r = run(16, TEE, JEANS, SNEAK, hi=22, p=prefs(rules=ban))
    assert r.outfits == []
    assert _t.monotonic() - t < 3


def test_the_seventeenth_candidate_still_counts():
    """Past the wide pass too: sixteen white tees banned with the only jeans."""
    import rules
    whites = [g(f"wtee{n:05d}", f"white tee {n}", "tops", "t_shirt", ["base"], 1, colors=["white"]) for n in range(16)]
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt", "color": "white"},
                                    "b": {"type": "jeans"}}]))
    d, r = run(20, *whites, navy, JEANS, SNEAK, hi=24, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == navy["id"]
    assert not r.outfits[0].relaxed, "the notes say only what it gave up: nothing"


def test_warm_snow_boots_on_a_mild_snowy_day_are_not_demanded():
    from wardrobe_fixtures import BOOTS
    d, r = run(3, UNDER, OXFORD, SWEATER, JACKET, JEANS, SNEAK, BOOTS, hi=15, isSnow=True)
    assert_valid(d, r)
    import check as chk
    if not chk.snow_gear("footwear", {}, d):
        assert any(o.picks["footwear"] == SNEAK["id"] for o in r.outfits)


def test_words_stripped_by_closet_only_are_not_the_model_s(monkeypatch):
    out, _ = dress(monkeypatch, OFFICE, weather(10, 19), prefs("office", closet_only=True),
                   [fake_model.choice(1, tip="Wear a camel overcoat over it.")])
    assert "overcoat" not in out["text"] and out["byModel"] is False


def test_a_strict_outfit_past_the_wide_pass_beats_relaxing_a_rule():
    """Sixteen red tees clash in colour with the green trousers; the seventeenth,
    navy, does not — it is served with no note, before colour gives way."""
    reds = [g(f"rtee{n:05d}", f"red tee {n}", "tops", "t_shirt", ["base"], 1, colors=["red"]) for n in range(16)]
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    green = g("greenpnt1", "green chinos", "bottoms", "trousers", ["bottoms"], 3, colors=["green"])
    white = g("whitesnk1", "white sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["white"])
    d, r = run(20, *reds, navy, green, white, hi=24)
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == navy["id"] and not r.outfits[0].relaxed, r.outfits[0].picks


def test_snow_boots_they_disliked_with_their_only_jeans_leave_the_sneakers():
    from wardrobe_fixtures import BOOTS
    p = replace(pk.Prefs(), look=style.Look("casual", "man", "", disliked=((BOOTS["id"], JEANS["id"]),)))
    d, r = run(-3, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, BOOTS, hi=1, isSnow=True, p=p)
    assert_valid(d, r)
    assert r.outfits[0].picks["footwear"] == SNEAK["id"]


def test_many_shirts_never_crowd_out_the_knit_and_the_undershirt():
    """The pre-push gate's case: six each of shirts, chinos and sneakers at 6-19C."""
    shirts = [g(f"shrt{n:05d}", f"shirt {n}", "tops", "shirt", ["base", "mid", "outer"], 2) for n in range(6)]
    legs = [g(f"chin{n:05d}", f"chinos {n}", "bottoms", "trousers", ["bottoms"], 3) for n in range(6)]
    shoes = [g(f"snk{n:06d}", f"sneakers {n}", "footwear", "sneakers", ["footwear"], 2) for n in range(6)]
    d, r = run(6, *shirts, *legs, *shoes, UNDER, SWEATER, PARKA, hi=19)
    assert_valid(d, r)
    for o in r.outfits:
        assert o.picks["inner"] == UNDER["id"] and o.picks["mid"] == SWEATER["id"], o.picks


def test_the_chooser_hears_their_feedback_and_their_reasons(monkeypatch):
    p = replace(pk.Prefs(skipped=("too warm for the office",)),
                look=style.Look("casual", "man", "office", liked=((WHITE_OX["id"], CHINOS["id"]),),
                                notes=("navy and white suits me",)))
    _, seen = dress(monkeypatch, OFFICE, weather(10, 19), p, [fake_model.choice(1)])
    prompt = seen["chooser"][0]
    assert "they LIKED these together" in prompt and "navy and white suits me" in prompt
    assert "too warm for the office" in prompt
    assert WHITE_OX["id"] not in prompt, "handles, never ids"


def test_a_cold_day_that_warms_six_degrees_keeps_the_coat():
    d, r = run(-5, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, hi=1)
    assert "outer" not in r.outfits[0].sheds


def test_the_damp_shoes_note_survives_closet_only(monkeypatch):
    out, _ = dress(monkeypatch, [UNDER, WHITE_OX, CHINOS, MESH], weather(14, 20, rain=90, isRain=True),
                   prefs(closet_only=True), [fake_model.choice(1, tip="Wear a camel overcoat.")])
    assert "damp shoes" in out["tip"] and "damp shoes" in out["text"]
    assert "overcoat" not in out["text"]


def test_waterproof_mesh_trainers_are_fine_in_the_rain():
    wp = {**MESH, "waterproof": True}
    d, r = run(14, UNDER, WHITE_OX, CHINOS, wp, hi=20, rain=90, isRain=True)
    assert r.outfits[0].picks["footwear"] == MESH["id"] and "wet" not in r.outfits[0].relaxed


def test_a_jumpsuit_is_not_a_suit():
    import garment
    assert garment.level({"label": "denim jumpsuit", "type": "jumpsuit", "group": "onepiece"}) == 3
    assert garment.level({"label": "grey tracksuit", "type": "trousers", "group": "bottoms"}) == 1
    assert garment.level({"label": "navy suit trousers", "type": "trousers", "group": "bottoms"}) == 5


def test_a_reroll_widens_before_it_repeats():
    """Five banned white tees and the shown grey one fill the first six; the navy one,
    worn today, is seventh — and is what a re-roll must show."""
    import rules
    whites = [g(f"wtee{n:05d}", f"white tee {n}", "tops", "t_shirt", ["base"], 1, colors=["white"]) for n in range(5)]
    grey = g("gtee00001", "grey tee", "tops", "t_shirt", ["base"], 1, colors=["grey"])
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt", "color": "white"},
                                    "b": {"type": "jeans"}}]))
    d, r = run(20, *whites, grey, navy, JEANS, SNEAK, hi=24, p=prefs(rules=ban, shown={"base": grey["id"]}))
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == navy["id"], r.outfits[0].picks


def test_a_polo_never_goes_over_a_sweater():
    ls_polo = g("lspolo001", "navy long-sleeve polo", "tops", "polo", ["base", "mid", "outer"], 2, sleeve="long")
    d, r = run(3, UNDER, ls_polo, REINDEER, PARKA, JEANS, SNEAK, hi=6)
    assert_valid(d, r)
    for o in r.outfits:
        assert not (o.picks.get("base") == REINDEER["id"] and o.picks.get("mid") == ls_polo["id"]), o.picks
    ctx = strict(3, ls_polo, REINDEER, hi=6)
    assert funnel.clash(ctx, {"base": REINDEER["id"], "mid": ls_polo["id"]}) == "stack"


def test_dark_jeans_follow_their_fits_tags_too():
    import garment
    assert garment.level({"label": "dark indigo jeans", "type": "jeans", "group": "bottoms",
                          "formality": ["active"]}) == 1


def test_a_reroll_widens_within_a_relaxed_step():
    """Green trousers and red shoes: colour gives way for every outfit. Five white tees
    are banned with the trousers, the grey one is on screen, the navy one — worn today
    — is seventh: the narrow colour-relaxed pass must not settle for the grey again."""
    import rules
    whites = [g(f"wtee{n:05d}", f"white tee {n}", "tops", "t_shirt", ["base"], 1, colors=["white"]) for n in range(5)]
    grey = g("gtee00001", "grey tee", "tops", "t_shirt", ["base"], 1, colors=["grey"])
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    green = g("grnpnt001", "green trousers", "bottoms", "trousers", ["bottoms"], 3, colors=["green"])
    red = g("redsnk001", "red sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["red"])
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt", "color": "white"},
                                    "b": {"type": "trousers"}}]))
    d, r = run(20, *whites, grey, navy, green, red, hi=24, p=prefs(rules=ban, shown={"base": grey["id"]}))
    assert_valid(d, r)
    assert "colour" in r.outfits[0].relaxed
    assert r.outfits[0].picks["base"] == navy["id"], r.outfits[0].picks


def test_a_coat_they_voted_down_with_their_only_trousers_is_not_demanded():
    p = replace(pk.Prefs(), look=style.Look("casual", "man", "", disliked=((PARKA["id"], JEANS["id"]),)))
    d, r = run(3, UNDER, OXFORD, SWEATER, PARKA, JEANS, SNEAK, hi=6, p=p)
    assert_valid(d, r)
    assert all(o.picks.get("outer") != PARKA["id"] for o in r.outfits)


def test_a_cardigan_can_be_the_top_when_the_tee_is_banned_with_it():
    import rules
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "cardigan"}}]))
    d, r = run(9, TEE, CARDI, JEANS, SNEAK, hi=15, p=prefs(rules=ban))
    assert_valid(d, r)
    assert any(CARDI["id"] in o.picks.values() for o in r.outfits)


def test_the_dress_level_note_is_true_both_ways():
    formal = g("oxshoe001", "black oxford shoes", "footwear", "dress_shoes", ["footwear"], 2, colors=["black"], level=5)
    d, r = run(18, UNDER, TEE, JEANS, formal, hi=24)
    assert r.outfits and r.outfits[0].relaxed
    for n in funnel.notes(r.outfits[0].relaxed):
        assert "relaxed" not in n, n


def test_a_usable_undershirt_past_the_first_six_is_found():
    longs = [g(f"lsin{n:05d}", f"long-sleeve undershirt {n}", "underwear", "undershirt", ["inner"], 1, sleeve="long")
             for n in range(6)]
    short = {**g("ssin00001", "white crew undershirt", "underwear", "undershirt", ["inner"], 1, sleeve="short"),
             "_ago": 0}
    d, r = run(20, *longs, short, TEE, JEANS, SNEAK, hi=24)
    assert_valid(d, r)
    assert r.outfits[0].picks["inner"] == short["id"], r.outfits[0].picks


def test_a_turned_down_look_is_not_offered_again_in_other_slots(monkeypatch):
    out, seen = dress(monkeypatch, [CARDI, JEANS, SNEAK], weather(9, 19), prefs(),
                      [fake_model.choice(0, reason="no"), fake_model.choice(1)])
    assert len(seen["chooser"]) == 1, "nothing new to offer: no second call on the same clothes"


def test_a_sweater_too_warm_to_wear_does_not_make_the_tee_cold():
    hot_knit = g("hotknit01", "heavy wool sweater", "tops", "sweater", ["base", "mid", "outer"], 5)
    d, r = run(14, TEE, hot_knit, JEANS, SNEAK, hi=20)
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == TEE["id"]


def test_a_short_sleeved_shirt_never_goes_over_a_cardigan():
    ss = g("ssshirt01", "short-sleeved shirt", "tops", "shirt", ["base", "mid", "outer"], 1, sleeve="short")
    d, r = run(9, TEE, CARDI, ss, JEANS, SNEAK, hi=13)
    assert_valid(d, r)
    for o in r.outfits:
        assert not (o.picks.get("mid") == CARDI["id"] and o.picks.get("outer") == ss["id"]), o.picks
    ctx = strict(9, TEE, CARDI, ss, hi=13)
    assert funnel.clash(ctx, {"base": TEE["id"], "mid": CARDI["id"], "outer": ss["id"]}) == "stack"


def test_a_blazer_or_open_shirt_as_outer_counts_for_the_trousers():
    blazer = g("blazer001", "navy blazer", "outerwear", "blazer", ["mid", "outer"], 2, formality=["smart"])
    joggers = g("jogger001", "grey joggers", "bottoms", "trousers", ["bottoms"], 2, colors=["grey"])
    ctx = strict(10, TEE, blazer, joggers, LOAFERS, hi=16)
    assert funnel.clash(ctx, {"base": TEE["id"], "outer": blazer["id"], "bottoms": joggers["id"]}) == "register"


def test_joggers_on_a_smart_office_day_are_served_with_a_note_not_refused():
    joggers = g("jogger001", "grey joggers", "bottoms", "trousers", ["bottoms"], 2, colors=["grey"])
    d, r = run(18, OXFORD, joggers, LOAFERS, hi=24, p=prefs("office", "smart"))
    assert_valid(d, r)
    assert r.outfits[0].picks["bottoms"] == joggers["id"] and r.outfits[0].relaxed


def test_the_undershirt_counts_toward_warmth():
    """A warmth-2 undershirt under a warmth-1 tee is warm enough at 14C: the cardigan
    is not needed, and when the cardigan is banned with the jeans the tee outfit stays."""
    import rules
    warm_inner = g("winner001", "white cotton undershirt", "underwear", "undershirt", ["inner"], 2, sleeve="short")
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "cardigan"}, "b": {"type": "jeans"}}]))
    d, r = run(14, warm_inner, TEE, CARDI, JEANS, SNEAK, hi=20, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == TEE["id"] and r.outfits[0].picks["inner"] == warm_inner["id"]


def test_an_outfit_giving_up_more_rules_is_never_offered():
    formal = g("oxshoe001", "black oxford shoes", "footwear", "dress_shoes", ["footwear"], 2, colors=["black"], level=4)
    red = g("redtee001", "red tee", "tops", "t_shirt", ["base"], 1, colors=["red"])
    green = g("grnchin01", "green chinos", "bottoms", "trousers", ["bottoms"], 3, colors=["green"])
    d, r = run(20, TEE, red, green, formal, hi=24)
    assert_valid(d, r)
    assert all(o.relaxed == r.outfits[0].relaxed for o in r.outfits), [o.relaxed for o in r.outfits]
    assert all(o.picks["base"] == TEE["id"] for o in r.outfits)


def test_a_dress_is_worn_rather_than_bare_legs():
    green = g("grnsnk001", "green sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["green"])
    d, r = run(14, DRESS, CARDI, green, hi=20)
    assert_valid(d, r)
    assert all(o.picks["base"] == DRESS["id"] for o in r.outfits), [o.picks for o in r.outfits]


def test_fewer_rules_given_up_ranks_before_the_cap(monkeypatch):
    monkeypatch.setattr(funnel, "CHECKED_CAP", 4)
    formal = [g(f"oxsh{n:05d}", f"black oxford shoes {n}", "footwear", "dress_shoes", ["footwear"], 2,
                colors=["black"], level=4) for n in range(8)]
    greens = [g(f"gchn{n:05d}", f"green chinos {n}", "bottoms", "trousers", ["bottoms"], 3, colors=["green"])
              for n in range(8)]
    reds = [g(f"rtee{n:05d}", f"red tee {n}", "tops", "t_shirt", ["base"], 1, colors=["red"]) for n in range(2)]
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    d, r = run(20, *reds, navy, *greens, *formal, hi=24)
    assert_valid(d, r)
    assert all(o.picks["base"] == navy["id"] for o in r.outfits), [o.relaxed for o in r.outfits]
