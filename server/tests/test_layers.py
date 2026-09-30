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



# ── raised by the pre-push reviewer, 2026-09-30 ─────────────────────────────────

def test_a_replacement_undershirt_must_survive_the_afternoon():
    """14C morning, 23C afternoon: a warmth-3 short undershirt is fine at 14 and too
    warm at 23, and an undershirt is worn all day."""
    hot_short = {**SHORT_UNDER, "id": "itm-hotshort1", "warmth": 3}
    picks = {"inner": LONG_T["id"], "base": TEE["id"], "mid": CARDI["id"]}
    layers.tidy(picks, wd(LONG_T, hot_short, TEE, CARDI), 14, [], peak_temp=23)
    assert picks["inner"] != hot_short["id"]


def test_one_swap_settles_both_clashes():
    """Long undershirt under a short base AND a short mid, at 8C where three layers
    fit: the short undershirt swapped in must not be taken off by the stale pair."""
    picks = {"inner": LONG_T["id"], "base": TEE["id"], "mid": SS_CARDI["id"]}
    done = layers.tidy(picks, wd(LONG_T, SHORT_UNDER, TEE, SS_CARDI), 8, [], peak_temp=12)
    assert picks["inner"] == SHORT_UNDER["id"], done
    assert done == [("inner", SHORT_UNDER["id"], "sleeve")]


def test_a_swapped_undershirt_is_named_in_the_advice(client, monkeypatch):
    async def cold_day(lat, lon, day):
        return {"date": "2026-11-20", "timezone": "America/New_York", "code": 3,
                "emoji": "⛅", "desc": "Cloudy", "lo": 6, "hi": 10, "swing": 4,
                "feelsLo": 5, "feelsHi": 9, "rain": 0, "wind": 2, "morning": 7,
                "midday": 10, "evening": 8, "isSnow": False, "isRain": False}
    monkeypatch.setattr(srv.weather, "fetch_weather", cold_day)
    r = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [LONG_T, SHORT_UNDER, TEE, CARDI, JEANS, SNEAK]})
    d = r.json()
    assert d["picks"]["inner"] == SHORT_UNDER["id"]
    assert "white undershirt as the undershirt" in d["outfit_text"]
    assert "long-T" not in d["outfit_text"]


def test_the_note_after_a_repair_says_changed_not_left_out(client):
    r = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [LONG_T, TEE, CARDI, JEANS, SNEAK]})
    assert "Changed a layer that did not go with the rest" in r.json()["outfit_text"]


def test_a_reroll_swap_into_a_clash_is_repaired_by_the_final_pass():
    """A long undershirt under a long shirt is fine; asked for 'something else', the
    re-roll may put a short tee over it. The layer pass runs AFTER the re-roll, so
    what is sent has no clash either way."""
    import reroll
    from picks import Prefs
    picks = {"inner": LONG_T["id"], "base": LS_SHIRT["id"], "bottoms": JEANS["id"]}
    w = wd(LONG_T, LS_SHIRT, {**TEE, "roles": ["base"]}, JEANS)
    reroll.swap_repeats(picks, ["base"], w, 18, [])
    day = {"morning": 18, "lo": 18, "hi": 22}
    layers.hold(picks, day, w, Prefs.of([]), [], None)
    assert layers.sleeve_clashes(picks, w.by_item) == []


def test_a_top_is_never_refused_for_the_undershirt_it_would_clash_with(client, monkeypatch):
    """The model leaves only a long undershirt on the torso; the tee is the only
    top owned. The tee goes on and the undershirt comes off — never the reverse,
    which left nothing above the waist."""
    async def only_the_long_t(messages, max_tokens, timeout=45, **kw):
        return json.dumps({
            "picks": {"inner": LONG_T["id"], "base": None, "mid": None, "outer": None,
                      "bottoms": JEANS["id"], "footwear": SNEAK["id"], "accessories": None},
            "bullets": ["Inner: the white long-T", "Bottoms: the jeans",
                        "Footwear: the white sneakers"], "missing": [], "tip": ""})
    monkeypatch.setattr(closet_llm, "_chat", only_the_long_t)
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [LONG_T, TEE, JEANS, SNEAK]}).json()
    assert d["picks"]["base"] == TEE["id"]
    assert d["picks"]["inner"] is None


def test_an_undershirt_the_outfit_did_not_need_is_not_a_wardrobe_gap(client):
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [LONG_T, TEE, CARDI, JEANS, SNEAK]}).json()
    assert d["picks"]["inner"] is None
    assert "inner" not in (d.get("missing") or [])


def test_a_repair_line_is_dropped_when_a_later_step_replaced_that_garment():
    from picks import Prefs
    red = {**CARDI, "id": "itm-redcardi1", "label": "red cardigan", "colors": ["red"]}
    picks = {"base": TEE["id"], "mid": red["id"]}          # the re-roll put red in
    _, put_on, _ = layers.hold(picks, {"morning": 14, "lo": 14, "hi": 23},
                               wd(TEE, CARDI, red), Prefs.of([]), [], ("mid", CARDI["id"]))
    assert put_on is None


def test_a_swap_and_a_rewarm_are_both_named(client, monkeypatch):
    warm_long = {**LONG_T, "warmth": 3}

    async def cool_morning(lat, lon, day):
        return {"date": "2026-11-02", "timezone": "America/New_York", "code": 3,
                "emoji": "⛅", "desc": "Cloudy", "lo": 8, "hi": 11, "swing": 3,
                "feelsLo": 7, "feelsHi": 10, "rain": 0, "wind": 2, "morning": 8,
                "midday": 11, "evening": 9, "isSnow": False, "isRain": False}

    async def long_and_tee(messages, max_tokens, timeout=45, **kw):
        return json.dumps({
            "picks": {"inner": warm_long["id"], "base": TEE["id"], "mid": None, "outer": None,
                      "bottoms": JEANS["id"], "footwear": SNEAK["id"], "accessories": None},
            "bullets": ["Inner: the white long-T", "Base: the white crew-neck T-shirt",
                        "Mid: None needed", "Bottoms: the jeans", "Footwear: the white sneakers"],
            "missing": [], "tip": ""})
    monkeypatch.setattr(srv.weather, "fetch_weather", cool_morning)
    monkeypatch.setattr(closet_llm, "_chat", long_and_tee)
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [
        warm_long, SHORT_UNDER, TEE, CARDI, JEANS, SNEAK]}).json()
    assert d["picks"]["inner"] == SHORT_UNDER["id"] and d["picks"]["mid"] == CARDI["id"]
    t = d["outfit_text"]
    assert "white undershirt as the undershirt" in t and "grey cardigan — for the morning" in t
    assert "Mid: None needed" not in t


def test_rewarm_replaces_a_mid_layer_that_is_itself_too_thin():
    """8C: the warm long undershirt comes off under the tee, and the linen mid layer
    is not warm enough to be left as the answer — the owned cardigan replaces it."""
    warm_long = {**LONG_T, "warmth": 3}
    linen = g("itm-linenmid1", "linen overshirt", "tops", "shirt", ["mid"], 1, sleeve="long")
    picks = {"inner": warm_long["id"], "base": TEE["id"], "mid": linen["id"]}
    done = layers.tidy(picks, wd(warm_long, TEE, linen, CARDI), 8, [], peak_temp=10)
    assert picks["inner"] is None and picks["mid"] == CARDI["id"], done


def test_a_reroll_swap_the_layer_pass_undid_is_not_described(client, monkeypatch):
    """Re-rolled: the short undershirt was shown, so the re-roll swaps in the long-T;
    under a tee the layer pass swaps the short one back. The text must not announce
    'white long-T instead' over an outfit that does not contain it."""
    async def same_again(messages, max_tokens, timeout=45, **kw):
        return json.dumps({
            "picks": {"inner": SHORT_UNDER["id"], "base": TEE["id"], "mid": CARDI["id"],
                      "outer": None, "bottoms": JEANS["id"], "footwear": SNEAK["id"],
                      "accessories": None},
            "bullets": ["Inner: the white undershirt", "Base: the tee", "Mid: the cardigan",
                        "Bottoms: the jeans", "Footwear: the sneakers"],
            "missing": [], "tip": ""})

    async def cool(lat, lon, day):
        return {"date": "2026-11-02", "timezone": "America/New_York", "code": 3,
                "emoji": "⛅", "desc": "Cloudy", "lo": 8, "hi": 11, "swing": 3,
                "feelsLo": 7, "feelsHi": 10, "rain": 0, "wind": 2, "morning": 8,
                "midday": 11, "evening": 9, "isSnow": False, "isRain": False}
    monkeypatch.setattr(closet_llm, "_chat", same_again)
    monkeypatch.setattr(srv.weather, "fetch_weather", cool)
    d = client.post("/advice", json={
        "lat": 40.3, "lon": -74.6, "closet": [LONG_T, SHORT_UNDER, TEE, CARDI, JEANS, SNEAK],
        "shown": {"inner": SHORT_UNDER["id"]}}).json()
    assert d["picks"]["inner"] == SHORT_UNDER["id"]
    assert "long-T" not in d["outfit_text"], d["outfit_text"]


def test_a_cleared_undershirt_is_not_refilled_by_the_generic_engine(client):
    """closetOnly off: null slots take the rule engine's generic suggestion — which
    put the removed undershirt back on the card as a 'Warm inner'."""
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6, "closetOnly": False,
                                     "closet": [LONG_T, TEE, CARDI, JEANS, SNEAK]}).json()
    assert d["picks"]["inner"] is None
    assert d["outfit"]["inner"] == "None needed", d["outfit"]


def test_a_tip_contradicting_the_added_layer_goes():
    text = "• Base: the tee\n\n💡 No mid-layer is needed today."
    out = layers.with_added(text, ("mid", CARDI["id"], "warmth"), {CARDI["id"]: CARDI})
    assert "No mid-layer" not in out and out.startswith("• grey cardigan")
