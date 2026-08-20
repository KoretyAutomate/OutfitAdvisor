"""The 2026-08-20 taxonomy round, exercised as HTTP rather than as functions.

The unit tests next door prove vocab.reconcile() and the type tables do the right
thing when CALLED. This proves they are actually WIRED — which is the half that has
broken twice: /classify had been asking the model for `group` and `roles` since
2026-08-10 and dropping both one line before the response, and no unit test noticed,
because every unit involved was correct.

So these go through the real FastAPI app: real routing, real pydantic validation,
real response serialization. Only the two things that leave the machine are stubbed
— the LLM and Open-Meteo.

The classifier stub deliberately returns the user's exact complaint: a plain white
tee that the model calls a Top and, in the same breath, says to wear as underwear.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# A bare sys.path call, so the imports below stay legal top-of-file imports rather
# than suppressed E402s.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as srv
import closet as closet_llm
import llm

# base64 of a sentence — long enough to clear the endpoint's min_length.
FAKE_IMAGE = (
    "aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgZW5vdWdoIHN0cmluZyB0byBwYXNzIHRoZSBt"
    "aW5pbXVtIGxlbmd0aCB2YWxpZGF0aW9uIGNoZWNrIGZvciB0aGUgZW5kcG9pbnQu"
)

# A wardrobe as an OLD phone build sends it: the group that no longer exists, and a
# dress still filed under bottoms.
LEGACY_CLOSET = [
    {"id": "itm-00000001", "label": "grey crewneck", "category": "mid",
     "group": "knitwear", "type": "sweater", "roles": ["mid", "outer"],
     "colors": ["grey"], "warmth": 4, "formality": ["casual"], "waterproof": False,
     "availableCount": 1},
    {"id": "itm-00000002", "label": "summer dress", "category": "bottoms",
     "group": "bottoms", "type": "dress", "roles": ["bottoms"], "colors": ["blue"],
     "warmth": 2, "formality": ["casual"], "waterproof": False, "availableCount": 1},
    {"id": "itm-00000003", "label": "wool socks", "category": "inner",
     "group": "underwear", "type": "socks", "roles": ["inner"], "colors": ["grey"],
     "warmth": 3, "formality": ["casual"], "waterproof": False, "availableCount": 1},
]


@pytest.fixture
def client(monkeypatch):
    """The real server, with only the network edges replaced."""
    seen: dict = {}

    async def fake_chat(messages, max_tokens, timeout=45):
        content = messages[0]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        seen["prompt"] = prompt
        if "Classify the clothing item" in prompt:
            # The user's complaint, verbatim: a Top that is also underwear. And a
            # type, which is the field this round added.
            return json.dumps({
                "label": "white cotton tee", "group": "tops", "type": "t_shirt",
                "category": "inner", "roles": ["inner", "base"], "colors": ["white"],
                "warmth": 0, "formality": [], "waterproof": False,
            })
        return json.dumps({
            "picks": {"inner": None, "base": "itm-00000001", "mid": None, "outer": None,
                      "bottoms": None, "footwear": None, "accessories": None},
            "bullets": ["Base: the grey crewneck"], "tip": "Nice day.",
        })

    async def fake_weather(lat, lon, day):
        return {"date": "2026-08-20", "timezone": "America/New_York", "code": 3,
                "emoji": "⛅", "desc": "Cloudy", "lo": 18, "hi": 26, "swing": 8,
                "feelsLo": 17, "feelsHi": 25, "rain": 10, "wind": 3, "morning": 19,
                "midday": 25, "evening": 21, "isSnow": False, "isRain": False}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    c = TestClient(srv.app)
    c.seen = seen
    return c


# ── /classify ──────────────────────────────────────────────────────────────────

def test_classify_returns_the_type_to_the_phone(client):
    """A field missing from this response is a field the phone never sees — which
    is exactly how `roles` was lost for eight days."""
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE}).json()
    assert d["type"] == "t_shirt"
    assert d["group"] == "tops"
    assert "roles" in d


def test_classify_refuses_to_pass_on_a_self_contradictory_answer(client):
    """The model said Top AND underwear. Only one of those can reach the phone."""
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE}).json()
    assert d["category"] == "base"
    assert "inner" not in d["roles"]


def test_classify_fills_warmth_and_formality_from_the_type(client):
    """The stub answers warmth 0 and no formality — unusable. A t-shirt's defaults
    are a better answer than the bare 3/["casual"] fallback, and formality is the
    field that finally makes a tee and a polo differ on a smart day."""
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE}).json()
    assert d["warmth"] == 1
    assert d["formality"] == ["casual", "active"]
    assert "smart" not in d["formality"]


# ── /advice with a wardrobe an older build saved ───────────────────────────────

def test_a_legacy_closet_is_accepted_not_422d(client):
    """`knitwear` stopped being a group on 2026-08-20. A Literal rejection here
    fails the WHOLE request — every other item lost because one used last week's
    spelling."""
    r = client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    assert r.status_code == 200, r.text
    assert r.json()["closetUsed"] is True


def test_the_wardrobe_the_model_sees_has_no_contradictions_left(client):
    client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    wardrobe = client.seen["prompt"].split("WARDROBE", 1)[1].split("```")[1]
    assert "can be worn as: mid/outer" in wardrobe      # the ex-knitwear sweater
    assert "inner" not in wardrobe, wardrobe


def test_the_socks_never_reach_the_outfit_prompt(client):
    """Nothing stopped the advisor putting wool socks in the undershirt slot before
    NON_SLOT_TYPES were withheld."""
    client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    wardrobe = client.seen["prompt"].split("WARDROBE", 1)[1].split("```")[1]
    assert "wool socks" not in wardrobe
    assert "grey crewneck" in wardrobe


def test_the_wardrobe_the_model_sees_names_the_garment_types(client):
    client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    wardrobe = client.seen["prompt"].split("WARDROBE", 1)[1].split("```")[1]
    assert "Sweater / pullover" in wardrobe
    assert "Dress" in wardrobe


def test_the_dress_arrives_as_a_one_piece_not_as_trousers(client):
    """It was filed under bottoms, because `onepiece` did not exist when it was
    saved — and the packing prompt has been reading it as a pair of trousers."""
    client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    wardrobe = client.seen["prompt"].split("WARDROBE", 1)[1].split("```")[1]
    dress_line = next(ln for ln in wardrobe.splitlines() if "summer dress" in ln)
    assert "can be worn as: base" in dress_line, dress_line


def test_the_prompt_states_the_one_piece_rule(client):
    client.post("/advice", json={"lat": 40.7, "lon": -74.0, "closet": LEGACY_CLOSET})
    assert "ONE-PIECE RULE" in client.seen["prompt"]


def test_a_closet_of_nothing_but_socks_falls_back_rather_than_dressing_you_in_them(client):
    """closetUsed=false and generic advice is the honest outcome; naming the socks
    as an undershirt is not."""
    r = client.post("/advice", json={
        "lat": 40.7, "lon": -74.0,
        "closet": [i for i in LEGACY_CLOSET if i["id"] == "itm-00000003"]})
    assert r.status_code == 200
    assert r.json()["closetUsed"] is False
