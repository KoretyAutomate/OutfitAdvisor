"""A stricter style check (user, 2026-10-18).

At 06:31 every round broke a hard fact, so the stylist never ran, and the fallback's
outfit — the one served — was never looked at. Replayed, the stylist scored that
outfit 4, 4, 3 and 4, once saying "the beige cargo pants clash with the polo and
sweater", and only a 2 or lower was ever sent back.
"""
import asyncio

import advisor
import fake_model
import picks as pk
import style
import stylist
from fake_model import outfit
from wardrobe_fixtures import CARDI, JEANS, KNIT_POLO, POLO, SNEAK, UNDER, weather

CLOSET = [UNDER, POLO, KNIT_POLO, CARDI, JEANS, SNEAK]
GOOD = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
OTHER = outfit(inner=UNDER["id"], base=KNIT_POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"],
               footwear=SNEAK["id"])
# A garment that is not in the wardrobe: hard, and fixable by the fallback.
HARD = outfit(inner=UNDER["id"], base=POLO["id"], mid="itm-nope", bottoms=JEANS["id"], footwear=SNEAK["id"])
def V(score, issue=""):
    return {"score": score, "issue": issue}


def dress(monkeypatch, answers, verdicts):
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    seen = fake_model.install(monkeypatch, answers, verdicts)
    out = asyncio.run(advisor.dress(weather(10), CLOSET, pk.Prefs(look=style.Look("casual", "man"))))
    return out, seen


# ── the threshold ─────────────────────────────────────────────────────────────

def test_a_three_that_names_a_problem_goes_back(monkeypatch):
    out, seen = dress(monkeypatch, answers=[GOOD, OTHER], verdicts=[V(3, "the belt fights the sweater"), V(4)])
    assert 'a second stylist scored it 3/5: "the belt fights the sweater"' in seen["prompts"][1]


def test_a_three_with_nothing_named_stands(monkeypatch):
    out, seen = dress(monkeypatch, answers=[GOOD, OTHER], verdicts=[V(3)])
    assert seen["calls"] == 1 and out["picks"]["base"] == POLO["id"]


def test_needs_another():
    assert stylist.needs_another(stylist.Verdict(2, ""))
    assert stylist.needs_another(stylist.Verdict(3, "clash"))
    assert not stylist.needs_another(stylist.Verdict(3, ""))
    assert not stylist.needs_another(stylist.Verdict(4, "minor"))
    assert not stylist.needs_another(None)


def test_the_facts_come_before_the_look_note(monkeypatch):
    _, seen = dress(monkeypatch, answers=[GOOD, OTHER], verdicts=[V(2, "too bulky"), V(4)])
    assert "a look note never overrides them" in seen["prompts"][1]


# ── the stylist on a round with hard issues ───────────────────────────────────

def test_a_round_with_a_hard_issue_is_reviewed_too(monkeypatch):
    _, seen = dress(monkeypatch, answers=[HARD, GOOD], verdicts=[V(2, "dull"), V(4)])
    assert seen["stylist"] == 2
    assert "itm-nope" in seen["prompts"][1] and 'scored it 2/5: "dull"' in seen["prompts"][1]


def test_late_hard_rounds_are_not_reviewed(monkeypatch):
    """Its review would cost the next revision its start."""
    monkeypatch.setattr(advisor, "REVISE_BY_S", stylist.STYLIST_TIMEOUT_S - 1)
    _, seen = dress(monkeypatch, answers=[HARD, GOOD], verdicts=[V(2, "dull"), V(4)])
    assert seen["stylist"] == 1, "only the clean second round"
    assert "scored it" not in seen["prompts"][1]


# ── the rescue round after the fallback ───────────────────────────────────────

def test_a_poor_fallback_outfit_gets_one_more_round_and_a_good_answer_is_taken(monkeypatch):
    out, seen = dress(monkeypatch, answers=[HARD, HARD, HARD, OTHER],
                      verdicts=[V(4), V(4), V(4), V(2, "flat"), V(4)])
    assert seen["calls"] == 1 + advisor.MAX_REVISIONS + 1
    assert "the outfit was corrected to:" in seen["prompts"][-1] and 'scored it 2/5: "flat"' in seen["prompts"][-1]
    assert "itm-" not in seen["prompts"][-1], "handles, never ids"
    assert out["picks"]["base"] == KNIT_POLO["id"]
    assert out["tip"] == "Have a good day.", "the taken answer's own words"


def test_a_rescue_that_breaks_a_hard_fact_is_not_taken(monkeypatch):
    out, seen = dress(monkeypatch, answers=[HARD, HARD, HARD, HARD],
                      verdicts=[V(4), V(4), V(4), V(2, "flat"), V(5)])
    assert seen["calls"] == 4 and out["picks"]["base"] == POLO["id"] and out["picks"]["mid"] != "itm-nope"
    assert out["tip"] == "", "the fallback's outfit, in plain words"


def test_a_rescue_the_stylist_still_dislikes_is_not_taken(monkeypatch):
    out, _ = dress(monkeypatch, answers=[HARD, HARD, HARD, OTHER],
                   verdicts=[V(4), V(4), V(4), V(2, "flat"), V(3, "still flat")])
    assert out["picks"]["base"] == POLO["id"]


def test_a_fallback_outfit_the_stylist_likes_is_served_without_another_round(monkeypatch):
    out, seen = dress(monkeypatch, answers=[HARD, HARD, HARD, OTHER], verdicts=[V(4), V(4), V(4), V(4)])
    assert seen["calls"] == 1 + advisor.MAX_REVISIONS and out["picks"]["base"] == POLO["id"]


def test_no_review_of_the_fallback_outfit_means_no_rescue(monkeypatch):
    _, seen = dress(monkeypatch, answers=[HARD, HARD, HARD, OTHER], verdicts=[V(4), V(4), V(4)])
    assert len(seen["prompts"]) == 1 + advisor.MAX_REVISIONS


def test_no_time_means_no_rescue(monkeypatch):
    monkeypatch.setattr(advisor, "RESCUE_MIN_LEFT_S", advisor.DEADLINE_S)
    _, seen = dress(monkeypatch, answers=[HARD, HARD, HARD, OTHER], verdicts=[V(4), V(4), V(4), V(2, "x"), V(4)])
    assert seen["calls"] == 1 + advisor.MAX_REVISIONS and seen["stylist"] == 3


def test_the_stylist_off_means_no_review_and_no_rescue(monkeypatch):
    seen = fake_model.install(monkeypatch, [HARD, HARD, HARD, OTHER], [V(2, "x")] * 5)
    monkeypatch.setenv("OUTFIT_STYLIST", "0")
    asyncio.run(advisor.dress(weather(10), CLOSET, pk.Prefs(look=style.Look("casual", "man"))))
    assert seen["stylist"] == 0 and seen["calls"] == 1 + advisor.MAX_REVISIONS


# ── one taste for the advisor and its judge ───────────────────────────────────

def test_the_advisor_and_the_stylist_are_told_the_same_principles():
    assert style.LOOK_PRINCIPLES in advisor.SYSTEM
    assert style.LOOK_PRINCIPLES in stylist.prompt({}, {}, style.Look("casual", "man"))
    assert "ONE accent colour" in style.LOOK_PRINCIPLES and "cargo" in style.LOOK_PRINCIPLES


def test_the_cold_morning_line_names_the_threshold():
    assert f"below {advisor.layers.COAT_BELOW_C}C felt" in advisor.SYSTEM


def test_the_review_never_outlives_the_request(monkeypatch):
    got = {}

    async def chat(messages, max_tokens, timeout=45, **kw):
        got["timeout"] = timeout
        return '{"score": 4, "issue": ""}'
    monkeypatch.setattr(stylist, "_chat", chat)
    wd = pk._index(CLOSET)
    asyncio.run(stylist.judge({"base": POLO["id"]}, wd, style.Look(), left=3.5))
    assert got["timeout"] == 3
    got.clear()
    assert asyncio.run(stylist.judge({"base": POLO["id"]}, wd, style.Look(), left=0.5)) is None and not got
