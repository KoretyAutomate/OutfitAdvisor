"""'A Tokyo trip cannot be survived with 2 pants' (user, 2026-09-07).

A 15-day trip came back with two pairs of bottoms. The prompt caps the model at
two pack entries per category so its JSON stays short; the count rule wanted five;
nothing closed the gap. Pinned here:

  1. the TOP-UP — the list is brought to what the trip needs, from what is owned,
     and never past what is owned;
  2. the WORDING when the closet itself is short — how often to wash, not "you
     don't own";
  3. the TRAVEL DAY — said in the prompt only when the trip is far, and marked
     on day 1 of the plan;
  4. the PLAN — first mornings kept only where they name packed items, in the
     slot of their own category; nothing invented;
  5. the WIRING through /packing.
"""
import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import app as srv
import llm
import packing
import packlist

ANCH = {"warmthScale": "home", "warmthAnchors": [0.7, 12.9, 25.6]}


def item(i, cat, label, count=1, formality=("casual",), typ="chinos"):
    return {"id": f"itm-{i:08d}", "label": label, "category": cat, "group": "bottoms" if cat == "bottoms" else "tops",
            "type": typ, "roles": [cat], "colors": ["navy"], "warmth": 2, "formality": list(formality),
            "waterproof": False, "availableCount": count, **ANCH}


BOTTOMS = [item(1, "bottoms", "navy chinos"), item(2, "bottoms", "grey chinos"),
           item(3, "bottoms", "dark jeans", typ="jeans"),
           item(4, "bottoms", "black trousers", formality=("smart",), typ="trousers"),
           item(5, "bottoms", "khaki chinos")]
TOPS = [item(10 + k, "base", f"tee {k}", typ="t_shirt") for k in range(8)]
SHOES = [item(30, "footwear", "white sneakers", typ="sneakers")]


def packed(*ids, qty=1):
    by = {i["id"]: i for i in BOTTOMS + TOPS + SHOES}
    return [{"id": i, "category": by[i]["category"], "label": by[i]["label"], "qty": qty, "why": "x"} for i in ids]


def days(n, start="2026-10-12"):
    d0 = dt.date.fromisoformat(start)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "lo": 14, "hi": 22, "desc": "Clear",
             "rain": 10, "wind": 3, "code": 1, "emoji": "🌤️"} for i in range(n)]


# ── 1. the top-up ─────────────────────────────────────────────────────────────

def test_the_day_that_started_this():
    """15 days, five pairs owned, the model packed two → five leave."""
    pack = packed("itm-00000001", "itm-00000002")
    out = packing.top_up(pack, BOTTOMS + TOPS + SHOES, 15, ["casual"])
    assert sum(p["qty"] for p in out if p["category"] == "bottoms") == 5


def test_never_more_than_is_owned():
    pack = packed("itm-00000001")
    out = packing.top_up(pack, BOTTOMS[:2] + SHOES, 15, ["casual"])
    assert sum(p["qty"] for p in out if p["category"] == "bottoms") == 2, "two owned, two go"


def test_a_second_pair_of_the_same_trousers_goes_first():
    two = dict(BOTTOMS[0], availableCount=2)
    pack = packed("itm-00000001")
    out = packing.top_up(pack, [two, BOTTOMS[1]] + SHOES, 6, ["casual"])
    # need ceil(6/3)=2: the packed chinos' second pair is used before a new item
    assert out[0]["id"] == "itm-00000001" and out[0]["qty"] == 2
    assert not any(p["id"] == "itm-00000002" for p in out)


def test_the_trips_register_decides_who_joins():
    pack = packed("itm-00000001")
    out = packing.top_up(pack, BOTTOMS + SHOES, 6, ["smart"])
    added = [p["id"] for p in out if p["id"] != "itm-00000001"]
    assert added[0] == "itm-00000004", "the smart trousers join a smart trip first"


def test_a_full_list_is_left_alone():
    pack = packed("itm-00000001", "itm-00000002")
    before = [dict(p) for p in pack]
    assert packing.top_up(pack, BOTTOMS + SHOES, 4, ["casual"]) == before


def test_a_winter_trip_is_not_topped_up_with_shorts():
    """The reviewer's case: two warm trousers packed, three pairs of shorts owned,
    a 15-day trip at -2..6C. The shorts stay home; the shortfall counts only what
    suits the weather."""
    warm = [dict(item(41, "bottoms", "wool trousers"), warmth=4),
            dict(item(42, "bottoms", "flannel trousers"), warmth=4)]
    shorts = [dict(item(50 + k, "bottoms", f"shorts {k}", typ="shorts"), warmth=1) for k in range(3)]
    pack = [{"id": w["id"], "category": "bottoms", "label": w["label"], "qty": 1, "why": "x"} for w in warm]
    out = packing.top_up(pack, warm + shorts + SHOES, 15, ["casual"], lo=-2, hi=6)
    assert sum(p["qty"] for p in out if p["category"] == "bottoms") == 2
    assert not any("shorts" in p["label"] for p in out)
    assert [i["id"] for i in packing.owned_for(warm + shorts, "bottoms", -2, 6)] == [w["id"] for w in warm]


def test_shorts_the_model_packed_do_not_count_as_winter_trousers():
    """The reviewer's second case: the model put one pair of shorts and one warm
    pair on a winter list; two warm pairs are owned. Both warm pairs must leave —
    the shorts stay on the list but stand in for nothing."""
    warm = [dict(item(41, "bottoms", "wool trousers"), warmth=4),
            dict(item(42, "bottoms", "flannel trousers"), warmth=4)]
    shorts = dict(item(50, "bottoms", "shorts"), warmth=1)
    pack = [{"id": "itm-00000050", "category": "bottoms", "label": "shorts", "qty": 1, "why": "x"},
            {"id": "itm-00000041", "category": "bottoms", "label": "wool trousers", "qty": 1, "why": "x"}]
    out = packing.top_up(pack, warm + [shorts] + SHOES, 15, ["casual"], lo=-2, hi=6)
    ids = {p["id"] for p in out if p["category"] == "bottoms"}
    assert {"itm-00000041", "itm-00000042"} <= ids, "both warm pairs go"


def test_a_wide_range_keeps_both_the_warm_trousers_and_the_shorts():
    """5–25C: each pair has its own days. Requiring one garment to cover both ends
    rejected both and reported a false shortfall (the reviewer's case)."""
    warm = dict(item(41, "bottoms", "wool trousers"), warmth=4)
    shorts = dict(item(50, "bottoms", "shorts", typ="shorts"), warmth=1)
    assert [i["id"] for i in packing.owned_for([warm, shorts], "bottoms", 5, 25)] == [warm["id"], shorts["id"]]


def test_thin_shirts_are_fine_on_a_cold_trip_because_they_are_layered():
    tees = [dict(item(10 + k, "base", f"tee {k}", typ="t_shirt"), warmth=1) for k in range(3)]
    assert len(packing.owned_for(tees, "base", -2, 6)) == 3
    assert len(packing.owned_for(tees, "inner", -2, 6)) == 0, "category is matched, not guessed"


def test_normals_trips_repair_against_the_extremes_the_prompt_packed_for():
    avg = {"mode": "normals", "loMin": 8, "hiMax": 18, "loMinEver": -3, "hiMaxEver": 27}
    assert packing.trip_range(avg) == (-3, 27)
    assert packing.trip_range({"mode": "forecast", "loMin": 8, "hiMax": 18}) == (8, 18)


def test_a_summer_trip_leaves_the_wool_at_home():
    warm = [dict(item(41, "bottoms", "wool trousers"), warmth=5)]
    light = [item(51, "bottoms", "linen trousers"), dict(item(52, "bottoms", "shorts", typ="shorts"), warmth=1)]
    out = packing.top_up([], warm + light, 6, ["casual"], lo=24, hi=33)
    assert {p["id"] for p in out if p["category"] == "bottoms"} == {"itm-00000051", "itm-00000052"}


def test_footwear_never_scales():
    pack = packed("itm-00000030")
    out = packing.top_up(pack, BOTTOMS + SHOES + [item(31, "footwear", "boots", typ="boots")], 15, ["casual"])
    assert sum(p["qty"] for p in out if p["category"] == "footwear") == 1


# ── 2. the wording ────────────────────────────────────────────────────────────

def test_a_short_closet_is_told_how_often_to_wash():
    s = packing.shortfall("bottoms", 2, 5, 15)
    assert s == "2 pairs for 15 days — a wash every ~6 days"
    assert "don't own" not in s and "clean" not in s


def test_nothing_owned_is_still_said_plainly():
    assert packing.shortfall("base", 0, 16, 15).startswith("none in your closet yet")


# ── 3 + 4. travel day and the plan ────────────────────────────────────────────

def test_the_travel_day_is_said_only_when_the_trip_is_far():
    assert packing.is_travel(10800) and not packing.is_travel(40) and not packing.is_travel(None)
    d = days(3)
    summ = {"nDays": 3, "loMin": 14, "hiMax": 22, "rainDays": 0, "mode": "forecast"}
    far = packlist._pack_prompt((d, summ), packlist.Trip("man", ("casual",), "business", travel=True), BOTTOMS)
    near = packlist._pack_prompt((d, summ), packlist.Trip("man", ("casual",), "business", travel=False), BOTTOMS)
    assert "TRAVEL DAYS: day 1 (2026-10-12)" in far and "cabin" in far
    assert "TRAVEL DAYS" not in near
    assert '"plan": [one object per day for the FIRST 3 days' in far


def test_the_plan_keeps_only_packed_items_in_their_own_slot():
    pack = packed("itm-00000001", "itm-00000010", "itm-00000030")
    raw = [
        {"base": "itm-00000010", "bottoms": "itm-00000001", "footwear": "itm-00000030"},
        {"base": "itm-00000011", "bottoms": "itm-00000001"},          # tee 1 was NOT packed
        {"bottoms": "itm-00000010", "footwear": "itm-00000030"},      # a tee in the bottoms slot
        {"base": "itm-00000010"},                                     # a 4th day nobody asked for
    ]
    plan = packing.validate_plan(raw, days(15), pack, travel=True)
    assert [p["date"] for p in plan] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert plan[0]["travel"] is True and plan[1]["travel"] is False
    assert plan[0]["picks"]["base"] == "itm-00000010"
    assert plan[1]["picks"]["base"] is None, "an unpacked id is dropped, not trusted"
    assert plan[2]["picks"]["bottoms"] is None and plan[2]["picks"]["footwear"] == "itm-00000030"


def test_a_day_that_names_nothing_packed_is_dropped_not_invented():
    plan = packing.validate_plan([{"base": "nope"}, {}], days(5), packed("itm-00000001"), travel=False)
    assert plan == []


def test_garbage_plans_are_harmless():
    assert packing.validate_plan("nonsense", days(3), packed("itm-00000001"), travel=False) == []
    assert packing.validate_plan(None, days(3), [], travel=True) == []


# ── 5. the wiring ─────────────────────────────────────────────────────────────

@pytest.fixture
def api(monkeypatch):
    seen: dict = {}

    async def fake_range(lat, lon, start, end):
        d = days(15, start)
        return {"days": d, "summary": {"nDays": 15, "loMin": 14, "hiMax": 22, "swing": 8, "windMax": 3,
                                       "isSnow": False, "isRain": False, "rainDays": 0, "mode": "forecast"}}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        seen.setdefault("prompts", []).append(messages[0]["content"])
        return ('{"pack": [{"id": "itm-00000001", "qty": 1, "why": "a"}, {"id": "itm-00000002", "qty": 1, "why": "b"},'
                ' {"id": "itm-00000010", "qty": 1, "why": "c"}, {"id": "itm-00000030", "qty": 1, "why": "d"}],'
                ' "gaps": [], "bullets": ["Bottoms: chinos", "Shoes: sneakers"],'
                ' "plan": [{"base": "itm-00000010", "bottoms": "itm-00000001", "footwear": "itm-00000030"},'
                ' {"base": "itm-00000010", "bottoms": "itm-00000002"}, {"bottoms": "itm-00000001"}],'
                ' "tip": "Pack light."}')

    monkeypatch.setattr(srv.weather, "fetch_range", fake_range)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def _req(**over):
    start = dt.date.today() + dt.timedelta(days=3)
    body = {"lat": 35.68, "lon": 139.77, "start": start.isoformat(), "end": (start + dt.timedelta(days=14)).isoformat(),
            "type": "business", "gender": "man", "styles": ["smart", "casual"],
            "closet": BOTTOMS + TOPS + SHOES, "travelKm": 10800}
    body.update(over)
    return body


def test_fifteen_days_leave_with_five_pairs(api):
    d = api.post("/packing", json=_req()).json()
    assert d["closetUsed"] is True
    assert sum(p["qty"] for p in d["pack"] if p["category"] == "bottoms") == 5
    assert not any(g["category"] == "bottoms" for g in d["gaps"]), "five owned, five packed — no shortfall"


def test_the_plan_comes_back_with_the_travel_day_first(api):
    d = api.post("/packing", json=_req()).json()
    assert d["travel"] is True
    assert len(d["plan"]) == 3 and d["plan"][0]["travel"] is True
    assert d["plan"][0]["picks"]["bottoms"] == "itm-00000001"
    assert "TRAVEL DAYS" in api.seen["prompts"][0]


def test_a_short_wardrobe_is_told_how_often_to_wash(api):
    d = api.post("/packing", json=_req(closet=BOTTOMS[:2] + TOPS + SHOES)).json()
    assert sum(p["qty"] for p in d["pack"] if p["category"] == "bottoms") == 2
    g = next(g for g in d["gaps"] if g["category"] == "bottoms")
    assert g["need"] == "2 pairs for 15 days — a wash every ~6 days"


def test_an_older_app_without_travelkm_still_works(api):
    body = _req()
    del body["travelKm"]
    d = api.post("/packing", json=body).json()
    assert d["travel"] is False and d["plan"][0]["travel"] is False
    assert "TRAVEL DAYS" not in api.seen["prompts"][0]


def test_a_trip_longer_than_the_forecast_is_packed_for_the_whole_trip(api):
    """The reviewer's case: 30 days starting soon, the forecast reaches ~15. Counts
    and the wash schedule follow the trip, the weather lines follow the forecast."""
    start = dt.date.today() + dt.timedelta(days=3)
    d = api.post("/packing", json=_req(end=(start + dt.timedelta(days=29)).isoformat())).json()
    assert d["trip"]["nDays"] == 30 and d["trip"]["forecastDays"] == 15
    assert sum(p["qty"] for p in d["pack"] if p["category"] == "bottoms") == 5, "all five owned pairs go"
    g = next(g for g in d["gaps"] if g["category"] == "bottoms")
    assert g["need"] == "5 pairs for 30 days — a wash every ~15 days"
    assert "Packing list for a 30-day business trip (the forecast reaches only the first 15" in api.seen["prompts"][0]


def test_the_computed_shortfall_replaces_the_models_gap_for_that_category(monkeypatch):
    """The prompt asks the model for gaps too. When the closet is short, the wash
    schedule is the one answer for that category — not a second, possibly
    contradictory line beside the model's (the reviewer's catch)."""
    async def fake_range(lat, lon, start, end):
        return {"days": days(15, start), "summary": {"nDays": 15, "loMin": 14, "hiMax": 22, "swing": 8, "windMax": 3,
                                                   "isSnow": False, "isRain": False, "rainDays": 0, "mode": "forecast"}}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        return ('{"pack": [{"id": "itm-00000001", "qty": 1, "why": "a"}], '
                '"gaps": [{"category": "bottoms", "need": "buy three more pairs"}, '
                '{"category": "outer", "need": "a rain shell"}], '
                '"bullets": ["Bottoms: chinos"], "tip": "x"}')

    monkeypatch.setattr(srv.weather, "fetch_range", fake_range)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    d = TestClient(srv.app).post("/packing", json=_req(closet=BOTTOMS[:2] + TOPS + SHOES)).json()
    bottoms = [g for g in d["gaps"] if g["category"] == "bottoms"]
    assert len(bottoms) == 1 and bottoms[0]["need"] == "2 pairs for 15 days — a wash every ~6 days"
    assert any(g["category"] == "outer" for g in d["gaps"]), "the model's other gaps stay"


def test_the_plan_is_validated_against_the_final_pack():
    """An id the model put in the plan but not in pack is dropped even though it is
    owned — the plan may only reference what is being packed."""
    pack = packed("itm-00000001")
    plan = packing.validate_plan([{"bottoms": "itm-00000002"}], days(3), pack, travel=False)
    assert plan == []


def test_tip_carries_no_emoji():
    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        return ('{"pack": [{"id": "itm-00000001", "qty": 1, "why": "a"}], "gaps": [], '
                '"bullets": ["Bottoms: chinos"], "tip": "Pack light."}')
    orig = llm._chat
    llm._chat = fake_chat
    try:
        summ = {"nDays": 3, "loMin": 14, "hiMax": 22, "rainDays": 0, "mode": "forecast"}
        r = asyncio.run(packlist.packing_list(days(3), summ, packlist.Trip("man", ("casual",), "vacation"), BOTTOMS))
    finally:
        llm._chat = orig
    assert r["text"].endswith("Tip: Pack light.")
