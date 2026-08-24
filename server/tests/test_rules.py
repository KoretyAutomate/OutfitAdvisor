"""The wearer's own rules are ENFORCED, not merely requested (2026-08-24).

User: "I got white V-neck inner + white T recommendation. this combination shall
be banned."

Two ways to honour that: put the sentence in the prompt and hope, or make it
checkable and check it. The prompt block exists to get it right first time; these
tests cover the part that makes the promise true when it does not — because prose
in a prompt is followed most of the time, and "most mornings" is not a ban.

Verified live on 2026-08-24 against the real 122B: with the banned pair as the only
all-white option, it was served 3 times out of 3 without the rule and 0 times out
of 3 with it.
"""
import pytest

import rules

WHITE_INNER = {"id": "i1", "type": "undershirt", "group": "underwear",
               "category": "inner", "colors": ["White"]}
WHITE_TEE = {"id": "i2", "type": "t_shirt", "group": "tops",
             "category": "base", "colors": ["white"]}
NAVY_TEE = {"id": "i3", "type": "t_shirt", "group": "tops",
            "category": "base", "colors": ["navy"]}
GREY_INNER = {"id": "i4", "type": "undershirt", "group": "underwear",
              "category": "inner", "colors": ["grey"]}
BY_ITEM = {i["id"]: i for i in (WHITE_INNER, WHITE_TEE, NAVY_TEE, GREY_INNER)}

BAN = {"kind": "avoid_pair",
       "a": {"type": "undershirt", "color": "white"},
       "b": {"type": "t_shirt", "color": "white"}}


def test_the_users_own_example():
    """The exact outfit that prompted the feature."""
    v = rules.violations([BAN], {"inner": "i1", "base": "i2"}, BY_ITEM)
    assert len(v) == 1
    # The slot to clear is the SECOND side: the first is what the outfit is built
    # around, so dropping the addition is the smaller change.
    assert v[0]["slot"] == "base"


def test_breaking_either_half_is_allowed():
    """A ban on a COMBINATION must not ban its parts."""
    assert not rules.violations([BAN], {"inner": "i1", "base": "i3"}, BY_ITEM)
    assert not rules.violations([BAN], {"inner": "i4", "base": "i2"}, BY_ITEM)
    assert not rules.violations([BAN], {"inner": "i4", "base": "i3"}, BY_ITEM)


def test_colour_matching_ignores_case():
    """The classifier writes "White", the user types "white"."""
    assert rules.violations([BAN], {"inner": "i1", "base": "i2"}, BY_ITEM)


def test_a_rule_never_matches_one_item_against_itself():
    """One garment cannot be both sides of a pair — it is worn in one slot."""
    same = {"kind": "avoid_pair", "a": {"type": "t_shirt"}, "b": {"type": "t_shirt"}}
    assert not rules.violations([same], {"base": "i2"}, BY_ITEM)
    # But two DIFFERENT tees in two slots genuinely is the pair.
    two = dict(BY_ITEM, i5={"id": "i5", "type": "t_shirt", "group": "tops",
                            "category": "mid", "colors": ["black"]})
    assert rules.violations([same], {"base": "i2", "mid": "i5"}, two)


def test_role_means_the_slot_it_was_worn_in():
    """A shirt worn as the base today is a base today, whatever else it could be."""
    r = {"kind": "avoid_item", "a": {"role": "mid", "type": "t_shirt"}}
    assert not rules.violations([r], {"base": "i2"}, BY_ITEM)
    assert rules.violations([r], {"mid": "i2"}, BY_ITEM)


def test_avoid_same_color_needs_a_shared_colour():
    r = {"kind": "avoid_same_color", "a": {"role": "inner"}, "b": {"role": "base"}}
    assert rules.violations([r], {"inner": "i1", "base": "i2"}, BY_ITEM)
    assert not rules.violations([r], {"inner": "i4", "base": "i2"}, BY_ITEM)


@pytest.mark.parametrize("bad", [
    {"kind": "nonsense", "a": {"type": "t_shirt"}, "b": {"type": "jeans"}},
    {"kind": "avoid_pair", "a": {"type": "t_shirt"}},              # no second side
    {"kind": "avoid_pair", "a": {}, "b": {"type": "jeans"}},       # empty side
    {"kind": "avoid_item", "a": {"type": "not_a_garment"}},        # unknown type
    {"kind": "avoid_item", "a": {"role": "elbow"}},                # unknown slot
    "not a dict", None, 42,
])
def test_unenforceable_rules_are_dropped(bad):
    """A rule that could never fire must not be stored looking like it will.

    That is the worst outcome available here: the user believes the advisor was
    told, and every future outfit quietly ignores them.
    """
    assert rules.clean_rule(bad) is None


def test_an_empty_descriptor_is_not_a_universal_ban():
    """{} matches EVERY garment, so it would turn avoid_item into "own nothing"."""
    assert rules.clean_descriptor({}) is None
    assert rules.clean_rule({"kind": "avoid_item", "a": {}}) is None


def test_the_rule_list_is_bounded():
    many = [dict(BAN, id=str(i)) for i in range(200)]
    assert len(rules.clean_rules(many)) <= rules.MAX_RULES


def test_junk_in_the_list_does_not_lose_the_good_rules():
    """A stale rule from an older build must not cost the user their advice."""
    got = rules.clean_rules([{"kind": "bogus"}, BAN, None, {"a": {}}])
    assert len(got) == 1 and got[0]["kind"] == "avoid_pair"


def test_the_prompt_block_states_the_rule():
    block = rules.prompt_block([BAN])
    assert "never use" in block and "white" in block and "t-shirt" in block


def test_no_rules_adds_nothing_to_the_prompt():
    assert rules.prompt_block([]) == ""


def test_a_rule_about_clothes_nobody_is_wearing_does_not_fire():
    assert not rules.violations([BAN], {"footwear": "i3"}, {"i3": NAVY_TEE})
    assert not rules.violations([BAN], {}, BY_ITEM)
