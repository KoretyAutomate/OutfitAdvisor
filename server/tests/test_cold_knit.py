"""
Below 5C felt a knit goes under the coat, ahead of the rules the search may give up
(user, 2026-11-26: "How can it recommend an outfit without a sweater....? Please fix"
— a white tee under the grey duffle coat, brown cargo pants, felt 2-6C, heavy rain).
The only sweater clashed with the cargo pants (utility trousers never with a knit),
so the tee kept every rule and won; warmth ranked after the rules.
"""
import funnel
from test_funnel import PARKA, run
from wardrobe_fixtures import SNEAK, TEE, g

CARGO = g("cargo0001", "brown cargo pants", "bottoms", "trousers", ["bottoms"], 3, colors=["brown"])
SWEATER = g("sweater01", "navy v-neck sweater", "tops", "sweater", ["base", "mid"], 4, colors=["navy"])
DUFFLE = {**PARKA, "id": "duffle001", "label": "grey duffle coat", "colors": ["grey"], "warmth": 5, "level": 2}


def _knit(o) -> bool:
    return SWEATER["id"] in (o.picks.get("base"), o.picks.get("mid"))


def test_2026_11_26_a_sweater_under_the_coat_at_two_degrees_even_with_cargo_pants():
    _, r = run(2, TEE, SWEATER, DUFFLE, CARGO, SNEAK, hi=6)
    assert r.outfits, r
    for o in r.outfits:
        assert _knit(o) and o.picks["outer"] == DUFFLE["id"], (o.picks, o.relaxed)


def test_the_tee_and_coat_is_still_served_when_no_knit_is_owned():
    _, r = run(2, TEE, DUFFLE, CARGO, SNEAK, hi=6)
    assert r.outfits and r.outfits[0].picks["outer"] == DUFFLE["id"], r


def test_from_five_degrees_a_warm_coat_over_the_tee_is_enough():
    """User, 2026-10-24 ("Coat over the top"): 5-8C under a warm coat, no knit asked."""
    coat = {**DUFFLE, "warmth": 4}   # a 5 is too warm at 6C (scale.too_warm)
    _, r = run(6, TEE, SWEATER, coat, CARGO, SNEAK, hi=10)
    o = r.outfits[0] if r.outfits else None
    assert o and o.picks["outer"] == coat["id"] and not _knit(o), [(o.picks, o.relaxed) for o in r.outfits]


def test_underlayered_is_the_coat_without_knitwear_below_five_only():
    import fit
    from test_funnel import CHINOS
    from wardrobe_fixtures import day
    d = day(2, TEE, SWEATER, DUFFLE, CHINOS, SNEAK, hi=6)
    c = funnel.Ctx(d, funnel.target_level(d.look))
    tee_coat = {"base": TEE["id"], "outer": DUFFLE["id"]}
    assert fit.underlayered(c, tee_coat)
    assert not fit.underlayered(c, {**tee_coat, "mid": SWEATER["id"]})
    assert not fit.underlayered(c, {"base": SWEATER["id"], "outer": DUFFLE["id"]}), "a sweater as the top"
    assert not fit.underlayered(c, {"base": TEE["id"]}), "no coat is check.py's no-coat, not this"
    d5 = day(5, TEE, SWEATER, DUFFLE, CHINOS, SNEAK, hi=9)
    assert not fit.underlayered(funnel.Ctx(d5, funnel.target_level(d5.look)), tee_coat), "5C: the boundary"
    d4 = day(4.9, TEE, SWEATER, DUFFLE, CHINOS, SNEAK, hi=9)
    assert fit.underlayered(funnel.Ctx(d4, funnel.target_level(d4.look)), tee_coat)


def test_dry_feet_still_count_below_five_when_no_knit_fits():
    """Codex review, 2026-11-26: folded into one weather flag, a missing knit erased the
    wet-feet penalty — chinos with mesh beat drawstrings with dry loafers at 2C."""
    from test_funnel import CHINOS, DRAWSTR, LOAFERS, MESH
    from wardrobe_fixtures import OXFORD
    # The sweater passes on its own (so a knit is "wearable") but no outfit can hold it:
    # every outfit lacks the knit, and only the separate wet flag tells them apart.
    ban = [{"kind": "avoid_pair", "a": {"type": "loafers"}, "b": {"type": "trousers", "color": "navy"}},
           {"kind": "avoid_pair", "a": {"type": "sweater"}, "b": {"type": "trousers"}}]
    from test_funnel import prefs
    _, r = run(2, OXFORD, SWEATER, PARKA, CHINOS, DRAWSTR, MESH, LOAFERS, hi=6, rain=90, isRain=True,
               p=prefs("office", rules=tuple(ban)))   # the drawstrings are a level down
    assert all(not _knit(o) for o in r.outfits)
    o = r.outfits[0]
    assert o.picks["footwear"] == LOAFERS["id"] and "wet" not in o.relaxed, (o.picks, o.relaxed)
    # The rank itself: both lack the knit; mesh gives up "wet", the drawstrings "band1"
    # — earlier on the ladder than band1, so one merged flag served the mesh.
    from wardrobe_fixtures import day
    d = day(2, OXFORD, SWEATER, PARKA, CHINOS, DRAWSTR, MESH, LOAFERS, hi=6, rain=90, isRain=True,
            prefs=prefs("office", rules=tuple(ban)))
    c = funnel.Ctx(d, funnel.target_level(d.look), frozenset({"colour", "belt", "texture", "wet", "band1"}))
    base = {"base": OXFORD["id"], "outer": PARKA["id"]}  # a shirt: on the office level
    shapes = [(("base", "outer"), {**base, "bottoms": CHINOS["id"], "footwear": MESH["id"]}),
              (("base", "outer"), {**base, "bottoms": DRAWSTR["id"], "footwear": LOAFERS["id"]})]
    got = sorted(funnel._evaluate(c, shapes, funnel.priority_for(c), frozenset(base) | {"mid"}), key=lambda o: o.rank)
    assert [o.picks["footwear"] for o in got] == [LOAFERS["id"], MESH["id"]], [(o.relaxed, o.rank[:6]) for o in got]


def test_no_wearable_knit_holds_nothing_aside():
    """Codex review, 2026-11-26: with no knit to wear, every coat outfit was held aside
    and the search walked every combination at every step for one that is not there."""
    import fit
    from test_funnel import CHINOS
    from wardrobe_fixtures import day
    tee_coat = {"base": TEE["id"], "outer": DUFFLE["id"]}
    d = day(2, TEE, DUFFLE, CHINOS, SNEAK, hi=6)
    assert not fit.underlayered(funnel.Ctx(d, funnel.target_level(d.look)), tee_coat), "no knit owned"
    banned = [{"kind": "avoid_item", "a": {"type": "sweater"}}]
    from test_funnel import prefs
    d = day(2, TEE, SWEATER, DUFFLE, CHINOS, SNEAK, hi=6, prefs=prefs(rules=tuple(banned)))
    assert not fit.underlayered(funnel.Ctx(d, funnel.target_level(d.look)), tee_coat), "the only knit is banned"
    tees = [g(f"tee{n:06d}", f"tee {n}", "tops", "t_shirt", ["base"], 1, colors=[c])
            for n, c in enumerate(("white", "black", "grey", "navy", "olive", "beige"))]
    _, r = run(2, *tees, DUFFLE, CHINOS, CARGO, SNEAK, hi=6)
    assert r.outfits and r.complete and r.exact == 0, (r.complete, r.exact)
