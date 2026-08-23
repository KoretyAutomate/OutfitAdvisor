"""The taxonomy as it is actually WIRED — schema, prompts, picks.

Separate from test_taxonomy.py deliberately. That file tests vocab.py, which is
pure. This one tests the seams, because the last two times this area broke every
unit was individually correct and only the wiring was wrong:

  - /classify asked the model for `group` and `roles` and then threw both away one
    line before they reached the phone (found twice, independently, 08-14 and 08-18)
  - underwear that is not a torso garment was a legal undershirt (08-20)
"""
import asyncio

import pytest

import closet as closet_mod
import llm
import vocab
from app import ClosetItem

WEATHER = {
    "lo": 8, "hi": 15, "feelsLo": 6, "feelsHi": 14, "desc": "Cloudy", "rain": 10,
    "wind": 3, "morning": 9, "midday": 14, "evening": 11, "swing": 7,
    "isRain": False, "isSnow": False, "code": 3,
}
# What _pack_prompt reads off the forecast summary — a trip, not a single day.
PACK_SUMMARY = {"nDays": 3, "mode": "forecast", "loMin": 8, "hiMax": 15, "rainDays": 1}


def item(**kw):
    base = dict(id="itm-00000001", label="a garment", category="base", colors=["navy"],
                warmth=3, formality=["casual"], waterproof=False, availableCount=1)
    base.update(kw)
    return ClosetItem(**base)


# ── the schema is the one sanitization path in both directions ─────────────────

def test_an_old_phone_sending_knitwear_is_not_a_422():
    """A Literal rejection here fails the WHOLE /advice request — every other item in
    the closet lost because one of them used last week's spelling."""
    it = item(category="mid", group="knitwear", type="sweater")
    assert it.group == "tops"
    assert it.type == "sweater"


def test_an_unknown_type_is_dropped_not_rejected():
    assert item(type="nonsense").type is None
    assert item(type="x" * 400).type is None      # _cap_type runs BEFORE the model validator


def test_a_type_from_another_group_is_dropped():
    assert item(category="base", group="tops", type="coat").type is None


def test_the_schema_cannot_construct_a_contradictory_item():
    """group=tops + category=inner was storable until 2026-08-18, and closet.py picks
    by role, so that tee was a legal undershirt."""
    it = item(category="inner", group="tops", roles=["inner"], type="t_shirt")
    assert it.group == "tops"
    assert it.category != "inner"
    assert "inner" not in it.roles


def test_the_type_survives_the_round_trip_to_the_phone():
    """/classify returns model_dump(); a field missing here is a field the phone
    never sees, which is exactly how `roles` was lost for eight days."""
    d = item(group="tops", type="polo", roles=["base", "mid"]).model_dump()
    assert d["type"] == "polo"
    assert d["group"] == "tops"
    assert d["roles"] == ["base", "mid"]


# ── the outfit prompt ──────────────────────────────────────────────────────────

def test_socks_and_underpants_are_withheld_from_the_outfit_prompt():
    """The `inner` slot means the undershirt worn under the visible top, and
    `footwear` means shoes. Nothing stopped the advisor putting wool socks in the
    undershirt slot before these types were withheld."""
    wardrobe = [
        item(id="itm-00000001", group="underwear", category="inner", type="undershirt").model_dump(),
        item(id="itm-00000002", group="underwear", category="inner", type="briefs").model_dump(),
        item(id="itm-00000003", group="footwear", category="footwear", type="socks").model_dump(),
        item(id="itm-00000004", group="footwear", category="footwear", type="boots").model_dump(),
    ]
    kept = {i["id"] for i in closet_mod.wearable(wardrobe)}
    assert kept == {"itm-00000001", "itm-00000004"}


def test_a_closet_of_only_underpants_reports_inner_as_uncoverable():
    """And that is the TRUE answer — the user owns no undershirt."""
    wardrobe = [item(id="itm-00000002", group="underwear", category="inner",
                     type="briefs").model_dump()]
    assert closet_mod.wearable(wardrobe) == []


def test_the_prompt_names_the_garment_type_beside_the_label():
    """"navy top" and "navy polo" read identically to the model otherwise."""
    wardrobe = [item(group="tops", type="polo", label="navy pique").model_dump()]
    prompt = closet_mod._closet_prompt(WEATHER, "man", "smart", wardrobe)
    assert "Polo shirt" in prompt


def test_the_packing_prompt_keeps_what_the_outfit_prompt_withholds():
    """A packing list that forgets socks is worse than useless."""
    wardrobe = [item(group="footwear", category="footwear", type="socks",
                     label="wool socks").model_dump()]
    days = [{"date": "2026-09-01", "lo": 8, "hi": 15, "desc": "Cloudy", "rain": 10, "wind": 3}]
    prompt = llm._pack_prompt((days, PACK_SUMMARY), "man", ["casual"], "vacation", wardrobe)
    assert "wool socks" in prompt
    assert "Socks / hosiery" in prompt


def test_the_classify_prompt_offers_every_type_of_every_group():
    """Listing the types PER GROUP is what stops "polo" coming back with group
    "outerwear": the model reads its own group choice off the line it answers from."""
    sent = {}

    async def fake_chat(msgs, **kw):
        sent["prompt"] = msgs[0]["content"][0]["text"]
        return None

    original, llm._chat = llm._chat, fake_chat
    try:
        asyncio.run(llm.classify_image("AAAA"))
    finally:
        llm._chat = original
    for group, types in vocab.TYPES.items():
        assert group in sent["prompt"]
        for t in types:
            assert t in sent["prompt"], f"{t} is not offered to the classifier"


def test_the_classify_prompt_asks_what_it_is_before_how_it_is_worn():
    """The model answers fields in the order asked. Asking `category` first, with
    "inner = underwear" buried in a parenthesis, is what mixed inner and base
    together in the user's Tops folder (2026-08-18)."""
    sent = {}

    async def fake_chat(msgs, **kw):
        sent["prompt"] = msgs[0]["content"][0]["text"]
        return None

    original, llm._chat = llm._chat, fake_chat
    try:
        asyncio.run(llm.classify_image("AAAA"))
    finally:
        llm._chat = original
    p = sent["prompt"]
    assert p.index('"group"') < p.index('"category"')
    assert p.index('"type"') < p.index('"category"')


# ── the one-piece rule ─────────────────────────────────────────────────────────

def test_trousers_under_a_dress_are_cleared():
    """`picks` holds one item per slot and _dedupe_picks forbids one id in two, so
    the honest encoding is: the one-piece takes `base`, bottoms is not NEEDED."""
    picks = {"base": "itm-dress", "bottoms": "itm-chinos"}
    by_group = {"itm-dress": "onepiece", "itm-chinos": "bottoms"}
    assert closet_mod._onepiece_conflicts(picks, by_group) is True
    assert picks["bottoms"] is None
    assert picks["base"] == "itm-dress"


def test_an_ordinary_top_leaves_bottoms_alone():
    picks = {"base": "itm-tee", "bottoms": "itm-chinos"}
    by_group = {"itm-tee": "tops", "itm-chinos": "bottoms"}
    assert closet_mod._onepiece_conflicts(picks, by_group) is False
    assert picks["bottoms"] == "itm-chinos"


def test_a_one_piece_with_no_bottoms_picked_is_already_correct():
    picks = {"base": "itm-dress", "bottoms": None}
    assert closet_mod._onepiece_conflicts(picks, {"itm-dress": "onepiece"}) is False


def test_a_one_piece_item_is_confined_to_the_base_slot():
    it = item(group="onepiece", type="dress", category="bottoms", roles=["bottoms", "base"])
    assert it.category == "base"
    assert it.roles == ["base"]


@pytest.mark.parametrize("kind", vocab.TYPES["onepiece"])
def test_every_one_piece_type_lands_in_base(kind):
    assert vocab.TYPE_DEFAULTS[kind]["roles"] == ("base",)
