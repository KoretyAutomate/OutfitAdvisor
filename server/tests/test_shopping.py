"""Purchase suggestions, and the evidence they are argued from (2026-08-27).

The user asked for a weekly review that says what is worth adding. The temptation
is to ask a model "what should they buy?" — a model asked that always has an
answer, and the answer is a catalogue: plausible, generic, and indifferent to
whether the person was ever actually cold.

So the design is the one the PPK week and the rules engine both arrived at. The
phone records what actually went wrong, and the model argues from that. These cover
the endpoint and what comes back from it; the gap evidence itself is in
test_gap_evidence.py and the closet-only promise in test_closet_only.py.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import app as app_mod

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


# ── suggestions are checked, not merely requested ──────────────────────────────

def test_a_garment_they_already_own_is_not_suggested(monkeypatch):
    """The prompt says so; saying it is not enforcing it.

    A second navy tee looks like a reasonable suggestion — that is exactly why it
    has to be caught in code. Raised by the pre-push reviewer, 2026-08-27.
    """
    out = _suggest(monkeypatch, '{"suggestions": ['
                   '{"what":"white t-shirt","slot":"base","why":"x","priority":1},'
                   '{"what":"wool overcoat","slot":"outer","why":"y","priority":1}],'
                   '"verdict":"v"}')
    assert [s["what"] for s in out["suggestions"]] == ["wool overcoat"]


def test_a_garment_they_have_banned_is_not_suggested(monkeypatch):
    """It looks like advice until it arrives in the post."""
    import shopping

    async def fake_chat(*a, **k):
        return ('{"suggestions": [{"what":"puffer jacket","slot":"outer",'
                '"why":"x","priority":1}], "verdict":"v"}')
    monkeypatch.setattr(shopping, "_chat", fake_chat)
    out = asyncio.run(shopping.shopping_list(
        [ITEM], [{"slot": "outer", "n": 9, "loC": 2, "hiC": 9}],
        [{"kind": "avoid_item", "a": {"type": "puffer"}}], {"tempOffset": 0}))
    assert out["suggestions"] == []


def test_a_pair_rule_does_not_block_a_purchase():
    """Owning two things does not commit anybody to wearing them together."""
    import shopping
    pair = [{"kind": "avoid_pair", "a": {"type": "undershirt"}, "b": {"type": "t_shirt"}}]
    assert not shopping._is_banned("cotton undershirt", "inner", pair)


def test_matching_is_on_the_garment_not_on_a_shared_word():
    import shopping
    closet = [{"label": "navy merino crew-neck tee", "type": "t_shirt"}]
    assert shopping._already_owned("navy merino tee", closet)
    assert not shopping._already_owned("wool overcoat", closet)


# ── a mischoice is not evidence, even when the pick was unsuitable ─────────────

BY_ITEM = {"shell": {"id": "shell", "warmth": 2, "label": "thin shell",
                     "type": "rainwear", "colors": []},
           "coat": {"id": "coat", "warmth": 5, "label": "wool coat",
                    "type": "coat", "colors": []},
           "tee": {"id": "tee", "warmth": 1, "label": "tee",
                   "type": "t_shirt", "colors": []}}
BY_ROLES = {"shell": ["outer"], "coat": ["outer"], "tee": ["base"]}


def test_a_suggestion_for_a_slot_that_never_came_up_short_is_dropped(monkeypatch):
    """Evidence only.

    A slot with no recorded gap has never once come up short, so a suggestion for it
    is not an argument — it is the catalogue this endpoint exists to avoid, arriving
    under the same heading as the reasoned ones and indistinguishable from them.
    Raised by the pre-push reviewer, 2026-08-27.
    """
    out = _suggest(monkeypatch, '{"suggestions": ['
                   '{"what":"leather boots","slot":"footwear","why":"x","priority":1},'
                   '{"what":"wool overcoat","slot":"outer","why":"y","priority":1}],'
                   '"verdict":"v"}')
    # _suggest submits a single `outer` gap.
    assert [s["slot"] for s in out["suggestions"]] == ["outer"]


@pytest.mark.parametrize("rule,what,slot,banned", [
    # "Never wear white" carries a COLOUR and nothing else. Reading only type and
    # group left the selector empty, and an empty subset test is always true — so
    # the endpoint recommended the very colour just banned. Raised by the reviewer.
    ({"kind": "avoid_item", "a": {"color": "white"}}, "white wool coat", "outer", True),
    ({"kind": "avoid_item", "a": {"color": "white"}}, "navy wool coat", "outer", False),
    # A ROLE-only ban: nothing at all can be suggested for that slot.
    ({"kind": "avoid_item", "a": {"role": "outer"}}, "wool coat", "outer", True),
    ({"kind": "avoid_item", "a": {"role": "outer"}}, "cotton tee", "base", False),
    ({"kind": "avoid_item", "a": {"group": "outerwear"}}, "outerwear shell", "outer", True),
])
def test_a_ban_is_matched_on_every_field_it_names(rule, what, slot, banned):
    import shopping
    assert shopping._is_banned(what, slot, [rule]) is banned


def test_the_planning_temperature_is_returned_to_the_phone(monkeypatch):
    """So the phone judges a bought garment by the number THIS server used.

    Outer suitability is decided from the planning temperature — morning, or the
    midpoint — not the overnight low. The phone deciding later whether a coat
    answers a gap has to use the same basis, and deriving it again is a twin waiting
    to drift. Raised by the pre-push reviewer, 2026-08-27.
    """
    async def fake_weather(*a, **k):
        return {"lo": 2, "hi": 14, "feelsLo": 0, "feelsHi": 12, "desc": "Cold",
                "rain": 10, "wind": 4, "morning": 4, "midday": 12, "evening": 6,
                "swing": 12, "isRain": False, "isSnow": False, "code": 3,
                "emoji": "x", "date": "2026-08-27", "timezone": "America/New_York"}

    async def fake_text(*a, **k):
        return "• x"

    monkeypatch.setattr(app_mod.weather, "fetch_weather", fake_weather)
    monkeypatch.setattr(app_mod.llm, "outfit_text", fake_text)
    body = client.post("/advice", json={"lat": 40.35, "lon": -74.66,
                                        "gender": "man", "style": "casual"}).json()
    # morning wins over the midpoint, which would have been 8.
    assert body["planTemp"] == 4.0, body["planTemp"]


@pytest.mark.parametrize("sel,what,banned", [
    # A rule stores the CANONICAL id; a suggestion is written the way a person
    # speaks. Comparing the two directly meant a ban on rainwear did not stop a
    # shell being recommended. Raised by the pre-push reviewer, 2026-08-27.
    ({"type": "rainwear"}, "waterproof shell", True),      # TYPE_LABEL: "Raincoat / shell"
    ({"type": "rainwear"}, "wool overcoat", False),
    ({"type": "t_shirt"}, "cotton tee", True),             # alias: the label has no "tee"
    ({"type": "t_shirt"}, "wool overcoat", False),
    ({"type": "puffer"}, "down jacket", True),
    ({"type": "trousers"}, "wool chinos", True),
    # A colour named alongside a garment must still match.
    ({"color": "white", "type": "coat"}, "white wool coat", True),
    ({"color": "white", "type": "coat"}, "navy wool coat", False),
])
def test_a_ban_reaches_the_words_a_person_would_use(sel, what, banned):
    import shopping
    assert shopping._is_banned(what, "outer", [{"kind": "avoid_item", "a": sel}]) is banned


def test_every_alias_names_a_type_the_taxonomy_has():
    """An alias for a type that does not exist can never fire, and hides a typo."""
    import shopping
    from vocab import TYPE_LABEL
    assert set(shopping._ALIASES) <= set(TYPE_LABEL), \
        set(shopping._ALIASES) - set(TYPE_LABEL)


def test_ownership_reads_the_spoken_word_too():
    """An owned "white cotton t-shirt" has no "tee" in its label.

    So a suggested "cotton tee" read as something new — the same canonical-versus-
    spoken gap the ban check had. Raised by the pre-push reviewer, 2026-08-27.
    """
    import shopping
    closet = [{"label": "white cotton t-shirt", "type": "t_shirt"}]
    assert shopping._already_owned("cotton tee", closet)
    assert not shopping._already_owned("wool overcoat", closet)


@pytest.mark.parametrize("what,banned", [
    ("wool coat", True),
    ("puffer jacket", True),
    ("cotton tee", False),          # a top, not outerwear
])
def test_a_group_ban_reaches_the_garments_in_that_group(what, banned):
    """"Never wear outerwear" is a real rule.

    Searching a suggestion for the literal word `outerwear` finds it in no sentence
    anybody writes, so "wool coat" sailed past a ban that names exactly it.
    """
    import shopping
    rule = [{"kind": "avoid_item", "a": {"group": "outerwear"}}]
    assert shopping._is_banned(what, "outer", rule) is banned


@pytest.mark.parametrize("sel,what,slot,banned", [
    # "down" alone is not a garment word — it sits inside "button-down" and half the
    # prepositions in English. A substring test made a puffer ban refuse a shirt.
    # Raised by the pre-push reviewer, 2026-08-27.
    ({"type": "puffer"}, "button-down shirt", "base", False),
    ({"type": "puffer"}, "down jacket", "outer", True),
    ({"type": "puffer"}, "quilted jacket", "outer", True),
    ({"type": "puffer"}, "wool overcoat", "outer", False),
    # A compound still counts: "overcoat" is a coat, "tshirt" is a shirt.
    ({"type": "coat"}, "wool overcoat", "outer", True),
    # But only as a SUFFIX. "coathanger" is not a coat.
    ({"type": "coat"}, "coathanger", "outer", False),
    # Punctuation is not a difference.
    ({"type": "t_shirt"}, "cotton t-shirt", "base", True),
])
def test_an_alias_matches_on_word_boundaries(sel, what, slot, banned):
    import shopping
    assert shopping._is_banned(what, slot, [{"kind": "avoid_item", "a": sel}]) is banned


def test_a_label_is_read_as_alternatives_not_loose_words():
    """TYPE_LABEL["puffer"] is "Padded / down jacket".

    Split into words that yielded {padded, down, jacket} — so the ban matched
    `down` in "button-down", and would have matched ANY jacket on `jacket`. The
    two sides of the slash are alternatives, and each is a phrase.
    """
    import shopping
    assert shopping._garment_aliases("puffer") == {"padded", "down jacket",
                                                   "quilted", "puffer"}
    assert "jacket" not in shopping._garment_aliases("puffer")


def test_the_floor_is_low_enough_not_to_silence_a_short_winter():
    """Two, not more — the RANKING separates a nuisance from a real gap.

    Higher would silence somebody who has simply not met much weather yet.
    """
    import shopping
    assert shopping.MIN_MORNINGS_PER_SLOT == 2


@pytest.mark.parametrize("sel,what,banned", [
    # CONJUNCTIVE, like rules.clean_descriptor: every field named must match.
    # Unioning the type's aliases with the group's made them an OR, so a rule for
    # type=coat AND group=outerwear also refused a puffer — a legitimate suggestion
    # gone, with no way for the reader to tell why. Raised by the reviewer.
    ({"type": "coat", "group": "outerwear"}, "wool coat", True),
    ({"type": "coat", "group": "outerwear"}, "puffer jacket", False),
    ({"color": "white", "type": "coat"}, "white wool coat", True),
    ({"color": "white", "type": "coat"}, "white puffer jacket", False),
    ({"color": "white", "type": "coat"}, "navy wool coat", False),
    # A single field still works on its own.
    ({"type": "coat"}, "wool overcoat", True),
    ({"group": "outerwear"}, "puffer jacket", True),
])
def test_every_field_a_ban_names_must_match(sel, what, banned):
    import shopping
    assert shopping._is_banned(what, "outer", [{"kind": "avoid_item", "a": sel}]) is banned


def test_a_brand_labelled_garment_is_recognised_by_its_kind():
    """An item labelled "Patagonia" of type `puffer` is still a puffer.

    _garment_aliases returns PHRASES, because a ban must match "down jacket" as a
    phrase and not on "down" alone. Ownership is asked of a word set, so the phrase
    matched nothing and the already-owned garment could be recommended. Same source,
    two shapes, one for each question. Raised by the pre-push reviewer, 2026-08-27.
    """
    import shopping
    closet = [{"label": "Patagonia", "type": "puffer"}]
    assert shopping._already_owned("down jacket", closet)
    assert shopping._already_owned("quilted jacket", closet)
    assert not shopping._already_owned("wool overcoat", closet)


def test_the_ban_still_reads_a_multi_word_alias_as_a_phrase():
    """The two shapes must not collapse into one.

    If ownership's word-splitting leaked into the ban, "down" alone would match
    again and a puffer ban would refuse a button-down shirt.
    """
    import shopping
    assert "down jacket" in shopping._garment_aliases("puffer")
    assert not shopping._is_banned("button-down shirt", "base",
                                   [{"kind": "avoid_item", "a": {"type": "puffer"}}])
