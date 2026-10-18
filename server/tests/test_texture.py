"""What goes under a sweater must suit its knit (user, 2026-10-18).

The 07:09 outfit: a navy knit polo under a navy reindeer sweater — "Fabric of polo
and sweater doesn't go well". The name said "reindeer" and the advisor read it as a
plain sweater; the fabric the photo scan reads was never sent. Replayed on the live
model: polo under the reindeer sweater 1 in 6 before, 0 in 8 after (with fabric) and
0 in 6 (without). Evidence: test_results/advisor_review_2026-10-18.txt.
"""
import advisor
import check
import picks as pk
import style
import stylist
from schemas import ClosetItem
from wardrobe_fixtures import JEANS, POLO, SNEAK, g

REINDEER = g("reindeer1", "navy reindeer sweater", "tops", "sweater", ["mid"], 4)


def test_knit_patterns_are_patterns():
    for name in ("navy reindeer sweater", "Fair Isle jumper", "fairisle crew", "Nordic knit",
                 "snowflake cardigan", "argyle vest", "ノルディックセーター"):
        assert style.pattern_of({"label": name}) == "print", name
    assert style.pattern_of({"label": "charcoal merino crew-neck"}) is None


def test_the_texture_rule_is_one_taste_for_the_advisor_and_its_judge():
    assert "never a polo" in style.LOOK_PRINCIPLES and "Fair Isle" in style.LOOK_PRINCIPLES
    assert style.LOOK_PRINCIPLES in advisor.SYSTEM
    assert style.LOOK_PRINCIPLES in stylist.prompt({}, {}, style.Look())


def test_the_advisor_sees_the_fabric_and_the_pattern():
    d = check.Day.of({"lo": 3, "hi": 14, "morning": 3, "midday": 12, "evening": 10, "swing": 11, "rain": 0,
                      "wind": 2, "isRain": False, "isSnow": False, "code": 0, "desc": "Clear"},
                     pk._index([REINDEER]), pk.Prefs())
    line = advisor._line({**REINDEER, "fabric": "wool"}, "i1", d)
    assert "fabric: wool" in line and "pattern: print" in line
    assert "fabric" not in advisor._line(REINDEER, "i1", d), "unknown fabric says nothing"


def test_the_stylist_sees_the_fabric():
    by = {POLO["id"]: {**POLO, "fabric": "knit"}, REINDEER["id"]: REINDEER, JEANS["id"]: JEANS, SNEAK["id"]: SNEAK}
    p = stylist.prompt({"base": POLO["id"], "mid": REINDEER["id"]}, by, style.Look())
    assert "fabric: knit" in p and "navy reindeer sweater | sweater | colours: navy | pattern: print |" in p


def test_the_fabric_survives_the_request():
    item = ClosetItem(**{**POLO, "fabric": "Knit"})
    assert item.fabric == "knit"
    assert ClosetItem(**{**POLO, "fabric": "unobtainium"}).fabric is None
