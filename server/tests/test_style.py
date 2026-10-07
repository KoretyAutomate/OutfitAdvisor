"""Style: rules (style.py), the stylist (stylist.py) and the wearer's look votes.

User, 2026-10-07: "I'm not sure if today's recommendation is looking fashionable ...
build all 3. user feedback is important to build."
"""
import json

import pytest
from fastapi.testclient import TestClient

import app as srv
import closet as closet_llm
import llm
import style
import stylist
from picks import Prefs, _index


def g(iid, label, group, typ, roles, *warmth_colors, **kw):
    warmth, colors = warmth_colors
    return {"id": iid, "label": label, "category": roles[0], "group": group, "type": typ,
            "roles": roles, "colors": colors, "warmth": warmth,
            "formality": kw.pop("formality", ["casual"]), "waterproof": False,
            "availableCount": 1, **kw}


RED_TEE = g("itm-redtee001", "red tee", "tops", "t_shirt", ["base"], 2, ["red"])
WHITE_TEE = g("itm-whtee0001", "white tee", "tops", "t_shirt", ["base"], 2, ["white"])
GREEN_CARDI = g("itm-grncard01", "green cardigan", "tops", "cardigan", ["mid"], 3, ["green"])
NAVY_CARDI = g("itm-navcard01", "navy cardigan", "tops", "cardigan", ["mid"], 3, ["navy"])
YELLOW_PANTS = g("itm-yelpant01", "yellow chinos", "bottoms", "trousers", ["bottoms"], 2,
                 ["yellow"])
JEANS = g("itm-jeans0001", "blue jeans", "bottoms", "jeans", ["bottoms"], 2, ["blue"])
STRIPE_SHIRT = g("itm-strshrt1", "striped oxford shirt", "tops", "shirt", ["base"], 2, ["blue"])
PLAID_JACKET = g("itm-pldjack1", "plaid jacket", "outerwear", "jacket", ["outer"], 3, ["grey"])
NAVY_JACKET = g("itm-navjack1", "navy jacket", "outerwear", "jacket", ["outer"], 3, ["navy"])
JOGGERS = g("itm-joggers01", "grey joggers", "bottoms", "trousers", ["bottoms"], 2, ["grey"],
            formality=["active"])
CHINOS = g("itm-chinos001", "beige chinos", "bottoms", "trousers", ["bottoms"], 2, ["beige"],
           formality=["casual", "smart"])
SNEAK = g("itm-sneaker01", "white sneakers", "footwear", "sneakers", ["footwear"], 2, ["white"])


def ctx(*items, style_="casual", disliked=(), plan=14, peak=20, shown=None):
    wd = _index(list(items))
    look = style.Look(style_, "man", tuple(disliked))
    return style.Ctx(wd, plan, peak, (), shown or {}, look)


# ── what a garment is ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("item,want", [
    ({"label": "striped oxford shirt"}, "striped"),
    ({"label": "plaid flannel"}, "checked"),
    ({"label": "ボーダーT"}, "striped"),
    ({"label": "floral dress"}, "print"),
    ({"label": "navy tee"}, None),
    ({"label": "striped tee", "pattern": "solid"}, "solid"),
])
def test_pattern_is_stated_or_read_off_the_name(item, want):
    assert style.pattern_of(item) == want


@pytest.mark.parametrize("item,want", [
    ({"colors": ["red", "white"]}, "red"),
    ({"colors": ["navy"]}, None),
    ({"colors": ["burgundy"]}, None),
    ({"colors": ["blue"], "type": "jeans"}, None),     # denim is denim
    ({"colors": ["紺"]}, None),                         # unknown word: never an accent
    ({"colors": ["multi"]}, None),
    ({"colors": []}, None),
])
def test_accent_is_the_main_colour_and_unknowns_are_neutral(item, want):
    assert style.accent_of(item) == want


# ── the rules ──────────────────────────────────────────────────────────────────

def test_three_accent_colours_is_one_too_many_and_the_mid_changes():
    c = ctx(RED_TEE, GREEN_CARDI, YELLOW_PANTS, NAVY_CARDI)
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    assert style.violations(picks, c.wd.by_item, c.look)
    done = style.repair(c, picks, set())
    assert picks["mid"] == NAVY_CARDI["id"] and picks["base"] == RED_TEE["id"]
    assert done == [("mid", NAVY_CARDI["id"], GREEN_CARDI["id"], "fewer colours together")]


def test_two_patterns_keep_one():
    c = ctx(STRIPE_SHIRT, PLAID_JACKET, NAVY_JACKET, CHINOS)
    picks = {"base": STRIPE_SHIRT["id"], "outer": PLAID_JACKET["id"], "bottoms": CHINOS["id"]}
    style.repair(c, picks, set())
    assert picks["outer"] == NAVY_JACKET["id"] and picks["base"] == STRIPE_SHIRT["id"]


def test_joggers_on_a_smart_day_are_swapped_but_kept_on_a_casual_one():
    picks = {"base": WHITE_TEE["id"], "bottoms": JOGGERS["id"]}
    style.repair(ctx(WHITE_TEE, JOGGERS, CHINOS), picks, set())
    assert picks["bottoms"] == JOGGERS["id"]
    style.repair(ctx(WHITE_TEE, JOGGERS, CHINOS, style_="smart"), picks, set())
    assert picks["bottoms"] == CHINOS["id"]


def test_a_tee_under_a_jacket_is_fine_on_a_smart_day():
    """Only the outermost top is judged — smart-casual is a tee under a blazer."""
    tee = {**WHITE_TEE, "formality": ["casual", "active"]}
    jacket = {**NAVY_JACKET, "formality": ["casual", "smart"]}
    picks = {"base": tee["id"], "outer": jacket["id"], "bottoms": CHINOS["id"]}
    c = ctx(tee, jacket, CHINOS, style_="smart")
    assert style.violations(picks, c.wd.by_item, c.look) == []


def test_a_pair_voted_down_is_changed():
    c = ctx(WHITE_TEE, JEANS, CHINOS, disliked=((WHITE_TEE["id"], JEANS["id"]),))
    picks = {"base": WHITE_TEE["id"], "bottoms": JEANS["id"]}
    style.repair(c, picks, set())
    assert picks["bottoms"] == CHINOS["id"]


def test_with_nothing_better_owned_the_outfit_is_kept():
    c = ctx(RED_TEE, GREEN_CARDI, YELLOW_PANTS)
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    assert style.repair(c, picks, set()) == []
    assert picks["mid"] == GREEN_CARDI["id"]


def test_a_swap_never_undoes_the_reroll():
    c = ctx(RED_TEE, GREEN_CARDI, YELLOW_PANTS, NAVY_CARDI, shown={"mid": NAVY_CARDI["id"]})
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    style.repair(c, picks, set())
    assert picks["mid"] == GREEN_CARDI["id"]


def test_a_swap_never_leaves_the_morning_cold():
    thin = {**NAVY_CARDI, "warmth": 1}
    c = ctx(RED_TEE, GREEN_CARDI, YELLOW_PANTS, thin, plan=8, peak=10)
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    style.repair(c, picks, set())
    assert picks["mid"] == GREEN_CARDI["id"]


def test_a_garment_they_keep_choosing_is_changed_last():
    c = ctx(RED_TEE, WHITE_TEE, GREEN_CARDI, NAVY_CARDI, YELLOW_PANTS)
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    style.repair(c, picks, {GREEN_CARDI["id"]})
    assert picks["mid"] == GREEN_CARDI["id"] and picks["base"] == WHITE_TEE["id"]


# ── votes in the prompt ─────────────────────────────────────────────────────────

def test_votes_and_notes_reach_the_prompt_by_handle_only():
    look = style.Look("casual", "man", disliked=(("a-00000001", "b-00000001"),),
                      liked=(("a-00000001", "c-00000001"),), notes=("too many colours",))
    block = style.prompt_block(look, {"a-00000001": "i1", "b-00000001": "i2", "c-00000001": "i3"})
    assert "LIKED these together: i1+i3" in block and "NOT like these together: i1+i2" in block
    assert "too many colours" in block and "a-00000001" not in block


# ── end to end through /advice ──────────────────────────────────────────────────

def _client(monkeypatch, outfit_picks, stylist_reply=None, stylist_on=False):
    seen: dict = {"calls": 0}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        content = messages[0]["content"]
        p = content if isinstance(content, str) else content[0]["text"]
        seen["calls"] += 1
        if p.startswith("You are a personal stylist"):
            seen["stylist"] = p
            return json.dumps(stylist_reply) if stylist_reply is not None else "nope"
        seen["prompt"] = p
        return json.dumps({"picks": {"inner": None, "base": None, "mid": None, "outer": None,
                                     "bottoms": None, "footwear": None, "accessories": None,
                                     **outfit_picks},
                           "bullets": ["Base: the top", "Bottoms: the trousers"],
                           "missing": [], "tip": ""})

    async def fake_weather(lat, lon, day):
        return {"date": "2026-10-07", "timezone": "America/New_York", "code": 1,
                "emoji": "🌤", "desc": "Clear", "lo": 14, "hi": 20, "swing": 6,
                "feelsLo": 14, "feelsHi": 20, "rain": 0, "wind": 2, "morning": 14,
                "midday": 19, "evening": 17, "isSnow": False, "isRain": False}
    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    monkeypatch.setenv("OUTFIT_STYLIST", "1" if stylist_on else "0")
    c = TestClient(srv.app)
    c.seen = seen
    return c


def test_the_rules_run_on_the_real_route_and_say_so(monkeypatch):
    c = _client(monkeypatch, {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"],
                              "bottoms": YELLOW_PANTS["id"], "footwear": SNEAK["id"]})
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [
        RED_TEE, GREEN_CARDI, NAVY_CARDI, YELLOW_PANTS, SNEAK]}).json()
    assert d["picks"]["mid"] == NAVY_CARDI["id"]
    assert "navy cardigan — fewer colours together" in d["outfit_text"]
    assert "your own rules" not in d["outfit_text"]


def test_a_disliked_pair_from_the_phone_is_enforced(monkeypatch):
    c = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JEANS["id"]})
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                "closet": [WHITE_TEE, JEANS, CHINOS, SNEAK],
                                "styleVotes": {"disliked": [[WHITE_TEE["id"], JEANS["id"]]],
                                               "notes": ["too plain"]}}).json()
    assert d["picks"]["bottoms"] == CHINOS["id"]
    assert "too plain" in c.seen["prompt"]


def test_the_stylist_swap_is_applied_when_it_passes_every_check(monkeypatch):
    c = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JOGGERS["id"]},
                stylist_reply={"score": 2, "issue": "joggers look sloppy with that tee",
                               "swap": {"slot": "bottoms", "handle": "@@"}}, stylist_on=True)
    closet = [WHITE_TEE, JOGGERS, CHINOS, SNEAK]
    # the stylist answers with the handle the server gave chinos
    from picks import handles_for
    h = {i: k for k, i in handles_for(closet).items()}[CHINOS["id"]]
    c2 = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JOGGERS["id"]},
                 stylist_reply={"score": 2, "issue": "joggers look sloppy with that tee",
                                "swap": {"slot": "bottoms", "handle": h}}, stylist_on=True)
    d = c2.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet}).json()
    assert d["picks"]["bottoms"] == CHINOS["id"]
    assert "beige chinos — joggers look sloppy with that tee" in d["outfit_text"]
    del c


def test_the_stylist_cannot_break_a_check(monkeypatch):
    """Its swap would undo the re-roll: refused, the outfit stands."""
    closet = [WHITE_TEE, JOGGERS, CHINOS, SNEAK]
    from picks import handles_for
    h = {i: k for k, i in handles_for(closet).items()}[CHINOS["id"]]
    c = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JOGGERS["id"]},
                stylist_reply={"score": 1, "issue": "x", "swap": {"slot": "bottoms", "handle": h}},
                stylist_on=True)
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet,
                                "shown": {"bottoms": CHINOS["id"]}}).json()
    assert d["picks"]["bottoms"] != CHINOS["id"]


def test_a_good_score_changes_nothing_and_a_broken_reply_costs_nothing(monkeypatch):
    closet = [WHITE_TEE, JOGGERS, CHINOS, SNEAK]
    for reply in ({"score": 4, "issue": "", "swap": None}, None):
        c = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JOGGERS["id"]},
                    stylist_reply=reply, stylist_on=True)
        r = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet})
        assert r.status_code == 200 and r.json()["picks"]["bottoms"] == JOGGERS["id"]
        assert "stylist" in c.seen


def test_the_stylist_is_skipped_once_the_request_is_too_old(monkeypatch):
    import time
    look = style.Look("casual", "man", t0=time.monotonic() - stylist.BUDGET_S - 1)
    c = ctx(WHITE_TEE, JOGGERS, CHINOS)
    c = style.Ctx(c.wd, c.plan, c.peak, (), {}, look)
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    called = []

    async def boom(*a, **k):
        called.append(1)
        return "{}"
    monkeypatch.setattr(llm, "_chat", boom)
    import asyncio
    assert asyncio.run(stylist.review(c, {"base": WHITE_TEE["id"]})) is None
    assert called == []


def test_votes_from_an_old_phone_or_malformed_never_cost_the_morning(monkeypatch):
    c = _client(monkeypatch, {"base": WHITE_TEE["id"], "bottoms": JEANS["id"]})
    r = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [WHITE_TEE, JEANS],
                                "styleVotes": {"disliked": "x", "notes": [1, None]}})
    assert r.status_code == 200, r.text
    assert Prefs().look is None


# ── raised by the pre-push reviewer, 2026-10-07 ─────────────────────────────────

def test_a_dress_is_never_swapped_for_a_top_that_leaves_the_legs_bare():
    dress = g("itm-dress0001", "floral dress", "onepiece", "dress", ["base"], 2, ["red"])
    c = ctx(dress, WHITE_TEE, PLAID_JACKET, NAVY_JACKET)
    picks = {"base": dress["id"], "outer": PLAID_JACKET["id"]}
    style.repair(c, picks, set())
    assert picks["base"] == dress["id"]


def test_a_disliked_pair_is_fixed_from_whichever_side_can_change():
    """One pair of trousers, a second shirt: the shirt changes."""
    c = ctx(WHITE_TEE, RED_TEE, JEANS, disliked=((WHITE_TEE["id"], JEANS["id"]),))
    picks = {"base": WHITE_TEE["id"], "bottoms": JEANS["id"]}
    style.repair(c, picks, set())
    assert picks["base"] == RED_TEE["id"] and picks["bottoms"] == JEANS["id"]


def test_two_patterns_are_fixed_from_whichever_side_can_change():
    """No plain jacket owned, a plain shirt is: the shirt changes."""
    plain = g("itm-plnshrt1", "white oxford shirt", "tops", "shirt", ["base"], 2, ["white"])
    c = ctx(STRIPE_SHIRT, plain, PLAID_JACKET, CHINOS)
    picks = {"base": STRIPE_SHIRT["id"], "outer": PLAID_JACKET["id"], "bottoms": CHINOS["id"]}
    style.repair(c, picks, set())
    assert picks["base"] == plain["id"] and picks["outer"] == PLAID_JACKET["id"]


def test_a_colour_fix_never_brings_in_a_pairing_they_voted_down():
    c = ctx(RED_TEE, GREEN_CARDI, YELLOW_PANTS, NAVY_CARDI,
            disliked=((RED_TEE["id"], NAVY_CARDI["id"]),))
    picks = {"base": RED_TEE["id"], "mid": GREEN_CARDI["id"], "bottoms": YELLOW_PANTS["id"]}
    style.repair(c, picks, set())
    assert picks["mid"] != NAVY_CARDI["id"]


def test_on_a_wet_day_the_waterproof_jacket_stays():
    wet_plaid = {**PLAID_JACKET, "waterproof": True}
    base = ctx(STRIPE_SHIRT, wet_plaid, NAVY_JACKET, CHINOS)
    picks = {"base": STRIPE_SHIRT["id"], "outer": wet_plaid["id"], "bottoms": CHINOS["id"]}
    style.repair(style.Ctx(base.wd, 14, 18, (), {}, base.look, True), picks, set())
    assert picks["outer"] == wet_plaid["id"]
    style.repair(base, picks, set())               # dry: the pattern rule may change it
    assert picks["outer"] == NAVY_JACKET["id"]
