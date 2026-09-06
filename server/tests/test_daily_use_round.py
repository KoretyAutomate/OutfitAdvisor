"""Silent failures found by the pre-launch review (2026-09-06).

The app kept working through every one of these; what it said about WHY was wrong.
Four things are pinned:

  1. `_chat` names the kind of nothing it got — transport, HTTP status, unreadable
     body, empty content — and the closet loop does not call a missing reply "not
     the required JSON", nor ask again in the same second;
  2. `source` follows the text: `llm` only when a model wrote it, `none` for the
     closet-only refusal, `rule-engine` when the engine did;
  3. the wardrobe listing marks, per role, every garment the heat rules out, with
     the same arithmetic the validator applies — and a too-warm pick is repaired in
     code on the FIRST attempt rather than bought back with a second generation;
  4. a rule that clears a pick is logged by kind, never by what it says.
"""
import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

import app as srv
import closet as closet_llm
import llm
import picks as pk

ANCHORS = [0.7, 12.9, 25.6]
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
HOT = {"date": "2026-09-01", "code": 0, "emoji": "☀️", "desc": "Clear", "lo": 22,
       "hi": 32, "swing": 10, "feelsLo": 22, "feelsHi": 33, "rain": 0, "wind": 2,
       "morning": 23, "midday": 30, "evening": 29, "isSnow": False, "isRain": False}
COLD = {"date": "2026-01-10", "code": 3, "emoji": "☁️", "desc": "Cloudy", "lo": 2,
        "hi": 9, "swing": 7, "feelsLo": 0, "feelsHi": 7, "rain": 10, "wind": 4,
        "morning": 3, "midday": 8, "evening": 5, "isSnow": False, "isRain": False}

FLEECE_ANSWER = ('{"picks": {"inner": null, "base": "itm-00000001", '
                 '"mid": "itm-00000002", "outer": null, "bottoms": "itm-00000003", '
                 '"footwear": null, "accessories": null}, '
                 '"bullets": ["Base: the white tee", "Mid: the grey fleece"], '
                 '"tip": "Nice day."}')


# ── 1. the kind of nothing ────────────────────────────────────────────────────

class _Client:
    """httpx.AsyncClient stand-in whose post() does whatever the test says."""

    def __init__(self, behaviour):
        self._b = behaviour

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        return self._b()


def _response(status, body):
    req = httpx.Request("POST", llm.VLLM_URL)
    return httpx.Response(status, json=body, request=req)


@pytest.mark.parametrize("behaviour, said", [
    (lambda: (_ for _ in ()).throw(httpx.ConnectError("refused")), "unreachable (ConnectError)"),
    (lambda: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "unreachable (ReadTimeout)"),
    (lambda: _response(503, {"error": "loading"}), "HTTP 503"),
    (lambda: _response(200, {"choices": []}), "unreadable (IndexError)"),
    (lambda: _response(200, {"choices": [{"message": {"content": "  "}}]}), "empty content"),
])
def test_chat_says_which_kind_of_nothing_it_got(monkeypatch, caplog, behaviour, said):
    """2026-09-06 09:18:25: vLLM still loading after a reboot, and the journal said the
    model had answered badly twice. It had not answered at all."""
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda timeout: _Client(behaviour))
    with caplog.at_level(logging.WARNING, logger="outfit.llm"):
        out = asyncio.run(llm._chat([{"role": "user", "content": "x"}], max_tokens=8))
    assert out is None
    assert any(said in r.getMessage() for r in caplog.records), caplog.text


def test_a_good_reply_still_comes_back_unchanged(monkeypatch):
    def ok():
        return _response(200, {"choices": [{"message": {"content": " hi "},
                                            "finish_reason": "stop"}]})

    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda timeout: _Client(ok))
    assert asyncio.run(llm._chat([{"role": "user", "content": "x"}], max_tokens=8)) == "hi"


def test_no_reply_is_not_called_bad_json_and_is_not_asked_again(monkeypatch, caplog):
    """Two attempts 4 ms apart against a model that is not there is not a retry."""
    calls = []

    async def silent(messages, max_tokens, timeout=45, **kw):
        calls.append(1)
        return None

    monkeypatch.setattr(closet_llm, "_chat", silent)
    with caplog.at_level(logging.WARNING, logger="outfit.llm"):
        out = asyncio.run(closet_llm.closet_outfit(HOT, "man", "casual", [TEE, SHORTS]))
    assert out is None
    assert len(calls) == 1, "a missing reply must not be asked for a second time"
    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "no reply from the model" in said
    assert "not the required JSON" not in said


def test_bad_json_is_still_bad_json_and_still_retried(monkeypatch, caplog):
    calls = []

    async def garbage(messages, max_tokens, timeout=45, **kw):
        calls.append(1)
        return "not json at all"

    monkeypatch.setattr(closet_llm, "_chat", garbage)
    with caplog.at_level(logging.WARNING, logger="outfit.llm"):
        assert asyncio.run(closet_llm.closet_outfit(HOT, "man", "casual", [TEE, SHORTS])) is None
    assert len(calls) == 2
    assert "not the required JSON" in caplog.text


# ── 2. source follows the text ────────────────────────────────────────────────

@pytest.fixture
def api(monkeypatch):
    async def fake_weather(lat, lon, day):
        return dict(COLD)

    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    return TestClient(srv.app)


def _silence(monkeypatch):
    async def none(*a, **k):
        return None

    monkeypatch.setattr(llm, "_chat", none)
    monkeypatch.setattr(closet_llm, "_chat", none)


def test_closet_only_refusal_is_not_credited_to_the_model(api, monkeypatch):
    """Journal 2026-09-06: `source=llm closetUsed=no 0.44s` with vLLM down."""
    _silence(monkeypatch)
    d = api.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [TEE],
                                  "closetOnly": True}).json()
    assert d["closetUsed"] is False
    assert d["source"] == "none"
    assert d["outfit"]["base"].startswith("None — ")


def test_the_engine_is_credited_when_it_writes_the_words(api, monkeypatch):
    _silence(monkeypatch)
    d = api.post("/advice", json={"lat": 40.3, "lon": -74.6}).json()
    assert d["source"] == "rule-engine"


def test_the_model_is_credited_when_it_answers(api, monkeypatch):
    async def cold_answer(messages, max_tokens, timeout=45, **kw):
        return ('{"picks": {"inner": null, "base": "itm-00000001", "mid": null, '
                '"outer": null, "bottoms": null, "footwear": null, "accessories": null}, '
                '"bullets": ["Base: the white tee"], "tip": ""}')

    monkeypatch.setattr(closet_llm, "_chat", cold_answer)
    d = api.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [TEE]}).json()
    assert d["closetUsed"] is True
    assert d["source"] == "llm"


# ── 3. told per garment, repaired without a second ask ────────────────────────

def test_the_listing_marks_what_the_heat_rules_out():
    prompt = closet_llm._closet_prompt(HOT, "man", "casual", [TEE, FLEECE, SHORTS],
                                       closet_llm.Prefs())
    fleece_line = next(ln for ln in prompt.splitlines() if "grey fleece" in ln)
    assert "TOO WARM today as: mid,outer" in fleece_line
    tee_line = next(ln for ln in prompt.splitlines() if "white tee" in ln)
    assert "TOO WARM" not in tee_line
    assert "HEAT RULE" in prompt


def test_the_mark_uses_the_validators_own_arithmetic():
    """The line and the check must agree, or the model is told one thing and
    corrected by another."""
    prompt = closet_llm._closet_prompt(COLD, "man", "casual", [TEE, FLEECE, SHORTS],
                                       closet_llm.Prefs())
    wardrobe = prompt.split("```")[1]
    assert "TOO WARM" not in wardrobe, "a fleece is not too warm at 3C"
    plan = llm._plan_temp(HOT)
    peak = max(plan, HOT["hi"])
    assert pk._too_warm_slots({"mid": FLEECE["id"]}, {FLEECE["id"]: FLEECE}, plan, peak) == ["mid"]


def test_a_too_warm_pick_is_repaired_on_the_first_attempt(monkeypatch):
    """Was: a corrective retry, then the swap. In 30 days of journal the retry never
    once changed what the swap then did anyway (2026-09-06)."""
    prompts = []

    async def insists(messages, max_tokens, timeout=45, **kw):
        prompts.append(messages[0]["content"])
        return FLEECE_ANSWER

    monkeypatch.setattr(closet_llm, "_chat", insists)
    out = asyncio.run(closet_llm.closet_outfit(HOT, "man", "casual", [TEE, FLEECE, SHORTS]))
    assert out is not None
    assert out["picks"]["mid"] is None, "the fleece is shed"
    assert len(prompts) == 1, "told in the listing, repaired in code — not asked twice"
    assert "Too much clothing for the heat" not in prompts[0]


# ── 4. the rule's kind, not its words ─────────────────────────────────────────

def test_a_rule_that_clears_a_pick_is_logged_by_kind_only(caplog):
    rule = {"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "fleece"},
            "text": "never the grey fleece over the white tee"}
    picks = {"base": TEE["id"], "mid": FLEECE["id"]}
    by_item = {TEE["id"]: TEE, FLEECE["id"]: FLEECE}
    with caplog.at_level(logging.WARNING, logger="outfit.llm"):
        note, cleared, _ = pk._enforce_user_rules(picks, by_item, [rule], 1)
    assert cleared, "the pair rule must have fired for this test to mean anything"
    said = caplog.text
    assert "avoid_pair rule" in said
    for word in ("fleece", "tee", "white", "grey", "never"):
        assert word not in said.lower(), f"rule text leaked into the journal: {word!r}"
