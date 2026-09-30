"""The outfit as a STACK (layers.py).

User, 2026-09-30, on a 14-23C morning dressed in a long-sleeve tee as the undershirt,
a t-shirt over it and a cardigan over that: "a stupid recommendation which no human
would do". Each garment passed every per-garment check there was; the combination
was never looked at.

The end-to-end test at the bottom replays that morning through the real /advice
route with the model stubbed to give that exact answer.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app as srv
import closet as closet_llm
import layers
import llm
from picks import _index


def g(iid, label, group, typ, roles, warmth, **kw):
    return {"id": iid, "label": label, "category": roles[0], "group": group, "type": typ,
            "roles": roles, "colors": ["white"], "warmth": warmth, "formality": ["casual"],
            "waterproof": False, "availableCount": 1, **kw}


LONG_T = g("itm-longtee1", "white long-T", "underwear", "undershirt", ["inner"], 2)
SHORT_UNDER = g("itm-shortun1", "white undershirt", "underwear", "undershirt", ["inner"], 1,
                sleeve="short")
TEE = g("itm-teeshirt1", "white crew-neck T-shirt", "tops", "t_shirt", ["base"], 1)
LS_SHIRT = g("itm-lsshirt1", "blue oxford shirt", "tops", "shirt", ["base", "mid", "outer"], 2,
             sleeve="long")
SS_CARDI = g("itm-sscardi1", "short sleeve knit cardigan", "tops", "cardigan", ["mid"], 2)
CARDI = g("itm-cardigan1", "grey cardigan", "tops", "cardigan", ["mid"], 3)
JACKET = g("itm-jacket001", "navy jacket", "outerwear", "jacket", ["outer"], 3)
COAT = g("itm-woolcoat1", "wool coat", "outerwear", "coat", ["outer"], 5)
JEANS = g("itm-jeans0001", "jeans", "bottoms", "jeans", ["bottoms"], 2)
SNEAK = g("itm-sneaker01", "white sneakers", "footwear", "sneakers", ["footwear"], 2)


def wd(*items):
    return _index(list(items))


# ── what a garment's sleeve is ──────────────────────────────────────────────────

@pytest.mark.parametrize("label,typ,want", [
    ("white long-T", "undershirt", "long"),
    ("navy long sleeve tee", "t_shirt", "long"),
    ("ロンT ホワイト", None, "long"),
    ("長袖ヒートテック", "thermal", "long"),
    ("white crew-neck T-shirt", "t_shirt", "short"),
    ("半袖シャツ", "shirt", "short"),
    ("black tank", "tank", "none"),
    ("grey cardigan", "cardigan", "long"),
    ("blue oxford shirt", "shirt", None),       # comes both ways: never guessed
    ("heattech", "thermal", None),
])
def test_sleeve_is_read_off_the_name_then_the_kind(label, typ, want):
    assert layers.sleeve_of({"label": label, "type": typ}) == want


def test_a_stated_sleeve_beats_the_name():
    assert layers.sleeve_of({"label": "long-T", "type": "t_shirt", "sleeve": "short"}) == "short"


# ── the sleeve rule ─────────────────────────────────────────────────────────────

def test_a_long_undershirt_under_a_tee_comes_off():
    picks = {"inner": LONG_T["id"], "base": TEE["id"], "bottoms": JEANS["id"]}
    done = layers.tidy(picks, wd(LONG_T, TEE, JEANS), 20, [])
    assert picks["inner"] is None and picks["base"] == TEE["id"]
    assert ("inner", None, "sleeve") in done


def test_a_short_undershirt_is_swapped_in_when_one_is_owned():
    picks = {"inner": LONG_T["id"], "base": TEE["id"]}
    layers.tidy(picks, wd(LONG_T, SHORT_UNDER, TEE), 20, [])
    assert picks["inner"] == SHORT_UNDER["id"]


def test_a_long_undershirt_under_a_long_shirt_stays():
    picks = {"inner": LONG_T["id"], "base": LS_SHIRT["id"], "outer": COAT["id"]}
    assert layers.tidy(picks, wd(LONG_T, LS_SHIRT, COAT), 2, []) == []
    assert picks["inner"] == LONG_T["id"]


def test_the_base_is_never_what_the_sleeve_rule_removes():
    """A long-sleeved shirt under a short-sleeved cardigan: the shirt is the outfit,
    the cardigan goes."""
    picks = {"base": LS_SHIRT["id"], "mid": SS_CARDI["id"]}
    layers.tidy(picks, wd(LS_SHIRT, SS_CARDI), 8, [])
    assert picks["base"] == LS_SHIRT["id"] and picks["mid"] is None


def test_an_unknown_sleeve_never_triggers_the_rule():
    shirt = {**LS_SHIRT, "sleeve": None}
    picks = {"inner": LONG_T["id"], "base": shirt["id"], "outer": COAT["id"]}
    assert layers.sleeve_clashes(picks, wd(LONG_T, shirt, COAT).by_item) == []


# ── the layer budget ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plan,want", [(25, 2), (14, 2), (8, 3), (2, 4), (-10, 4)])
def test_the_budget_follows_the_cold(plan, want):
    assert layers.max_layers({"base": TEE["id"]}, {TEE["id"]: TEE}, plan) == want


def test_three_layers_on_a_mild_morning_sheds_the_undershirt_first():
    short_inner = {**SHORT_UNDER}
    picks = {"inner": short_inner["id"], "base": TEE["id"], "mid": CARDI["id"]}
    done = layers.tidy(picks, wd(short_inner, TEE, CARDI), 14, [])
    assert picks == {"inner": None, "base": TEE["id"], "mid": CARDI["id"]}
    assert done == [("inner", None, "budget")]


def test_the_outer_and_the_base_are_never_shed():
    picks = {"base": TEE["id"], "mid": CARDI["id"], "outer": JACKET["id"]}
    layers.tidy(picks, wd(TEE, CARDI, JACKET), 14, [])
    assert picks["base"] == TEE["id"] and picks["outer"] == JACKET["id"]
    assert picks["mid"] is None


def test_a_cold_morning_keeps_four_layers():
    picks = {"inner": SHORT_UNDER["id"], "base": TEE["id"], "mid": CARDI["id"],
             "outer": COAT["id"]}
    assert layers.tidy(picks, wd(SHORT_UNDER, TEE, CARDI, COAT), 0, []) == []


def test_never_shed_into_the_cold():
    """Over budget, and the undershirt — first in line to go — is the only layer warm
    enough for the morning. It stays; the thin mid layer goes instead."""
    warm_inner = g("itm-thermal01", "heavy thermal", "underwear", "thermal", ["inner"], 3,
                   sleeve="short")
    thin_mid = g("itm-thinmid01", "linen overshirt", "tops", "shirt", ["mid"], 1,
                 sleeve="long")
    picks = {"inner": warm_inner["id"], "base": TEE["id"], "mid": thin_mid["id"]}
    layers.tidy(picks, wd(warm_inner, TEE, thin_mid), 13, [])
    assert picks["inner"] == warm_inner["id"] and picks["mid"] is None


# ── the morning it happened, end to end ─────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    seen: dict = {"n": 0}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        seen["prompt"] = messages[0]["content"]
        seen["n"] += 1
        return json.dumps({
            "picks": {"inner": LONG_T["id"], "base": TEE["id"], "mid": CARDI["id"],
                      "outer": None, "bottoms": JEANS["id"], "footwear": SNEAK["id"],
                      "accessories": None},
            "bullets": ["Inner: the white long-T for warmth",
                        "Base: the white crew-neck T-shirt",
                        "Mid: the grey cardigan for the morning chill",
                        "Bottoms: the jeans", "Footwear: the white sneakers"],
            "missing": [], "tip": "Take the cardigan off by noon."})

    async def fake_weather(lat, lon, day):
        return {"date": "2026-09-30", "timezone": "America/New_York", "code": 1,
                "emoji": "🌤", "desc": "Mainly clear", "lo": 14, "hi": 23, "swing": 9,
                "feelsLo": 14, "feelsHi": 23, "rain": 0, "wind": 2, "morning": 14,
                "midday": 22, "evening": 19, "isSnow": False, "isRain": False}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def test_the_30_september_outfit_is_no_longer_sent(client):
    closet = [LONG_T, TEE, CARDI, JEANS, SNEAK]
    r = client.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["picks"]["inner"] is None
    assert d["picks"]["base"] == TEE["id"] and d["picks"]["mid"] == CARDI["id"]
    # And the prose no longer recommends what was taken off.
    assert "long-T" not in d["outfit_text"]


def test_the_model_is_told_both_rules_and_each_sleeve(client):
    client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                 "closet": [LONG_T, TEE, CARDI, JEANS, SNEAK]})
    p = client.seen["prompt"]
    assert "at most 2 torso layers" in p
    assert "Never put a long-sleeved item under a short-sleeved one" in p
    assert "white long-T (Undershirt / singlet) | long sleeves" in p
    assert "white crew-neck T-shirt (T-shirt) | short sleeves" in p


def test_taking_the_long_t_off_puts_the_warmth_back(client, monkeypatch):
    """What the real model answered three times out of three on the day this shipped:
    long-T + tee, nothing over them. The long-T goes; a tee alone at 14C does not."""
    async def long_t_and_tee(messages, max_tokens, timeout=45, **kw):
        return json.dumps({
            "picks": {"inner": LONG_T["id"], "base": TEE["id"], "mid": None, "outer": None,
                      "bottoms": JEANS["id"], "footwear": SNEAK["id"], "accessories": None},
            "bullets": ["Inner: the white long-T for the morning chill",
                        "Base: the white crew-neck T-shirt", "Mid: None needed",
                        "Outer: None needed", "Bottoms: the jeans",
                        "Footwear: the white sneakers"],
            "missing": [], "tip": "Mild day."})
    monkeypatch.setattr(closet_llm, "_chat", long_t_and_tee)
    r = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [LONG_T, TEE, CARDI, JEANS, SNEAK]})
    d = r.json()
    assert d["picks"]["inner"] is None
    assert d["picks"]["base"] == TEE["id"] and d["picks"]["mid"] == CARDI["id"]
    t = d["outfit_text"]
    assert "grey cardigan" in t and "long-T" not in t
    assert "Mid: None needed" not in t and "Outer: None needed" in t
    assert "your own rules" not in t and "did not go with the rest" in t


def test_rewarm_never_adds_a_clash_or_a_second_layer_budget_breach():
    picks = {"inner": LONG_T["id"], "base": TEE["id"]}
    w = wd(LONG_T, TEE, SS_CARDI, CARDI)
    layers.tidy(picks, w, 14, [])
    assert picks["inner"] is None and picks["mid"] in (CARDI["id"], SS_CARDI["id"])
    assert layers.sleeve_clashes(picks, w.by_item) == []
    assert sum(1 for c in ("inner", "base", "mid", "outer") if picks.get(c)) <= 2


def test_rewarm_skips_a_layer_that_would_clash_itself():
    """Over a long-sleeved base, a short-sleeved cardigan would be a new clash."""
    base = {**LS_SHIRT, "roles": ["base"], "warmth": 1}
    picks = {"base": base["id"]}
    res = layers._rewarm(picks, wd(base, SS_CARDI, CARDI), 14, [])
    assert res == [("mid", CARDI["id"], "warmth")]


@pytest.mark.parametrize("line,gone", [
    ("• No mid-layer is needed as the heat makes a cardigan too warm.", True),
    ("• Mid: None needed", True),
    ("• A cardigan is unnecessary today.", True),
    ("• No outer jacket is required since there is no rain.", False),   # other slot
    ("• White sneakers — no rain, so they stay dry.", False),
])
def test_the_line_calling_the_added_slot_unneeded_goes(line, gone):
    text = layers.with_added(f"• Base: the tee\n{line}", ("mid", CARDI["id"], "warmth"),
                             {CARDI["id"]: CARDI})
    assert (line not in text) is gone
    assert text.startswith("• grey cardigan")
