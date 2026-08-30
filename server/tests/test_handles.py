"""The model never sees a UUID (2026-08-30).

The ids the phone generates are UUIDs. Asking a model to copy one back exactly is
asking it to transcribe 32 random hex digits, and it got them nearly right: the same
real garment came back as `itm-e27af5ac-6454-44ed-9a7e-3ddb08307222` on 2026-08-29
and `itm-e27af5ac-6454-44ed-9a7a-5ed294a3f494` on 2026-08-30 — identical for 25
characters, different after. Both were rejected as unknown ids on both attempts, and
the user was told their closet had nothing wearable, on two consecutive days, with
fifteen garments registered. They reported it as the server being unreachable.
"""
import closet as closet_mod
import picks as pk

UUID = "itm-e27af5ac-6454-44ed-9a7e-3ddb08307222"
TEE = {"id": UUID, "label": "white tee", "category": "base", "group": "tops",
       "type": "t_shirt", "roles": ["base"], "colors": ["white"], "warmth": 1,
       "formality": ["casual"], "waterproof": False, "availableCount": 2}
POLO = {**TEE, "id": "itm-9f2b1c7d-0000-4aaa-8bbb-ccccdddd1111",
        "label": "navy polo", "type": "polo"}
WARM = {"lo": 18, "hi": 27, "morning": 20, "midday": 26, "evening": 22,
        "feelsLo": 18, "feelsHi": 28, "desc": "Clear", "rain": 0, "wind": 2,
        "swing": 9, "isRain": False, "isSnow": False, "code": 0}


def test_handles_are_short_and_in_listing_order():
    assert pk.handles_for([TEE, POLO]) == {"i1": TEE["id"], "i2": POLO["id"]}


def test_no_uuid_reaches_the_prompt():
    prompt = closet_mod._closet_prompt(WARM, "man", "casual", [TEE, POLO], pk.Prefs())
    assert UUID not in prompt
    assert POLO["id"] not in prompt
    assert "i1 |" in prompt and "i2 |" in prompt
    # and the garments are still identifiable by name
    assert "white tee" in prompt and "navy polo" in prompt


def test_the_answer_comes_back_in_real_ids():
    handles = pk.handles_for([TEE, POLO])
    picks = pk.resolve_handles({"base": "i1", "mid": "i2", "outer": None},
                               handles, frozenset({TEE["id"], POLO["id"]}))
    assert picks == {"base": TEE["id"], "mid": POLO["id"], "outer": None}


def test_a_real_id_is_still_accepted():
    """The model may answer with one it remembers from earlier in the conversation.
    Rejecting an id that names the right garment would be an error of our own."""
    ids = frozenset({TEE["id"], POLO["id"]})
    picks = pk.resolve_handles({"base": UUID}, pk.handles_for([TEE, POLO]), ids)
    assert picks["base"] == UUID


def test_something_that_is_neither_survives_to_be_rejected():
    """A miscopied handle must reach _unknown_ids as itself, so the corrective note
    tells the model what it actually wrote."""
    picks = pk.resolve_handles({"base": "i9"}, pk.handles_for([TEE]),
                               frozenset({TEE["id"]}))
    assert picks["base"] == "i9"
    assert "i9" in pk._unknown_ids(picks, frozenset({TEE["id"]}))


def test_whitespace_around_a_handle_does_not_lose_the_garment():
    picks = pk.resolve_handles({"base": " i1 "}, pk.handles_for([TEE]),
                               frozenset({TEE["id"]}))
    assert picks["base"] == TEE["id"]


def test_the_two_sides_derive_the_handles_from_one_list():
    """The prompt's listing order IS the handle order. Two derivations of one map is
    how a handle comes to mean different garments on the two sides of a request."""
    closet = [TEE, POLO]
    prompt = closet_mod._closet_prompt(WARM, "man", "casual", closet, pk.Prefs())
    handles = pk.handles_for(closet)
    for handle, iid in handles.items():
        label = next(i["label"] for i in closet if i["id"] == iid)
        line = next(ln for ln in prompt.split("\n") if ln.startswith(handle + " |"))
        assert label in line, (handle, line)
