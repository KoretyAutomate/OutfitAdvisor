"""Purchase suggestions, and the evidence they are argued from (2026-08-27).

The user asked for a weekly review that says what is worth adding. The temptation
is to ask a model "what should they buy?" — a model asked that always has an
answer, and the answer is a catalogue: plausible, generic, and indifferent to
whether the person was ever actually cold.

So the design is the one the PPK week and the rules engine both arrived at. The
phone records what actually went wrong — the slots the advisor could not fill and
the weather on those mornings — and the model argues from that. These tests cover
what makes the evidence trustworthy; the wording is the model's job.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import app as app_mod
import closet as closet_mod

client = TestClient(app_mod.app)

ITEM = {"id": "itm-tee-0001", "label": "white t-shirt", "category": "base",
        "group": "tops", "type": "t_shirt", "roles": ["base"], "colors": ["white"],
        "warmth": 1, "formality": ["casual"], "waterproof": False, "availableCount": 2}
COLD = {"lo": 2, "hi": 9, "feelsLo": 0, "feelsHi": 7, "desc": "Cold", "rain": 10,
        "wind": 4, "morning": 3, "midday": 8, "evening": 5, "swing": 7,
        "isRain": False, "isSnow": False, "code": 3}


def test_a_gap_must_name_a_real_slot():
    """A slot this app does not have is a gap that could never be filled."""
    r = client.post("/shopping", json={"gaps": [{"slot": "elbow", "n": 3, "loC": 2, "hiC": 9}]})
    assert r.status_code == 422


@pytest.mark.parametrize("bad", [
    {"slot": "outer", "n": 0, "loC": 2, "hiC": 9},        # a gap on no mornings
    {"slot": "outer", "n": 3, "loC": -99, "hiC": 9},      # not a temperature
    {"slot": "outer", "n": 100000, "loC": 2, "hiC": 9},   # more mornings than exist
])
def test_implausible_evidence_is_refused(bad):
    """The evidence IS the argument, so nonsense in it is refused at the door."""
    assert client.post("/shopping", json={"gaps": [bad]}).status_code == 422


def test_the_evidence_list_is_bounded():
    many = [{"slot": "outer", "n": 1, "loC": 2, "hiC": 9} for _ in range(50)]
    assert client.post("/shopping", json={"gaps": many}).status_code == 422


# ── "my closet is complete" ────────────────────────────────────────────────────

def test_the_prompt_stops_suggesting_what_they_cannot_wear():
    """With the wardrobe declared complete, a generic suggestion is not a hint.

    It is a garment the user has told us they do not own and cannot put on, so the
    slot is reported empty instead (user, 2026-08-27).
    """
    prompt = closet_mod._closet_prompt(COLD, "man", "casual", [ITEM],
                                       closet_mod.Prefs(closet_only=True))
    assert "Nothing in your closet for this" in prompt
    assert "not in your closet yet" not in prompt, \
        "a complete wardrobe must not be offered garments it does not contain"


def test_by_default_the_helpful_suggestion_stays():
    """Off by default, deliberately.

    A bare "None" told a user with three registered shirts nothing about their legs
    (2026-07-15). That complaint is still valid for anyone who has not finished
    photographing their wardrobe.
    """
    prompt = closet_mod._closet_prompt(COLD, "man", "casual", [ITEM], closet_mod.Prefs())
    assert "not in your closet yet" in prompt


def test_the_model_is_asked_WHY_a_slot_is_empty():
    """"Nothing needed" and "nothing suitable owned" are both null in `picks`.

    They mean opposite things — a warm day versus a hole in the wardrobe — and the
    shopping list is built from the second. Guessing between them would recommend
    buying a coat because it was July.
    """
    prompt = closet_mod._closet_prompt(COLD, "man", "casual", [ITEM], closet_mod.Prefs())
    assert '"missing"' in prompt
    assert "not the ones the weather made unnecessary" in prompt


# ── what comes BACK from the model is validated too ────────────────────────────

def _suggest(monkeypatch, reply):
    """Run shopping_list against a canned model reply.

    asyncio.run rather than pytest-asyncio: this suite has no such plugin, and the
    other wiring tests here drive coroutines the same way.
    """
    import shopping

    async def fake_chat(*a, **k):
        return reply
    monkeypatch.setattr(shopping, "_chat", fake_chat)
    return asyncio.run(shopping.shopping_list(
        [ITEM], [{"slot": "outer", "n": 9, "loC": 2, "hiC": 9}], [], {"tempOffset": -1.5}))


def test_a_suggestion_for_a_slot_the_app_has_no_place_for_is_dropped(monkeypatch):
    """It could not be displayed, and it could never be satisfied."""
    out = _suggest(monkeypatch, '{"suggestions": ['
                         '{"what":"elbow pads","slot":"elbow","why":"x","priority":1},'
                         '{"what":"wool coat","slot":"outer","why":"y","priority":1}],'
                         '"verdict":"ok"}')
    assert [s["slot"] for s in out["suggestions"]] == ["outer"]


def test_a_nameless_suggestion_is_dropped(monkeypatch):
    out = _suggest(monkeypatch, '{"suggestions": ['
                         '{"what":"","slot":"outer","why":"x","priority":1}], "verdict":"v"}')
    assert out["suggestions"] == []


def test_the_list_is_capped_and_the_priority_is_sane(monkeypatch):
    """Five is plenty; a "priority 99" would sort and label wrongly on the phone."""
    many = ",".join(f'{{"what":"coat {i}","slot":"outer","why":"x","priority":99}}'
                    for i in range(9))
    out = _suggest(monkeypatch, f'{{"suggestions": [{many}], "verdict":"v"}}')
    assert len(out["suggestions"]) <= 5
    assert all(1 <= s["priority"] <= 3 for s in out["suggestions"])


def test_no_suggestions_is_a_legitimate_answer(monkeypatch):
    """A wardrobe with no real gaps should be told so, not sold something."""
    out = _suggest(monkeypatch, '{"suggestions": [], "verdict":"Nothing missing."}')
    assert out["suggestions"] == [] and "Nothing missing" in out["verdict"]


def test_a_reply_that_is_not_the_required_shape_yields_nothing(monkeypatch):
    """Better no answer than a half-parsed one presented as advice."""
    assert _suggest(monkeypatch, "sorry, I cannot help with that") is None


def test_the_verdict_ends_on_a_word(monkeypatch):
    """A sentence cut mid-word reads as a bug in the app, not as a long sentence."""
    long = "The wardrobe " + "lacks essential layers and " * 20
    out = _suggest(monkeypatch, f'{{"suggestions": [], "verdict": "{long}"}}')
    assert not out["verdict"].rstrip("…").endswith(" ")
    assert out["verdict"].endswith("…"), "a trimmed verdict should say it was trimmed"
    assert " " in out["verdict"] and not out["verdict"][:-1].endswith("ess")


# ── a slot VALIDATION emptied is a gap too ─────────────────────────────────────

def test_a_slot_we_cleared_ourselves_counts_as_missing():
    """The model only knows about the gaps IT left.

    A slot it filled and this module then cleared — a duplicate, an item in a role
    it cannot play, a garment too thin for the cold, one the wearer has banned —
    means the wardrobe had nothing legal for that slot. That is exactly a gap, and
    because the model believed the slot was filled it never appears in `missing`.
    Without this the slot reads "None needed", the weather takes the blame, and the
    shopping list never hears about it. Raised by the pre-push reviewer, 2026-08-27.
    """
    got = closet_mod._missing_slots(["outer"], {"outer": None, "mid": None, "base": "x"},
                                    {"mid", "base"})
    assert got == ["mid", "outer"]


def test_a_slot_the_model_claims_but_then_fills_is_not_a_gap():
    """Otherwise the phone remembers a hole that was never there, for weeks."""
    assert closet_mod._missing_slots(["base"], {"base": "x"}, set()) == []


def test_bottoms_cleared_under_a_dress_is_not_a_gap():
    """A dress covers the legs. That is a dress, not a hole in the wardrobe."""
    assert closet_mod._missing_slots([], {"bottoms": None, "base": "d1"},
                                     {"bottoms", "base"}) == []


def test_the_slots_come_back_in_wearing_order():
    """The phone lists them; inner-outwards is the order everything else uses."""
    got = closet_mod._missing_slots(["footwear", "inner", "outer"],
                                    {"inner": None, "outer": None, "footwear": None}, set())
    assert got == ["inner", "outer", "footwear"]


def test_junk_from_the_model_is_ignored():
    assert closet_mod._missing_slots(["elbow", None, 7], {"outer": None}, set()) == []
    assert closet_mod._missing_slots(None, {"outer": None}, set()) == []


# ── the promise has to hold when things go wrong ───────────────────────────────

def test_a_failed_generation_does_not_dress_a_complete_closet_from_a_catalogue(monkeypatch):
    """closet_outfit returns None on a malformed reply or an unreachable model.

    The fallback is the rule engine, which dresses from a catalogue and knows
    nothing about this wardrobe. Serving that to someone who has said "only what I
    own" breaks the promise in exactly the case they cannot check — a degraded day,
    where every other signal already looks normal. Raised by the pre-push reviewer.
    """
    async def no_answer(*a, **k):
        return None

    async def fake_weather(*a, **k):
        return {"lo": 2, "hi": 9, "feelsLo": 0, "feelsHi": 7, "desc": "Cold",
                "rain": 10, "wind": 4, "morning": 3, "midday": 8, "evening": 5,
                "swing": 7, "isRain": False, "isSnow": False, "code": 3,
                "emoji": "☁️", "date": "2026-08-27", "timezone": "America/New_York"}

    async def fake_text(*a, **k):
        return "• wear a coat"

    monkeypatch.setattr(app_mod.closet_llm, "closet_outfit", no_answer)
    monkeypatch.setattr(app_mod.weather, "fetch_weather", fake_weather)
    monkeypatch.setattr(app_mod.llm, "outfit_text", fake_text)

    r = client.post("/advice", json={"lat": 40.35, "lon": -74.66, "gender": "man",
                                     "style": "casual", "closetOnly": True,
                                     "closet": [ITEM]})
    assert r.status_code == 200
    body = r.json()
    assert body["closetUsed"] is False
    for slot, value in body["outfit"].items():
        if slot == "tip":
            continue
        assert value.startswith("None"), f"{slot} was filled with {value!r}"
    assert body["missing"] == [], "a failure is not evidence about the wardrobe"


def test_without_the_flag_the_fallback_still_helps(monkeypatch):
    """Anyone who has not declared their wardrobe complete still wants the hint."""
    async def no_answer(*a, **k):
        return None

    async def fake_weather(*a, **k):
        return {"lo": 2, "hi": 9, "feelsLo": 0, "feelsHi": 7, "desc": "Cold",
                "rain": 10, "wind": 4, "morning": 3, "midday": 8, "evening": 5,
                "swing": 7, "isRain": False, "isSnow": False, "code": 3,
                "emoji": "☁️", "date": "2026-08-27", "timezone": "America/New_York"}

    async def fake_text(*a, **k):
        return "• wear a coat"

    monkeypatch.setattr(app_mod.closet_llm, "closet_outfit", no_answer)
    monkeypatch.setattr(app_mod.weather, "fetch_weather", fake_weather)
    monkeypatch.setattr(app_mod.llm, "outfit_text", fake_text)

    body = client.post("/advice", json={"lat": 40.35, "lon": -74.66, "gender": "man",
                                        "style": "casual", "closet": [ITEM]}).json()
    assert any(not str(v).startswith("None")
               for k, v in body["outfit"].items() if k != "tip")
