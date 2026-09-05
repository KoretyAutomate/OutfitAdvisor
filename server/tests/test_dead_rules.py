"""A rule that is stored, restated back, and can never fire (user, 2026-09-05).

> "I don't know how many times I have to update no inner with white Crew-neck
> T-shirt. this is being ignored."

Six times, by the journal. Every one accepted. What the live parser returned for
those words was:

    kind: avoid_pair
    a: {type: t_shirt, role: inner, color: white}
    b: {role: inner}
    restated: "Do not wear an inner layer with a white crew-neck t-shirt."

The restatement is exactly right, which is why nobody saw it. The rule under it is
dead twice: side `a` wants a white tee worn AS the inner layer, and both sides pin
the same slot, which `violations` skips because one garment cannot be both sides
of a pair. No outfit and no wardrobe can make it fire.

`clean_rule` validated the VOCABULARY and never the SATISFIABILITY — every field
in that rule is legal. These tests are the missing half.
"""
import asyncio
import json

import closet as closet_mod
import picks as pk
import rules

# The outfit the wearer kept being given.
BY_ITEM = {
    "u1": {"label": "white undershirt", "type": "undershirt", "group": "underwear",
           "colors": ["white"]},
    "t1": {"label": "white crew-neck tee", "type": "t_shirt", "group": "tops",
           "colors": ["white"]},
    "j1": {"label": "blue jeans", "type": "jeans", "group": "bottoms",
           "colors": ["blue"]},
}
WORN = {"inner": "u1", "base": "t1", "mid": None, "outer": None,
        "bottoms": "j1", "footwear": None, "accessories": None}

# Verbatim from POST /rule against the live model, 2026-09-05.
AS_PARSED = {"kind": "avoid_pair",
             "a": {"type": "t_shirt", "role": "inner", "color": "white"},
             "b": {"role": "inner"}}
# What the sentence actually means.
AS_MEANT = {"kind": "avoid_pair",
            "a": {"type": "undershirt", "role": "inner"},
            "b": {"type": "t_shirt", "role": "base", "color": "white"}}


# ── the shape that could never fire ────────────────────────────────────────────

def test_the_rule_the_user_was_given_is_refused():
    """Not stored. A rule kept and never fired is worse than a rejected one — the
    module says so in its first paragraph, and this is the case it missed."""
    assert rules.clean_rule(AS_PARSED) is None


def test_and_it_really_could_never_have_fired():
    """The reason it must be refused rather than kept: no outfit satisfies it. If
    this ever starts returning a violation, the rejection above is over-strict."""
    raw = {"kind": "avoid_pair", "a": dict(AS_PARSED["a"]), "b": dict(AS_PARSED["b"])}
    assert rules.violations([raw], WORN, BY_ITEM) == []
    # …not even with the tee moved into the slot side `a` demands.
    moved = dict(WORN, inner="t1", base=None)
    assert rules.violations([raw], moved, BY_ITEM) == []


def test_the_reason_names_the_slot_and_says_what_to_do():
    """It is fed back to the model as a corrective note, so it has to be actionable
    rather than merely true."""
    why = rules.dead_pair(AS_PARSED["a"], AS_PARSED["b"])
    assert "inner" in why
    assert "DIFFERENT slots" in why


def test_one_side_naming_a_slot_is_fine():
    """"no inner with a white tee" pins only one side, and that is satisfiable —
    over-rejecting here would throw away working rules."""
    r = {"kind": "avoid_pair", "a": {"role": "inner"},
         "b": {"type": "t_shirt", "color": "white"}}
    assert rules.clean_rule(r) is not None
    assert rules.violations([rules.clean_rule(r)], WORN, BY_ITEM)


def test_neither_side_naming_a_slot_is_fine():
    r = {"kind": "avoid_pair", "a": {"type": "undershirt"},
         "b": {"type": "t_shirt", "color": "white"}}
    assert rules.clean_rule(r) is not None


def test_two_of_the_same_thing_in_two_slots_is_still_a_real_rule():
    """"never two tees at once" is satisfiable — the slots differ even though the
    descriptions do not."""
    r = {"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "t_shirt"}}
    assert rules.clean_rule(r) is not None


def test_a_same_colour_rule_gets_the_same_treatment():
    """Same loop, same skip, same dead rule."""
    r = {"kind": "avoid_same_color", "a": {"role": "base", "type": "t_shirt"},
         "b": {"role": "base"}}
    assert rules.clean_rule(r) is None


def test_avoid_item_is_untouched():
    """One-sided rules have no pair loop to be skipped by."""
    r = {"kind": "avoid_item", "a": {"role": "inner", "type": "undershirt"}}
    assert rules.clean_rule(r) is not None


# ── a group its own type contradicts ───────────────────────────────────────────

def test_a_contradicting_group_is_dropped_so_the_rule_still_fires():
    """`_matches` requires every field, so {type: t_shirt, group: underwear}
    describes a garment that cannot exist. Here the answer is not a guess — the
    type is the more specific level and vocab files garments by it."""
    c = rules.clean_descriptor({"type": "t_shirt", "group": "underwear",
                                "color": "white"})
    assert c == {"type": "t_shirt", "color": "white"}
    r = {"kind": "avoid_pair", "a": {"type": "undershirt", "role": "inner"},
         "b": {"type": "t_shirt", "group": "underwear", "color": "white"}}
    assert rules.violations([rules.clean_rule(r)], WORN, BY_ITEM)


def test_a_group_its_type_agrees_with_is_kept():
    assert rules.clean_descriptor({"type": "t_shirt", "group": "tops"}) == {
        "type": "t_shirt", "group": "tops"}


def test_a_group_on_its_own_is_kept():
    assert rules.clean_descriptor({"group": "underwear"}) == {"group": "underwear"}


# ── what the wearer actually asked for, once parsed properly ───────────────────

def test_the_rule_as_meant_fires_on_the_outfit_they_complained_about():
    v = rules.violations([rules.clean_rule(AS_MEANT)], WORN, BY_ITEM)
    assert v, "the whole point"
    # The TEE is blamed, not the undershirt: the pair loop drops the outer of the
    # two slots. That is the wrong way round for this rule — see the note in
    # PLAN.md — but it is existing behaviour and the rule does fire.
    assert v[0]["slot"] in ("base", "inner")


def test_it_says_something_usable_in_the_prompt_too():
    """The dead rule rendered as "never use white t-shirt in the inner slot
    together with in the inner slot" — gibberish the model cannot act on either."""
    block = rules.prompt_block([AS_MEANT])
    assert "undershirt in the inner slot" in block
    assert "white t-shirt in the base slot" in block
    assert rules.prompt_block([AS_PARSED]) == ""


# ── and once it fires, it has to be honoured the way it was meant ──────────────
#
# Getting the rule to fire was only half of it. Blaming the visible layer — which
# is what the pair loop did until 2026-09-05 — honoured "no inner with white
# Crew-neck T-shirt" by taking away the T-SHIRT. See test_rules.py
# ::test_the_undershirt_is_what_a_pair_rule_drops for the unit; this is what it
# does to an actual morning.

WARM = {"lo": 20, "hi": 29, "feelsLo": 19, "feelsHi": 30, "desc": "Clear", "rain": 0,
        "wind": 2, "morning": 21, "midday": 28, "evening": 24, "swing": 9,
        "isRain": False, "isSnow": False, "code": 0}


def _garment(iid, label, cat, kind, group, colors):
    # Warmth 2 throughout: every one of these is a warm-day garment and the heat
    # ceiling must not fire, or a test about RULES would be measuring the weather.
    return {"id": iid, "label": label, "category": cat, "type": kind, "group": group,
            "roles": [cat], "colors": colors, "warmth": 2,
            "formality": ["casual"], "waterproof": False, "availableCount": 3}


UNDERSHIRT = _garment("g-under-01", "white undershirt", "inner", "undershirt",
                      "underwear", ["white"])
WHITE_TEE = _garment("g-tee-0001", "white crew-neck tee", "base", "t_shirt", "tops",
                     ["white"])
NAVY_TEE = _garment("g-tee-0002", "navy tee", "base", "t_shirt", "tops", ["navy"])
JEANS = _garment("g-jean-001", "blue jeans", "bottoms", "jeans", "bottoms",
                 ["blue"])
SNEAKERS = _garment("g-shoe-001", "sneakers", "footwear", "sneakers", "footwear",
                    ["white"])


def _run(closet, handles):
    """One /advice generation with the model returning exactly what the wearer
    complained about: the undershirt under the white crew-neck tee."""
    reply = json.dumps({"picks": handles, "bullets": [
        "Inner: the white undershirt keeps you fresh.",
        "Base: the white crew-neck tee is cool.",
        "Bottoms: the blue jeans.", "Footwear: sneakers."],
        "missing": [], "tip": "Nice day."})

    async def fake_chat(messages, max_tokens, timeout=45, temperature=0.4):
        return reply

    real, closet_mod._chat = closet_mod._chat, fake_chat
    try:
        prefs = pk.Prefs.of([AS_MEANT], False, None, None)
        return asyncio.run(
            closet_mod.closet_outfit(WARM, "man", "casual", closet, prefs))
    finally:
        closet_mod._chat = real


def test_the_wearer_keeps_the_shirt_and_loses_the_undershirt():
    out = _run([UNDERSHIRT, WHITE_TEE, NAVY_TEE, JEANS, SNEAKERS],
               {"inner": "i1", "base": "i2", "mid": None, "outer": None,
                "bottoms": "i4", "footwear": "i5", "accessories": None})
    assert out is not None
    assert out["picks"]["inner"] is None
    assert out["picks"]["base"] == WHITE_TEE["id"], "they asked to keep the tee"


def test_a_wardrobe_with_one_top_still_leaves_them_dressed():
    """The case that did real harm. Blaming the tee took away the only top they
    own: jeans, sneakers and nothing above the waist — and `base` reported as a
    wardrobe gap, which the shopping list answers by recommending a shirt they
    already have."""
    out = _run([UNDERSHIRT, WHITE_TEE, JEANS, SNEAKERS],
               {"inner": "i1", "base": "i2", "mid": None, "outer": None,
                "bottoms": "i3", "footwear": "i4", "accessories": None})
    assert out is not None
    assert out["picks"]["base"] == WHITE_TEE["id"]
    assert out["picks"]["inner"] is None
    assert out["missing"] == [], "a rule they chose is not a hole in the wardrobe"


def test_a_garment_banned_OUTRIGHT_is_still_a_wardrobe_gap():
    """The other half, so the exclusion above is not simply "rules never make
    gaps". "Never wear my only undershirt" leaves the wearer genuinely without one,
    and the shopping list is right to hear about it."""
    ban_item = {"kind": "avoid_item", "a": {"type": "undershirt", "role": "inner"}}
    reply = json.dumps({"picks": {"inner": "i1", "base": "i2", "mid": None,
                                  "outer": None, "bottoms": "i3", "footwear": "i4",
                                  "accessories": None},
                        "bullets": ["Inner: the undershirt.", "Base: the tee.",
                                    "Bottoms: jeans.", "Footwear: sneakers."],
                        "missing": [], "tip": "Nice day."})

    async def fake_chat(messages, max_tokens, timeout=45, temperature=0.4):
        return reply

    real, closet_mod._chat = closet_mod._chat, fake_chat
    try:
        prefs = pk.Prefs.of([ban_item], False, None, None)
        out = asyncio.run(closet_mod.closet_outfit(
            WARM, "man", "casual", [UNDERSHIRT, WHITE_TEE, JEANS, SNEAKERS], prefs))
    finally:
        closet_mod._chat = real
    assert out is not None
    assert out["picks"]["inner"] is None
    assert "inner" in out["missing"], "an outright ban on the only one IS a gap"


def test_an_outright_ban_wins_when_a_slot_breaks_both_kinds():
    """A slot can break two rules at once, and only one of them excuses the gap.

    "Never the grey undershirt" and "no undershirt with the white tee" both fire on
    `inner` when that is what is worn. Reading only the combination reason hid a
    real gap: the outright ban means no legal garment is available for that slot
    whatever the pair rule also said. Raised by the pre-push reviewer, 2026-09-05.
    """
    grey = _garment("g-under-02", "grey undershirt", "inner", "undershirt",
                    "underwear", ["grey"])
    both = [AS_MEANT,
            {"kind": "avoid_item", "a": {"type": "undershirt", "color": "grey"}}]
    reply = json.dumps({"picks": {"inner": "i1", "base": "i2", "mid": None,
                                  "outer": None, "bottoms": "i3", "footwear": "i4",
                                  "accessories": None},
                        "bullets": ["Inner: the grey undershirt.", "Base: the tee.",
                                    "Bottoms: jeans.", "Footwear: sneakers."],
                        "missing": [], "tip": "Nice day."})

    async def fake_chat(messages, max_tokens, timeout=45, temperature=0.4):
        return reply

    real, closet_mod._chat = closet_mod._chat, fake_chat
    try:
        out = asyncio.run(closet_mod.closet_outfit(
            WARM, "man", "casual", [grey, WHITE_TEE, JEANS, SNEAKERS],
            pk.Prefs.of(both, False, None, None)))
    finally:
        closet_mod._chat = real
    assert out is not None
    assert out["picks"]["inner"] is None
    # The only undershirt they own is banned outright, so they really are without
    # one — unlike the pure-combination case above.
    assert "inner" in out["missing"], out["missing"]


def test_the_unit_reports_only_the_slots_where_every_reason_was_a_combination():
    """The seam itself, so the rule above cannot be satisfied by accident."""
    by = {"u": {"id": "u", "type": "undershirt", "group": "underwear",
                "colors": ["grey"]},
          "t": {"id": "t", "type": "t_shirt", "group": "tops", "colors": ["white"]}}
    picks_combo = {"inner": "u", "base": "t"}
    _n, _c, combo = pk._enforce_user_rules(dict(picks_combo), by, [AS_MEANT], 1)
    assert combo == {"inner"}
    _n, _c, mixed = pk._enforce_user_rules(
        dict(picks_combo), by,
        [AS_MEANT, {"kind": "avoid_item", "a": {"type": "undershirt"}}], 1)
    assert mixed == set(), "one outright ban is enough to make it a real gap"


def test_only_underwear_can_occupy_inner():
    """What makes `_LOSES_A_PAIR` safe to key on the SLOT rather than the garment.

    The pre-push reviewer read the inner-last ordering as a general change to every
    pair involving that slot, and objected that a rule pairing "an inner-layer
    shirt" with a scarf would now drop the shirt and leave the wearer without a
    foundational top. That outfit cannot be built: vocab.reconcile strips the
    `inner` role from anything that is not underwear — the 2026-08-18 "wear your tee
    under your tee" fix — so the only garments that reach the inner slot are an
    undershirt or a thermal, and both are exactly the optional layer the ordering
    assumes.

    Pinned here so the rejection is checkable rather than an argument, and so the
    day somebody loosens normalize_roles this fails instead of quietly sending
    people out without a shirt.
    """
    import vocab

    for cat, group, roles, kind in (
        ("inner", "tops", ["inner", "base"], "t_shirt"),
        ("base", "tops", ["inner", "base"], "shirt"),
        ("accessories", "accessories", ["inner"], "scarf"),
        ("mid", "knitwear", ["inner", "mid"], "sweater"),
    ):
        _c, g, _k, r = vocab.reconcile(cat, group, roles, kind)
        assert "inner" not in r, f"{kind} kept the inner role"
        assert g != "underwear", f"{kind} was filed as underwear"

    # And what legitimately can — all of it underwear, and all but two withheld
    # from the outfit slots entirely.
    inner_types = [t for t in vocab.TYPES["underwear"]
                   if t not in vocab.NON_SLOT_TYPES]
    assert inner_types == ["undershirt", "thermal"], inner_types
    for kind in inner_types:
        _c, g, _k, r = vocab.reconcile("inner", "underwear", ["inner"], kind)
        assert r == ["inner"] and g == "underwear"

    # The TABLE that makes all of the above true, asserted directly. reconcile's
    # step 5 demotes a stated `inner` whenever the group does not allow it, so this
    # single row is the whole guarantee — and the loop above passes without it,
    # because a tee also fails the type/category checks earlier for its own reasons.
    # Naming the load-bearing line is the difference between a test that would catch
    # a regression here and one that merely happens to agree with the answer.
    owns_inner = [g for g, cats in vocab.GROUP_CATEGORIES.items() if "inner" in cats]
    assert owns_inner == ["underwear"], owns_inner
