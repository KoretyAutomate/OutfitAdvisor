"""The two-level clothing taxonomy — group > type (user request 2026-08-14).

WHY THIS EXISTS
    `type` is the first field whose valid values depend on ANOTHER field. Every
    other closet field is either a Literal or a free string, so pydantic alone was
    enough; this one is only meaningful relative to `group`, and the validation
    lives in vocab.normalize_type() where a Literal cannot reach it.

    The failure mode being pinned is silent, not loud: an unrecognised or
    group-mismatched type is DROPPED, never rejected. That is deliberate — a photo
    the user just took must not 422 because the model guessed "polo" for a coat —
    but it means a mistake here costs a field with no error anywhere. So the drop
    rules are asserted, not assumed.

    The parity table in section 1 is duplicated verbatim in
    app/tests/closet_types.test.js: normType() in index.html is this function's
    twin, and a drift between them shows up as types vanishing on the way to the
    advisor rather than as a failure.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vocab  # noqa: E402
from app import ClosetItem  # noqa: E402

# (input type, group, expected) — MIRRORED in app/tests/closet_types.test.js
PARITY = [
    ("polo", "tops", "polo"),
    ("Polo", "tops", "polo"),  # case
    ("t-shirt", "tops", "t_shirt"),  # hyphen
    ("dress shoes", "footwear", "dress_shoes"),  # space
    ("polo", "outerwear", None),  # right type, wrong group
    ("kimono", "tops", None),  # not in the taxonomy at all
    ("", "tops", None),
    (None, "tops", None),
    ("polo", None, None),  # no group -> nothing to validate against
]


@pytest.mark.parametrize("value,group,want", PARITY)
def test_normalize_type_parity(value, group, want):
    assert vocab.normalize_type(value, group) == want


def test_every_type_belongs_to_exactly_one_group():
    """A type that appeared under two groups would make GROUP_FROM_TYPE lossy and
    make "which folder does this live in" unanswerable."""
    flat = [t for ts in vocab.TYPES.values() for t in ts]
    assert len(flat) == len(set(flat))
    assert set(vocab.GROUP_FROM_TYPE) == set(flat)


def test_every_group_has_types_and_every_type_has_a_label():
    """A group with no types would render an empty picker; a type with no label
    would render its raw key ("dress_shoes") to the user."""
    assert set(vocab.TYPES) == set(vocab.GROUPS)
    for group, types in vocab.TYPES.items():
        assert types, group
        for t in types:
            assert vocab.TYPE_LABEL.get(t), t


def _item(**over):
    base = dict(id="itm-abcd1234", label="navy polo", category="base")
    base.update(over)
    return ClosetItem(**base)


def test_type_survives_validation_when_it_matches_the_group():
    it = _item(type="polo")
    assert (it.group, it.type) == ("tops", "polo")


def test_type_is_dropped_rather_than_rejected_when_it_does_not_fit():
    """The whole point: a wrong guess costs the field, not the request."""
    assert _item(category="outer", type="polo").type is None
    assert _item(type="kimono").type is None


def test_type_is_validated_against_the_DERIVED_group_not_the_sent_one():
    """A closet saved before `group` existed sends none, so the group is derived
    from `category` first — and only then can a type be judged. Getting that order
    wrong would drop every type on every legacy item."""
    it = _item(category="outer", group=None, type="coat")
    assert (it.group, it.type) == ("outerwear", "coat")


def test_no_type_is_the_normal_case_and_stays_none():
    assert _item().type is None


def test_classify_forwards_the_models_group_roles_and_type():
    """/classify used to build a ClosetItem from label/category/colors/warmth/
    formality/waterproof ONLY, so `group` and `roles` — which the prompt had been
    asking for since 2026-08-10 — were re-derived from `category` and the model's
    real answer was discarded one line before it reached the phone. Every
    classified item came back with roles=[category].

    This pins the forwarding. The normalizers still have the last word, which is
    what makes forwarding safe rather than trusting.
    """
    import asyncio

    import app as server_app

    raw = {
        "label": "white oxford shirt", "category": "base", "group": "tops",
        "roles": ["base", "mid", "outer"], "type": "shirt",
        "colors": ["white"], "warmth": 2, "formality": ["smart"], "waterproof": False,
    }

    async def fake_classify(_b64):
        return raw

    original = server_app.llm.classify_image
    server_app.llm.classify_image = fake_classify
    try:
        out = asyncio.run(server_app.classify(server_app.ClassifyRequest(imageB64="A" * 200)))
    finally:
        server_app.llm.classify_image = original

    assert out["group"] == "tops"
    assert out["roles"] == ["base", "mid", "outer"], "seasonal roles were dropped again"
    assert out["type"] == "shirt"


def test_the_phone_and_the_server_agree_on_the_taxonomy():
    """normType()/TYPES in app/www/index.html are TWINS of this module's. A drift
    is silent in both directions — the server drops a type the phone offers, and
    the phone files an item under a folder the server never validated — so it is
    checked against the real source rather than restated."""
    src = (Path(__file__).resolve().parents[2] / "app" / "www" / "index.html").read_text()
    block = src.split("const TYPES={", 1)[1].split("};", 1)[0]
    js: dict[str, list[str]] = {}
    for group, items in re.findall(r"(\w+):\[([^\]]*)\]", block):
        js[group] = re.findall(r'"([^"]+)"', items)
    assert js == {g: list(ts) for g, ts in vocab.TYPES.items()}

    labels = src.split("const TYPE_LABEL={", 1)[1].split("};", 1)[0]
    js_labels = dict(re.findall(r'(\w+):"([^"]*)"', labels))
    assert js_labels == vocab.TYPE_LABEL


def test_the_prompt_names_the_type_beside_the_label():
    """A polo and a tee differ in nothing else on the wardrobe line, and the
    difference decides whether an item suits `smart`."""
    import closet

    w = {
        "lo": 1, "hi": 9, "feelsLo": 0, "feelsHi": 8, "desc": "Clear", "rain": 0,
        "wind": 1, "morning": 3, "midday": 7, "evening": 5, "swing": 8,
        "isRain": False, "isSnow": False,
    }
    line = next(
        line
        for line in closet._closet_prompt(w, "man", "smart", [_item(type="polo").model_dump()]).splitlines()
        if "itm-abcd1234" in line
    )
    assert "navy polo (Polo shirt)" in line
    # An untyped item must not gain an empty "()" — that reads as missing data.
    untyped = next(
        line
        for line in closet._closet_prompt(w, "man", "smart", [_item().model_dump()]).splitlines()
        if "itm-abcd1234" in line
    )
    assert "()" not in untyped
