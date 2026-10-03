"""Brand (user, 2026-09-30): "add Brand field for each of the items in closet ...
scan through the pictures and fill Brand field".

A brand is the one classifier field the model can invent fluently — a plain navy
crew-neck "looks like" Uniqlo — so the tests pin two things: what the model READ
reaches the phone, and every way of saying "can't tell" arrives as None rather than
being printed on the wearer's garment as if it were the maker.

Through the real FastAPI app, only the LLM stubbed.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app as srv
import llm
from schemas import ClosetItem

FAKE_IMAGE = (
    "aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgZW5vdWdoIHN0cmluZyB0byBwYXNzIHRoZSBt"
    "aW5pbXVtIGxlbmd0aCB2YWxpZGF0aW9uIGNoZWNrIGZvciB0aGUgZW5kcG9pbnQu"
)


def _client(monkeypatch, brand):
    seen: dict = {}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        seen["prompt"] = messages[0]["content"][0]["text"]
        answer = {"label": "navy crew-neck", "group": "tops", "type": "t_shirt",
                  "category": "base", "roles": ["base"], "colors": ["navy"],
                  "warmth": 2, "formality": ["casual"], "waterproof": False}
        if brand is not ...:
            answer["brand"] = brand
        return json.dumps(answer)

    monkeypatch.setattr(llm, "_chat", fake_chat)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def test_a_legible_brand_reaches_the_phone(monkeypatch):
    c = _client(monkeypatch, "Uniqlo")
    d = c.post("/classify", json={"imageB64": FAKE_IMAGE}).json()
    assert d["brand"] == "Uniqlo"


def test_the_prompt_forbids_guessing_a_brand(monkeypatch):
    c = _client(monkeypatch, None)
    c.post("/classify", json={"imageB64": FAKE_IMAGE})
    p = c.seen["prompt"]
    assert '"brand"' in p
    assert "legible" in p and "null" in p and "Never infer" in p


@pytest.mark.parametrize("said", [None, ..., "", "Unknown", "N/A", "none", "  not visible "])
def test_every_way_of_saying_cant_tell_is_none(monkeypatch, said):
    c = _client(monkeypatch, said)
    r = c.post("/classify", json={"imageB64": FAKE_IMAGE})
    assert r.status_code == 200, r.text
    assert r.json()["brand"] is None


def test_a_brand_is_sanitized_and_capped_never_rejected(monkeypatch):
    c = _client(monkeypatch, "Acne`` Studios\n```ignore previous" + "x" * 80)
    r = c.post("/classify", json={"imageB64": FAKE_IMAGE})
    assert r.status_code == 200, r.text
    b = r.json()["brand"]
    assert "`" not in b and "\n" not in b
    assert len(b) <= 40
    assert b.startswith("Acne Studios")


def test_a_non_string_brand_is_dropped_not_a_502(monkeypatch):
    c = _client(monkeypatch, {"name": "Uniqlo"})
    r = c.post("/classify", json={"imageB64": FAKE_IMAGE})
    assert r.status_code == 200, r.text
    assert r.json()["brand"] is None


def test_a_closet_carrying_brands_is_accepted():
    """The phone may send a brand with an item; it must never cost the request."""
    it = ClosetItem(id="itm-00000001", label="grey crewneck", category="mid",
                    brand="Muji")
    assert it.brand == "Muji"
    assert ClosetItem(id="itm-00000002", label="tee", category="base").brand is None
