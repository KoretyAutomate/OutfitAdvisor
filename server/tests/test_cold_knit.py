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
