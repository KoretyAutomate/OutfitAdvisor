"""More clothing than the day calls for (user, 2026-09-01).

    "Has the temperature setting got reflected? Today's highest is estimated to be
    31 degrees and it's showing items marked as 3. This is horrible."

It had. The anchors were fetched that morning — cold 0.7 / avg 12.9 / hot 25.6 — and
they changed nothing, because every warmth check in this project was a FLOOR.
min_outer_warmth says what the outermost garment must be at LEAST; the heat was only
ever ASKED about, in a prompt flag, and that flag fires on the MORNING temperature,
which was 23C under a 32C afternoon. So the model was never told it was a hot day,
nothing checked what it answered, and a garment the wearer's own scale calls a 13C
garment passed everything there was.

Three things are pinned here:

  1. the CEILING itself, on either scale, and its one invariant — it can never fire
     on a garment the floor requires;
  2. the REPAIR, which swaps before it sheds, sheds only what a day may go without,
     and never leaves anybody undressed to keep them cool;
  3. the WIRING, end to end through the real app, including that an empty mid layer
     on a hot day is the right answer and not a hole in the wardrobe.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as srv
import closet as closet_llm
import llm
import picks as pk
import scale as sc

# The wearer's own year, as /climate measured it on 2026-09-01.
COLD, AVG, HOT = 0.7, 12.9, 25.6
ANCHORS = [COLD, AVG, HOT]


def home(warmth):
    return {"warmth": warmth, "warmthScale": "home", "warmthAnchors": ANCHORS}


# ── the ceiling ───────────────────────────────────────────────────────────────

def test_the_day_that_started_this():
    """23C planned, 32C by the afternoon, and a garment their own scale calls a 13C
    garment. Warmth 3 was the complaint; warmth 1 and 2 are what the day allows."""
    assert not sc.too_warm(home(1), 23.0)
    assert not sc.too_warm(home(2), 23.0)
    assert sc.too_warm(home(3), 23.0)
    assert sc.too_warm(home(4), 23.0)
    assert sc.too_warm(home(5), 23.0)


def test_it_reads_the_garments_own_scale():
    """A wardrobe graded in Oslo and one graded in Singapore are both judged by the
    year they were written against — a level is a sixth of that year, not a fixed
    number of degrees."""
    singapore = {"warmth": 4, "warmthScale": "home", "warmthAnchors": [26.3, 27.1, 27.7]}
    assert sc.too_warm(singapore, 27.7)          # their hottest day wants a 1
    assert not sc.too_warm(singapore, 26.3)      # their coldest wants a 5
    # And a garment with no scale at all is judged by the absolute table, as ever.
    assert sc.too_warm({"warmth": 3}, 23.0)
    assert not sc.too_warm({"warmth": 3}, 10.0)


@pytest.mark.parametrize("anchors", [None, ANCHORS, [26.3, 27.1, 27.7], [-4.0, 6.0, 17.0]])
def test_the_floor_and_the_ceiling_can_never_both_fire(anchors):
    """The one invariant. A garment at exactly the warmth the day REQUIRES must
    never also be too warm for it — a wardrobe where the two checks disagree has no
    right answer, and the repairs would take turns undoing each other."""
    item = (lambda w: {"warmth": w}) if anchors is None else (
        lambda w: {"warmth": w, "warmthScale": "home", "warmthAnchors": anchors})
    for tenths in range(-200, 401):
        t = tenths / 10
        need = sc.min_outer_warmth(t, sc.graded_on(item(3)))
        assert not sc.too_warm(item(need), t), (t, need)


def test_the_cold_is_still_the_cold():
    """Nothing about this may soften the floor: the whole guard exists because a
    warmth-2 shirt went outermost at 4C in Ushuaia."""
    assert not sc.too_warm(home(5), COLD)
    assert not sc.warm_enough(home(2), COLD)


# ── the repair ────────────────────────────────────────────────────────────────

def _wd(by_item, by_roles, by_group=None):
    return pk.Wardrobe(frozenset(by_item), {}, by_roles, by_group or {}, by_item)


def _empty(**kw):
    p = {c: None for c in ("inner", "base", "mid", "outer",
                           "bottoms", "footwear", "accessories")}
    p.update(kw)
    return p


BY_ITEM = {
    "fleece": {"label": "grey fleece", **home(4)},
    "tee": {"label": "white tee", **home(1)},
    "linen": {"label": "linen shirt", **home(1)},
    "wool-trs": {"label": "wool trousers", **home(4)},
    "shorts": {"label": "chino shorts", "colors": ["khaki"], **home(1)},
    "scarf": {"label": "wool scarf", **home(4)},
    # A middling pair: fine for an 18C morning on this scale, wrong for a 32C
    # afternoon. It is the whole difference the peak makes.
    "chinos": {"label": "navy chinos", **home(3)},
}
BY_ROLES = {"fleece": ["mid", "outer"], "tee": ["base"], "linen": ["base"],
            "wool-trs": ["bottoms"], "shorts": ["bottoms"], "scarf": ["accessories"],
            "chinos": ["bottoms"]}


def test_every_slot_is_looked_at_not_only_the_outer_layer():
    """The cold reaches you through the outermost layer; the heat is carried by
    whatever you put on, and a fleece under a shell is exactly as wrong at 30C."""
    picks = _empty(base="tee", mid="fleece", bottoms="wool-trs", accessories="scarf")
    assert pk._too_warm_slots(picks, BY_ITEM, 23.0) == ["mid", "bottoms", "accessories"]


def test_something_cooler_they_own_beats_an_empty_slot():
    picks = _empty(base="tee", bottoms="wool-trs")
    done = pk._cool_down(picks, _wd(BY_ITEM, BY_ROLES), 23.0, [])
    assert picks["bottoms"] == "shorts"
    assert done == [("bottoms", "shorts")]


def test_a_layer_the_heat_makes_pointless_is_simply_shed():
    picks = _empty(base="tee", mid="fleece", accessories="scarf", bottoms="shorts")
    done = pk._cool_down(picks, _wd(BY_ITEM, BY_ROLES), 23.0, [])
    assert picks["mid"] is None and picks["accessories"] is None
    assert dict(done) == {"mid": None, "accessories": None}


def test_nobody_is_undressed_to_keep_them_cool():
    """Overdressed is uncomfortable; undressed is not dressed. Where nothing cooler
    is owned, a slot that cannot simply be empty keeps what it has."""
    only_wool = {"wool-trs": BY_ITEM["wool-trs"], "tee": BY_ITEM["tee"]}
    picks = _empty(base="tee", bottoms="wool-trs")
    done = pk._cool_down(picks, _wd(only_wool, BY_ROLES), 23.0, [])
    assert picks["bottoms"] == "wool-trs"
    assert done == []


def test_the_swap_obeys_the_wearers_own_bans():
    """A cooler garment is not a licence to break a prohibition."""
    rules = [{"kind": "avoid_item", "a": {"color": "khaki"},
              "text": "never the khaki shorts"}]
    picks = _empty(base="tee", bottoms="wool-trs")
    pk._cool_down(picks, _wd(BY_ITEM, BY_ROLES), 23.0, rules)
    assert picks["bottoms"] == "wool-trs"      # banned alternative, so it stands


def test_a_mild_morning_does_not_excuse_the_afternoon():
    """The reviewer's case, and the one that would have kept the bug alive: an 18C
    morning under a 32C high. Judged by the morning alone, warmth-3 trousers pass —
    on exactly the reasoning that produced the complaint. Trousers are worn through
    the afternoon, so the afternoon is what they answer to.
    Raised by the pre-push reviewer, 2026-09-01."""
    picks = _empty(base="tee", bottoms="chinos")
    # Warmth 3 trousers, an 18C morning: their own scale allows a 3 at that hour, so
    # the morning alone lets them through.
    assert pk._too_warm_slots(picks, BY_ITEM, 18.0) == []
    # The afternoon does not. They are worn through it.
    assert pk._too_warm_slots(picks, BY_ITEM, 18.0, 32.0) == ["bottoms"]


def test_a_layer_you_take_off_at_noon_is_judged_by_the_morning():
    """The other half, and why the peak is not simply used for everything. On an 8C
    morning under a 24C afternoon you wear a jacket and take it off — that is what a
    layer IS, and clearing it would send somebody out cold at eight to keep them
    cool at two."""
    picks = _empty(base="tee", mid="fleece", bottoms="wool-trs")
    hot = pk._too_warm_slots(picks, BY_ITEM, 8.0, 24.0)
    assert "mid" not in hot          # kept: it comes off when it warms up
    assert "bottoms" in hot          # cleared: they do not


def test_the_replacement_is_judged_by_the_same_hour():
    """A cooler pair chosen for the afternoon still has to survive the morning — the
    floor never moves off plan_temp."""
    picks = _empty(base="tee", bottoms="chinos")
    pk._cool_down(picks, _wd(BY_ITEM, BY_ROLES), 18.0, [], 32.0)
    assert picks["bottoms"] == "shorts"


def test_a_dress_swapped_in_takes_the_trousers_off():
    """A one-piece covers the legs. _suitable_for judges a trial with the trousers
    already off — so the swap is legal — but only the base was ever written back,
    and the one-piece check has run by then: the answer went out as a dress over
    trousers. Raised by the pre-push reviewer, 2026-09-01."""
    by_item = {"flannel": {"label": "flannel shirt", **home(4)},
               "sundress": {"label": "cotton sundress", **home(1)},
               "wool-trs": BY_ITEM["wool-trs"]}
    by_roles = {"flannel": ["base"], "sundress": ["base"], "wool-trs": ["bottoms"]}
    by_group = {"sundress": "onepiece"}
    picks = _empty(base="flannel", bottoms="wool-trs")
    done = pk._cool_down(picks, _wd(by_item, by_roles, by_group), 23.0, [])
    assert picks["base"] == "sundress"
    assert picks["bottoms"] is None, picks
    assert ("bottoms", None) in done          # reported, so the prose loses them too


def test_a_slot_emptied_by_an_earlier_repair_is_left_empty():
    """The offending slots are listed before any of them is repaired, and one repair
    can empty another. With both the base and the trousers too warm, swapping the
    base for a dress clears the trousers — and the stale list would then put a
    cooler pair straight back under it. Raised by the pre-push reviewer,
    2026-09-01."""
    by_item = {"flannel": {"label": "flannel shirt", **home(4)},
               "sundress": {"label": "cotton sundress", **home(1)},
               "wool-trs": BY_ITEM["wool-trs"], "shorts": BY_ITEM["shorts"]}
    by_roles = {"flannel": ["base"], "sundress": ["base"],
                "wool-trs": ["bottoms"], "shorts": ["bottoms"]}
    picks = _empty(base="flannel", bottoms="wool-trs")
    assert pk._too_warm_slots(picks, by_item, 23.0) == ["base", "bottoms"]
    pk._cool_down(picks, _wd(by_item, by_roles, {"sundress": "onepiece"}), 23.0, [])
    assert picks["base"] == "sundress"
    assert picks["bottoms"] is None, picks     # NOT the shorts, under a dress


def test_an_undershirt_nobody_needs_is_taken_off():
    """An inner layer is optional — the prompt has always said "Inner: None needed"
    on a hot day. Without this, somebody whose only undershirt is a thermal was told
    to wear it at 32C, for want of a cooler one to swap in. Raised by the pre-push
    reviewer, 2026-09-01."""
    by_item = {"thermal": {"label": "merino thermal", **home(5)},
               "tee": BY_ITEM["tee"]}
    by_roles = {"thermal": ["inner"], "tee": ["base"]}
    picks = _empty(inner="thermal", base="tee")
    done = pk._cool_down(picks, _wd(by_item, by_roles), 23.0, [])
    assert picks["inner"] is None
    assert done == [("inner", None)]


def test_the_top_check_prefers_a_cool_top_but_never_bare_skin():
    """_enforce_a_top guarantees a torso is covered. The heat is a preference there
    and never a veto, or a hot day with only a fleece to its name sends somebody
    out in their trousers."""
    picks = _empty(bottoms="shorts")
    assert pk._enforce_a_top(picks, _wd(BY_ITEM, BY_ROLES), 23.0, []) == ("base", "tee")
    only_fleece = {"fleece": BY_ITEM["fleece"]}
    picks = _empty(bottoms="shorts")
    added = pk._enforce_a_top(picks, _wd(only_fleece, BY_ROLES), 23.0, [])
    assert added == ("mid", "fleece")


def test_a_top_added_after_the_heat_pass_is_judged_by_the_same_hour():
    """_enforce_a_top is the last thing that can put a garment INTO the outfit, and
    it runs after the heat pass — so it must not put back what that pass would have
    taken out. A base added here is worn through the afternoon.
    Raised by the pre-push reviewer, 2026-09-01."""
    # linen (w1) and a warm base; the wardrobe lists the warm one first.
    by_item = {"heavy": {"label": "flannel shirt", **home(3)}, "linen": BY_ITEM["linen"]}
    by_roles = {"heavy": ["base"], "linen": ["base"]}
    picks = _empty(bottoms="shorts")
    added = pk._enforce_a_top(picks, _wd(by_item, by_roles), 18.0, [], 32.0)
    assert added == ("base", "linen"), added
    # And with nothing cooler owned it still covers the torso.
    picks = _empty(bottoms="shorts")
    only_heavy = {"heavy": by_item["heavy"]}
    assert pk._enforce_a_top(picks, _wd(only_heavy, by_roles), 18.0, [], 32.0) == ("base", "heavy")


def test_the_gap_check_is_not_made_stricter():
    """_has_suitable_alternative asks whether the wardrobe owns anything LEGAL for a
    slot. A garment that is too warm is still one they own, and refusing it here
    would report a gap for a wardrobe that has an answer."""
    picks = _empty(bottoms="shorts")
    assert pk._has_suitable_alternative("mid", picks, _wd(BY_ITEM, BY_ROLES), 23.0, [])


# ── the prompt ────────────────────────────────────────────────────────────────

def _wx(**kw):
    w = {"date": "2026-09-01", "code": 0, "emoji": "☀️", "desc": "Clear", "lo": 22,
         "hi": 32, "swing": 10, "feelsLo": 22, "feelsHi": 33, "rain": 0, "wind": 2,
         "morning": 23, "midday": 30, "evening": 29, "isSnow": False, "isRain": False}
    w.update(kw)
    return w


def test_a_hot_afternoon_is_a_hot_day_even_from_a_mild_morning():
    """The flag fired on the MORNING, so a 23C start under a 32C afternoon was never
    called hot — the model was told only that there was a big swing."""
    flags = " ".join(llm._weather_flags(_wx()))
    assert "HOT later (32C)" in flags
    assert "None needed" in flags


def test_a_genuinely_hot_morning_still_reads_as_one():
    flags = " ".join(llm._weather_flags(_wx(morning=27, hi=33)))
    assert "Hot day" in flags


def test_a_mild_day_is_not_called_hot():
    flags = " ".join(llm._weather_flags(_wx(morning=14, hi=19, swing=5)))
    assert "HOT" not in flags and "Hot day" not in flags


# ── the wiring ────────────────────────────────────────────────────────────────

TEE = {"id": "itm-00000001", "label": "white tee", "category": "base",
       "group": "tops", "type": "t_shirt", "roles": ["base"], "colors": ["white"],
       "warmth": 1, "formality": ["casual"], "waterproof": False,
       "availableCount": 1, "warmthScale": "home", "warmthAnchors": ANCHORS}
FLEECE = {"id": "itm-00000002", "label": "grey fleece", "category": "mid",
          "group": "tops", "type": "fleece", "roles": ["mid", "outer"],
          "colors": ["grey"], "warmth": 4, "formality": ["casual"],
          "waterproof": False, "availableCount": 1, "warmthScale": "home",
          "warmthAnchors": ANCHORS}
SHORTS = {"id": "itm-00000003", "label": "chino shorts", "category": "bottoms",
          "group": "bottoms", "type": "shorts", "roles": ["bottoms"],
          "colors": ["khaki"], "warmth": 1, "formality": ["casual"],
          "waterproof": False, "availableCount": 1, "warmthScale": "home",
          "warmthAnchors": ANCHORS}


@pytest.fixture
def client(monkeypatch):
    """The real server on the real hot day, with the model insisting on the fleece."""
    seen: dict = {}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        content = messages[0]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        seen.setdefault("prompts", []).append(prompt)
        return ('{"picks": {"inner": null, "base": "itm-00000001", '
                '"mid": "itm-00000002", "outer": null, "bottoms": "itm-00000003", '
                '"footwear": null, "accessories": null}, '
                '"bullets": ["Base: the white tee", "Mid: the grey fleece for later"], '
                '"tip": "Nice day."}')

    async def fake_weather(lat, lon, day):
        return _wx()

    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def test_the_fleece_does_not_survive_a_32C_day(client):
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [TEE, FLEECE, SHORTS]}).json()
    assert d["picks"]["mid"] is None, d["picks"]
    assert d["picks"]["base"] == "itm-00000001"      # still dressed
    assert d["picks"]["bottoms"] == "itm-00000003"


def test_an_empty_mid_layer_on_a_hot_day_is_not_a_wardrobe_gap(client):
    """Recording it would have the shopping list recommending a fleece to somebody
    who was told, correctly, not to wear one."""
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [TEE, FLEECE, SHORTS]}).json()
    assert "mid" not in (d.get("missing") or [])


def test_the_prose_stops_recommending_what_was_taken_off(client):
    """The bullets are what the wearer reads. Nulling the pick and leaving "Mid: the
    grey fleece for later" on screen is the outfit being right and the advice wrong."""
    d = client.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                     "closet": [TEE, FLEECE, SHORTS]}).json()
    assert "fleece" not in d["outfit_text"].lower(), d["outfit_text"]


def test_a_mild_morning_under_a_hot_day_reaches_the_endpoint(monkeypatch):
    """The reviewer's case driven through the real app: 18C at eight, 32C by three.
    The morning alone clears warmth-3 trousers, and they are worn all day.
    Raised by the pre-push reviewer, 2026-09-01."""
    chinos = {"id": "itm-00000004", "label": "navy chinos", "category": "bottoms",
              "group": "bottoms", "type": "trousers", "roles": ["bottoms"],
              "colors": ["navy"], "warmth": 3, "formality": ["casual"],
              "waterproof": False, "availableCount": 1, "warmthScale": "home",
              "warmthAnchors": ANCHORS}

    async def picks_the_chinos(messages, max_tokens, timeout=45, **kw):
        return ('{"picks": {"inner": null, "base": "itm-00000001", "mid": null, '
                '"outer": null, "bottoms": "itm-00000004", "footwear": null, '
                '"accessories": null}, "bullets": ["Bottoms: the navy chinos"], '
                '"tip": "Warm later."}')

    async def mild_morning(lat, lon, day):
        return _wx(morning=18, lo=17, hi=32, midday=30, evening=28, swing=15)

    monkeypatch.setattr(llm, "_chat", picks_the_chinos)
    monkeypatch.setattr(closet_llm, "_chat", picks_the_chinos)
    monkeypatch.setattr(srv.weather, "fetch_weather", mild_morning)
    c = TestClient(srv.app)
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                "closet": [TEE, chinos, SHORTS]}).json()
    assert d["picks"]["bottoms"] == "itm-00000003", d["picks"]   # the shorts


def test_the_top_the_SERVER_adds_is_heat_checked_too(monkeypatch):
    """End to end, because the unit above cannot see whether the peak is actually
    handed to that fallback. The model returns no top at all on an 18C/32C day; the
    server dresses the torso, and must reach past the flannel for the linen."""
    heavy = {"id": "itm-00000005", "label": "flannel shirt", "category": "base",
             "group": "tops", "type": "shirt", "roles": ["base"], "colors": ["red"],
             "warmth": 3, "formality": ["casual"], "waterproof": False,
             "availableCount": 1, "warmthScale": "home", "warmthAnchors": ANCHORS}

    async def no_top(messages, max_tokens, timeout=45, **kw):
        return ('{"picks": {"inner": null, "base": null, "mid": null, "outer": null, '
                '"bottoms": "itm-00000003", "footwear": null, "accessories": null}, '
                '"bullets": ["Bottoms: the chino shorts"], "tip": "Warm later."}')

    async def mild_morning(lat, lon, day):
        return _wx(morning=18, lo=17, hi=32, midday=30, evening=28, swing=15)

    monkeypatch.setattr(llm, "_chat", no_top)
    monkeypatch.setattr(closet_llm, "_chat", no_top)
    monkeypatch.setattr(srv.weather, "fetch_weather", mild_morning)
    c = TestClient(srv.app)
    # heavy is listed FIRST, so a search that does not weigh the heat finds it first.
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                "closet": [heavy, TEE, SHORTS]}).json()
    assert d["picks"]["base"] == "itm-00000001", d["picks"]   # the tee, not the flannel


def test_bare_legs_under_a_dress_are_not_a_wardrobe_gap(monkeypatch):
    """End to end: cooling into a one-piece must not report bottoms as missing, or
    the shopping list recommends trousers to somebody wearing a dress."""
    dress = {"id": "itm-00000006", "label": "cotton sundress", "category": "base",
             "group": "onepiece", "type": "dress", "roles": ["base"],
             "colors": ["blue"], "warmth": 1, "formality": ["casual"],
             "waterproof": False, "availableCount": 1, "warmthScale": "home",
             "warmthAnchors": ANCHORS}
    flannel = {"id": "itm-00000005", "label": "flannel shirt", "category": "base",
               "group": "tops", "type": "shirt", "roles": ["base"], "colors": ["red"],
               "warmth": 4, "formality": ["casual"], "waterproof": False,
               "availableCount": 1, "warmthScale": "home", "warmthAnchors": ANCHORS}
    wool = {"id": "itm-00000007", "label": "wool trousers", "category": "bottoms",
            "group": "bottoms", "type": "trousers", "roles": ["bottoms"],
            "colors": ["grey"], "warmth": 4, "formality": ["smart"],
            "waterproof": False, "availableCount": 1, "warmthScale": "home",
            "warmthAnchors": ANCHORS}

    async def picks_the_flannel(messages, max_tokens, timeout=45, **kw):
        return ('{"picks": {"inner": null, "base": "itm-00000005", "mid": null, '
                '"outer": null, "bottoms": "itm-00000007", "footwear": null, '
                '"accessories": null}, "bullets": ["Base: the flannel shirt", '
                '"Bottoms: the wool trousers"], "tip": "Hot."}')

    async def hot(lat, lon, day):
        return _wx()

    monkeypatch.setattr(llm, "_chat", picks_the_flannel)
    monkeypatch.setattr(closet_llm, "_chat", picks_the_flannel)
    monkeypatch.setattr(srv.weather, "fetch_weather", hot)
    c = TestClient(srv.app)
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                "closet": [flannel, wool, dress]}).json()
    assert d["picks"]["base"] == "itm-00000006", d["picks"]     # the sundress
    assert d["picks"]["bottoms"] is None, d["picks"]            # not under a dress
    assert "bottoms" not in (d.get("missing") or []), d.get("missing")
    assert "trousers" not in d["outfit_text"].lower(), d["outfit_text"]


def test_the_prose_loses_whatever_the_repair_took_off(monkeypatch):
    """Not only the offending garment. Swapping a too-warm base for a dress takes
    the trousers off too — and those trousers were perfectly fine for the day, so
    nothing else would have struck them from the bullets."""
    dress = {"id": "itm-00000006", "label": "cotton sundress", "category": "base",
             "group": "onepiece", "type": "dress", "roles": ["base"],
             "colors": ["blue"], "warmth": 1, "formality": ["casual"],
             "waterproof": False, "availableCount": 1, "warmthScale": "home",
             "warmthAnchors": ANCHORS}
    flannel = {"id": "itm-00000005", "label": "flannel shirt", "category": "base",
               "group": "tops", "type": "shirt", "roles": ["base"], "colors": ["red"],
               "warmth": 4, "formality": ["casual"], "waterproof": False,
               "availableCount": 1, "warmthScale": "home", "warmthAnchors": ANCHORS}

    async def flannel_and_shorts(messages, max_tokens, timeout=45, **kw):
        return ('{"picks": {"inner": null, "base": "itm-00000005", "mid": null, '
                '"outer": null, "bottoms": "itm-00000003", "footwear": null, '
                '"accessories": null}, "bullets": ["Base: the flannel shirt", '
                '"Bottoms: the chino shorts keep you cool"], "tip": "Hot."}')

    async def hot(lat, lon, day):
        return _wx()

    monkeypatch.setattr(llm, "_chat", flannel_and_shorts)
    monkeypatch.setattr(closet_llm, "_chat", flannel_and_shorts)
    monkeypatch.setattr(srv.weather, "fetch_weather", hot)
    c = TestClient(srv.app)
    d = c.post("/advice", json={"lat": 40.3, "lon": -74.6,
                                "closet": [dress, flannel, SHORTS]}).json()
    assert d["picks"]["base"] == "itm-00000006", d["picks"]      # the sundress
    assert d["picks"]["bottoms"] is None, d["picks"]
    assert "shorts" not in d["outfit_text"].lower(), d["outfit_text"]


def test_the_model_is_told_before_it_is_corrected(client):
    """Checked AND asked. The correction costs a retry and only ever fixes the
    picks; the flag is what stops the wrong answer being generated."""
    client.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [TEE, SHORTS]})
    assert any("HOT later" in p for p in client.seen["prompts"])
