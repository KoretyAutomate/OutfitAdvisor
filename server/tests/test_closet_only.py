"""'My closet is complete' — never suggest a garment they do not own.

Split out of test_shopping.py on 2026-08-27, when it crossed the line ceiling.
The tickbox has to hold in the picks, in the PROSE the notification shows, and when
the generation fails — the last being where a broken promise is hardest to notice,
since every other signal still looks normal.
"""

import asyncio

import pytest

from fastapi.testclient import TestClient

import app as app_mod
import closet as closet_mod
import picks as picks_mod

client = TestClient(app_mod.app)

ITEM = {"id": "itm-tee-0001", "label": "white t-shirt", "category": "base",
        "group": "tops", "type": "t_shirt", "roles": ["base"], "colors": ["white"],
        "warmth": 1, "formality": ["casual"], "waterproof": False, "availableCount": 2}
COLD = {"lo": 2, "hi": 9, "feelsLo": 0, "feelsHi": 7, "desc": "Cold", "rain": 10,
        "wind": 4, "morning": 3, "midday": 8, "evening": 5, "swing": 7,
        "isRain": False, "isSnow": False, "code": 3}

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
    # The TEXT as well. outfit_text() writes from a catalogue, and it is the
    # notification's headline — emptying the slots while the prose still says "wear
    # a coat" keeps the promise everywhere except where the user reads it.
    assert "coat" not in body["outfit_text"].lower(), body["outfit_text"]
    assert "Nothing to suggest" in body["outfit_text"]


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


# ── the prose must obey the tickbox too ────────────────────────────────────────

# (phrase, is_label): a LABEL is the name they gave the garment and means it
# wherever it appears; a KIND is a common noun and only means theirs where the
# sentence points at it.
OWNED = [("white t-shirt", True), ("shirt", False),
         ("blue jeans", True), ("jeans", False)]


@pytest.mark.parametrize("line", [
    "Add a light shell for the wind.",
    "Consider a wool overcoat.",           # taxonomy has "coat", model writes "overcoat"
    "A thin merino sweater would help.",
    # One owned mention used to exempt the whole sentence, so the unowned half rode
    # along — in the line the notification shows. Raised by the pre-push reviewer.
    "Add a wool overcoat over your white t-shirt.",
    "Layer the white t-shirt under a fleece.",
])
def test_prose_naming_a_garment_they_do_not_own_is_dropped(line):
    """The structured picks already say the slot is empty.

    Leaving the prose saying "add a light shell" keeps the promise in the data and
    breaks it in the words — and the words are what the notification shows. Raised
    by the pre-push reviewer, 2026-08-27.
    """
    assert picks_mod._names_something_unowned(line, OWNED)


@pytest.mark.parametrize("line", [
    "Start with your white t-shirt.",
    "Blue jeans work today.",
    "The wind will bite this morning.",     # advice, names no garment
    "Nothing in your closet for this.",
    "Take a laptop bag.",                   # "top" must not fire inside "laptop"
    "Stop by the shop first.",
])
def test_prose_that_is_fine_is_kept(line):
    assert not picks_mod._names_something_unowned(line, OWNED)


@pytest.mark.parametrize("line,dropped", [
    ("Start with your oxford.", False),          # their own, named
    ("Wear the white shirt you own.", False),    # their own, pointed at
    ("Your oxford shirt works today.", False),
    ("Add a wool shirt.", True),                 # a DIFFERENT shirt
    ("Consider a wool overcoat.", True),
    ("The wind will bite.", False),              # advice, no garment
])
def test_a_kind_of_garment_only_means_THEIRS_when_pointed_at(line, dropped):
    """Removing the kind unconditionally let recommendations through.

    Owning an Oxford shirt made "Add a wool shirt" read as a reference to it,
    because the word `shirt` was struck out before the line was judged. The
    determiner is what separates the two, and this prose is English. Raised by the
    pre-push reviewer, 2026-08-27.
    """
    owned = [("oxford", True), ("shirt", False)]
    assert picks_mod._names_something_unowned(line, owned) is dropped


def test_the_reader_is_told_the_advice_is_shorter():
    """A gap in the advice must explain itself rather than look like an oversight."""
    out = {"bullets": ["Start with your white t-shirt.", "Add a light shell."],
           "tip": "Take a brolly."}
    text = picks_mod._assemble_text(out, [], closet_mod.Prefs(closet_only=True),
                                     {"base": "i1"}, {"i1": {"label": "white t-shirt"}})
    assert "light shell" not in text
    assert "white t-shirt" in text
    assert "nothing you own suits them" in text


def test_without_the_tickbox_the_prose_is_left_alone():
    """A half-registered wardrobe still wants the hint."""
    out = {"bullets": ["Add a light shell."], "tip": ""}
    text = picks_mod._assemble_text(out, [], closet_mod.Prefs(),
                                     {"base": "i1"}, {"i1": {"label": "white t-shirt"}})
    assert "light shell" in text


def test_a_slot_that_came_up_short_once_cannot_carry_a_purchase(monkeypatch):
    """The prompt says a single cold morning is not a reason to buy a coat.

    But `evidenced` was satisfied by one appearance, so once seven mornings existed
    ANYWHERE, a slot with one incidental gap could carry a suggestion. The floor is
    in code now rather than asked for in prose. Raised by the pre-push reviewer,
    2026-08-27.
    """
    import shopping

    async def fake_chat(*a, **k):
        return ('{"suggestions": ['
                '{"what":"wool coat","slot":"outer","why":"x","priority":1},'
                '{"what":"silk scarf","slot":"accessories","why":"y","priority":2}],'
                '"verdict":"v"}')
    monkeypatch.setattr(shopping, "_chat", fake_chat)
    out = asyncio.run(shopping.shopping_list(
        [], [{"slot": "outer", "n": 9, "loC": 2, "hiC": 9},
             {"slot": "accessories", "n": 1, "loC": 2, "hiC": 9}], [], {"tempOffset": 0}))
    assert [s["slot"] for s in out["suggestions"]] == ["outer"]
