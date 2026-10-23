"""No rule gives way while some outfit keeps it (user, 2026-10-23).

The 04:00 outfit put a light blue long-sleeve polo under a black v-neck sweater:
"Why did knit on knit happened?" — then: "We need to make sure the selection is
nothing violating the rule. If there is truly no combination which does that, it
needs to mention that in the commentary ... it must try all the possible
combinations". A brute force over random closets agreed with the search 150/150;
main's beam, squeezed to one outfit, gave a rule up needlessly 5/60
(test_results/exhaustive_bruteforce_2026-10-23.txt)."""
from dataclasses import replace

import funnel
import rules
from test_funnel import (CHINOS, DRAWSTR, LOAFERS, WHITE_OX, assert_valid, dress, prefs, run)
from wardrobe_fixtures import JEANS, SNEAK, TEE, g, weather

INNER = g("innerls01", "white long-sleeve crewneck", "underwear", "thermal", ["inner"], 2, colors=["white"])
LB_POLO = g("lbpolo001", "Light blue long-sleeve polo", "tops", "polo", ["base", "mid", "outer"], 2,
            colors=["light blue"])
VNECK = g("vneck0001", "Black v-neck sweater", "tops", "sweater", ["base", "mid", "outer"], 3,
          colors=["black"], gauge="fine")
CARDIGAN = g("cardi0002", "grey cardigan", "tops", "cardigan", ["mid", "outer"], 3, colors=["grey"])


def test_2026_10_23_a_polo_never_goes_under_a_sweater_however_fine():
    for o in run(9, INNER, LB_POLO, VNECK, TEE, CHINOS, SNEAK, hi=15)[1].outfits:
        assert not (o.picks.get("base") == LB_POLO["id"] and o.picks.get("mid") == VNECK["id"]), o.picks
    # A cardigan still takes it.
    d, r = run(9, INNER, LB_POLO, CARDIGAN, CHINOS, SNEAK, hi=15)
    assert_valid(d, r)
    assert r.outfits[0].relaxed == ()


def test_only_the_polo_and_the_sweater_is_texture_given_up_and_said():
    d, r = run(9, INNER, LB_POLO, VNECK, CHINOS, SNEAK, hi=15)
    assert_valid(d, r)
    o = r.outfits[0]
    if o.picks.get("mid") == VNECK["id"]:
        assert "texture" in o.relaxed
        assert funnel.notes(o.relaxed)[0] == funnel.TRIED_ALL


def test_a_beam_that_cuts_every_legal_outfit_still_finds_one(monkeypatch):
    """Six white tees banned with the only jeans, a seventh navy one that is not —
    with the beam squeezed to one outfit, only the every-combination walk sees it."""
    monkeypatch.setattr(funnel, "WIDTHS", ((1, 1),))
    whites = [g(f"wtee{n:05d}", f"white tee {n}", "tops", "t_shirt", ["base"], 1, colors=["white"]) for n in range(6)]
    navy = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    ban = tuple(rules.clean_rules([{"kind": "avoid_pair", "a": {"type": "t_shirt", "color": "white"},
                                    "b": {"type": "jeans"}}]))
    d, r = run(20, *whites, navy, JEANS, SNEAK, hi=24, p=prefs(rules=ban))
    assert_valid(d, r)
    assert r.outfits[0].relaxed == (), [(o.picks["base"], o.relaxed) for o in r.outfits]
    assert r.complete


def test_with_the_walk_switched_off_the_same_closet_gives_a_rule_up(monkeypatch):
    """The control for the test above: it is the walk that keeps the rule."""
    monkeypatch.setattr(funnel, "WIDTHS", ((1, 1),))
    monkeypatch.setattr(funnel, "_exact", lambda ctx, priority, bound=None: ([], 0, True))
    a = {**g("atee00001", "red striped tee", "tops", "t_shirt", ["base"], 1, colors=["red"], pattern="striped"),
         "_ago": 7}
    b = {**g("btee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    loud = g("loudsnk01", "red striped sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["red"],
             pattern="striped")
    _, r = run(20, a, b, JEANS, loud, hi=24)
    monkeypatch.undo()
    _, exact = run(20, a, b, JEANS, loud, hi=24)
    assert r.outfits and r.outfits[0].relaxed, "the squeezed beam alone kept only the striped tee"
    assert exact.outfits[0].relaxed == () and exact.outfits[0].picks["base"] == b["id"]


def test_an_office_day_with_only_weekend_trousers_skips_the_walk_with_bare_legs():
    """Every outfit of the strict pass would lack the trousers they own: known before
    any is walked (87 garments took six minutes without it)."""
    d, r = run(10, WHITE_OX, DRAWSTR, LOAFERS, hi=19, p=prefs("office"))
    assert_valid(d, r)
    assert r.outfits[0].picks["bottoms"] == DRAWSTR["id"] and r.exact == 0


def test_every_rule_given_up_is_said_after_the_line_that_all_were_tried():
    gave = ("colour", "texture", "register")
    said = funnel.notes(gave)
    assert said[0] == funnel.TRIED_ALL
    assert said[1:] == [funnel.NOTES[k] for k in reversed(gave)], "all three, not the first two"
    assert funnel.notes(()) == []
    assert "time ran out" in funnel.notes(("colour",), complete=False)[0]


def test_turning_every_outfit_down_never_buys_a_broken_rule(monkeypatch):
    """The chooser says none; the search without them has only drawstring pants for
    an office day. The outfit that keeps the rules is served."""
    closet = [WHITE_OX, CHINOS, DRAWSTR, LOAFERS]
    out, seen = dress(monkeypatch, closet, weather(10, 19), prefs("office"),
                      [{"choice": 0, "reason": "too plain"}, {"choice": 1, "look": "", "lines": {}, "tip": ""}])
    assert out["picks"]["bottoms"] == CHINOS["id"]
    assert "Note:" not in out["text"]


# ── Codex review, 2026-10-23 (thread 01a1689a) ─────────────────────────────────────

def _tees_and_one_plain():
    loud = [g(f"rtee{n:05d}", f"red striped tee {n}", "tops", "t_shirt", ["base"], 1, colors=["red"],
              pattern="striped") for n in range(21)]
    plain = {**g("ntee00001", "navy tee", "tops", "t_shirt", ["base"], 1), "_ago": 0}
    # More jeans than tees: the walk takes the tees first (fewest candidates first).
    legs = [g(f"jean{n:05d}", f"grey jeans {n}", "bottoms", "jeans", ["bottoms"], 3, colors=["grey"])
            for n in range(25)]
    shoes = g("loudsnk01", "red striped sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["red"],
              pattern="striped")
    return [*loud, plain, *legs, shoes], plain


def test_a_full_beam_of_outfits_that_give_up_more_never_hides_one_that_gives_up_less():
    """An office day: every top is a step below it (band1). 550 tee-and-jeans pairs
    fill the beam with striped tees, which also break colour with the striped shoes;
    the navy tee, worn yesterday, breaks band1 alone."""
    closet, plain = _tees_and_one_plain()
    d, r = run(20, *closet, hi=24, p=prefs("office"))
    assert_valid(d, r)
    assert r.outfits[0].picks["base"] == plain["id"], r.outfits[0].relaxed
    assert r.outfits[0].relaxed == ("band1",)


def test_the_walk_goes_on_past_sixty_fits_while_something_could_give_up_less(monkeypatch):
    """With the beam finding nothing, the walk meets 525 striped-tee outfits (best by
    rotation, so first) before the navy one: stopping at CHECKED_CAP would serve one."""
    beam = funnel._pass
    monkeypatch.setattr(funnel, "_pass", lambda ctx, priority: ([], *beam(ctx, priority)[1:]))
    closet, plain = _tees_and_one_plain()
    _, r = run(20, *closet, hi=24, p=prefs("office"))
    assert r.outfits[0].picks["base"] == plain["id"] and r.complete


def test_turning_down_a_belt_mismatch_never_brings_back_a_colour_clash(monkeypatch):
    """cost() ranks colour ahead of belt; the re-search must still not trade one kept
    rule for another broken one."""
    import advisor
    from test_funnel import BLACK_BELT, BROWN_BELT
    closet = [WHITE_OX, CHINOS, LOAFERS, BLACK_BELT]
    first = run(14, *closet, hi=20)[1]
    first.outfits = [replace(o, relaxed=("belt",)) for o in first.outfits]
    other = run(14, WHITE_OX, CHINOS, LOAFERS, BROWN_BELT, hi=20)[1]
    other.outfits = [replace(o, relaxed=("colour",)) for o in other.outfits]
    calls = iter([first, other])
    monkeypatch.setattr(advisor.funnel, "search", lambda ctx, priority=None: next(calls))
    out, seen = dress(monkeypatch, [*closet, BROWN_BELT], weather(14, 20), prefs(),
                      [{"choice": 0, "reason": "no"}, {"choice": 1, "look": "", "lines": {}, "tip": ""}])
    assert len(seen["chooser"]) == 1, "the colour clash is never offered"
    assert out["picks"]["accessories"] != BROWN_BELT["id"]


def test_a_reroll_shows_the_same_tee_again_rather_than_break_a_rule():
    """The navy tee was on screen; every other tee clashes with the striped shoes. A
    re-roll keeps the rule and says nothing quieter fits only when it is true (Codex
    review, 2026-10-23, round 2)."""
    closet, plain = _tees_and_one_plain()
    d, r = run(20, *closet, hi=24, p=prefs("office", shown={"base": plain["id"]}))
    assert_valid(d, r)
    assert r.outfits[0].relaxed == ("band1",), r.outfits[0].relaxed
    assert r.outfits[0].picks["base"] == plain["id"]
