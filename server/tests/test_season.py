"""The seasonal closet (user, 2026-11-18): "I don't need shorts nor summer pants to be
in a part of choices during winter. In summer, I don't need jacket nor sweater ... this
morning I got a summer pants recommendation which is completely off."

Two layers (season.py): the actual weather's cold floor now covers the legs
(scale.too_cold_for_legs, layers.underdressed), and the home climate's normal for the
date ranks out-of-season garments below in-season ones, never above comfort."""
import pytest
from fastapi.testclient import TestClient

import app as srv
import fake_model
import funnel
import layers
import picks as pk
import scale
import season
from check import Day
from wardrobe_fixtures import CARDI, JACKET, OXFORD, SHORTS, SNEAK, SWEATER, TEE, g, weather

SUMMER_TR = g("linentr01", "beige linen trousers", "bottoms", "trousers", ["bottoms"], 1, colors=["beige"])
CHINOS = g("chinos001", "navy chinos", "bottoms", "trousers", ["bottoms"], 3)
LIGHT_TR = g("lighttr01", "stone cotton trousers", "bottoms", "trousers", ["bottoms"], 2, colors=["stone"])
SANDALS = g("sandals01", "brown sandals", "footwear", "sandals", ["footwear"], 1, colors=["brown"])
PUFFER = g("puffer001", "black down puffer", "outerwear", "puffer", ["outer"], 5, colors=["black"])

# A Tokyo-like year, January first: [normal low, normal high].
TOKYO = [[1, 10], [2, 11], [5, 14], [10, 19], [15, 23], [19, 26],
         [23, 30], [24, 31], [21, 27], [15, 22], [9, 17], [4, 12]]
JAN, JUL, NOV = season.Normal(1, 10), season.Normal(23, 30), season.Normal(9, 17)


# ── the leg floor: unit ────────────────────────────────────────────────────────────

def test_a_summer_leg_garment_is_too_cold_below_12c_on_the_absolute_scale():
    assert scale.too_cold_for_legs(SUMMER_TR, 11.9)
    assert not scale.too_cold_for_legs(SUMMER_TR, 12.0)


def test_nothing_warmer_than_summer_wear_is_ever_too_cold_for_the_legs():
    # Chinos and sneakers (warmth 2) are winter wear too; only warmth 1 is refused.
    assert not scale.too_cold_for_legs(LIGHT_TR, -20)
    assert not scale.too_cold_for_legs(SNEAK, -20)
    assert scale.too_cold_for_legs(SANDALS, -20)


def test_the_leg_floor_reads_the_garments_own_scale():
    # Graded against a hot climate: warmth 1 there answers to ~28C, warmth 3 to ~24C,
    # so 18C asks for a 5 and a summer garment is too cold well above 12C.
    tropical = {**SUMMER_TR, "warmthScale": "home", "warmthAnchors": [24.0, 26.0, 28.0]}
    assert scale.too_cold_for_legs(tropical, 18.0)
    assert not scale.too_cold_for_legs(SUMMER_TR, 18.0)


def _wd(*items):
    return pk._index(list(items))


def _ud(item, slot, closet, plan, peak, user_rules=()):
    """layers.underdressed on a day of these temperatures, closet and rules."""
    return layers.underdressed(item, slot, Day.of(weather(plan, peak), _wd(*closet),
                                                    pk.Prefs.of(list(user_rules))))


def test_underdressed_only_when_a_warmer_wearable_alternative_is_owned():
    assert _ud(SUMMER_TR, "bottoms", [SUMMER_TR, CHINOS], 8, 12)
    assert not _ud(SUMMER_TR, "bottoms", [SUMMER_TR, SHORTS], 8, 12), \
        "owning nothing warmer makes them the trousers"
    assert not _ud(CHINOS, "bottoms", [SUMMER_TR, CHINOS], 8, 12)


def test_an_alternative_they_banned_is_no_alternative():
    ban = [{"kind": "avoid_item", "a": {"type": "trousers", "color": "navy"}}]
    assert not _ud(SUMMER_TR, "bottoms", [SUMMER_TR, CHINOS], 8, 12, ban)


def test_an_alternative_too_warm_for_the_afternoon_is_no_alternative():
    # 11C morning, 30C afternoon: chinos are too warm by three, so the linen stays.
    assert not _ud(SUMMER_TR, "bottoms", [SUMMER_TR, CHINOS], 11, 30)


def test_the_torso_is_never_judged_by_the_leg_floor():
    assert not _ud(TEE, "base", [TEE, OXFORD], 2, 6)


# ── the normal day: unit ───────────────────────────────────────────────────────────

def test_mid_month_is_that_months_normal():
    assert season.normal_for(TOKYO, "2026-07-16") == season.Normal(23.0, 30.0)


def test_new_year_reads_between_december_and_january():
    n = season.normal_for(TOKYO, "2026-01-01")
    assert 1 < n.lo < 4 and 10 < n.hi < 12


def test_late_december_reads_toward_january():
    assert season.normal_for(TOKYO, "2026-12-31").lo < season.normal_for(TOKYO, "2026-12-16").lo


def test_no_normals_or_no_date_means_no_season():
    assert season.normal_for(None, "2026-07-16") is None
    assert season.normal_for(TOKYO, "not-a-date") is None


@pytest.mark.parametrize("bad", [TOKYO[:11], [[5, 1]] + TOKYO[1:], [["x", 1]] + TOKYO[1:],
                                 [[1, 99]] + TOKYO[1:], "TOKYO", None, [[1, 2, 3]] + TOKYO[1:]])
def test_malformed_normals_are_dropped(bad):
    assert season.clean_normals(bad) is None


def test_well_formed_normals_are_kept():
    assert season.clean_normals(TOKYO) == [[float(a), float(b)] for a, b in TOKYO]


# ── out of season: unit ────────────────────────────────────────────────────────────

def test_summer_legs_are_out_of_season_in_january_and_in_season_in_july():
    assert season.out_of_season(SHORTS, "bottoms", JAN)
    assert season.out_of_season(SANDALS, "footwear", JAN)
    assert not season.out_of_season(SHORTS, "bottoms", JUL)


def test_a_sweater_and_a_jacket_are_out_of_season_in_july():
    assert season.out_of_season(SWEATER, "mid", JUL)
    assert season.out_of_season(JACKET, "outer", JUL)
    assert season.out_of_season(SWEATER, "base", JUL)


def test_a_coat_is_in_season_in_november_a_deep_winter_puffer_is_not():
    coat = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
    assert not season.out_of_season(coat, "outer", NOV)
    assert season.out_of_season(PUFFER, "outer", NOV)
    assert not season.out_of_season(PUFFER, "outer", JAN)


def test_the_overrides():
    assert not season.out_of_season({**SHORTS, "season": "all"}, "bottoms", JAN)
    assert season.out_of_season({**CHINOS, "season": "warm"}, "bottoms", NOV)
    assert not season.out_of_season({**CHINOS, "season": "warm"}, "bottoms", JUL)
    assert season.out_of_season({**CHINOS, "season": "cold"}, "bottoms", JUL)
    assert not season.out_of_season({**CHINOS, "season": "cold"}, "bottoms", JAN)
    assert season.out_of_season({**SHORTS, "season": "bogus"}, "bottoms", JAN), "unknown reads as auto"


def test_the_warm_and_cold_months_split_at_12c_with_no_gap():
    warm, cold = {**CHINOS, "season": "warm"}, {**CHINOS, "season": "cold"}
    for lo in (11.9, 12.0):
        n = season.Normal(lo, lo + 8)
        assert season.out_of_season(warm, "bottoms", n) != season.out_of_season(cold, "bottoms", n)
    assert season.out_of_season(warm, "bottoms", season.Normal(11.9, 20))
    assert not season.out_of_season(warm, "bottoms", season.Normal(12.0, 20))


def _day(t, hi, normal, *items):
    return Day.of(weather(t, hi), pk._index(list(items)), pk.Prefs(normal=normal))


def test_a_leaveable_slot_always_counts_and_trousers_only_with_an_in_season_pair():
    d = _day(20, 24, JUL, TEE, JACKET, CHINOS)
    assert season.counts(d, "outer", JACKET["id"]), "leaving the jacket off is in season"
    assert not season.counts(d, "bottoms", CHINOS["id"]), "the only trousers are what they have"
    d2 = _day(20, 24, JUL, TEE, JACKET, CHINOS, SHORTS)
    assert season.counts(d2, "bottoms", CHINOS["id"])


def test_without_a_normal_nothing_is_out_of_season():
    assert season.mismatches(_day(20, 24, None, TEE, JACKET), {"outer": JACKET["id"], "base": TEE["id"]}) == 0


def test_the_last_resort_lets_summer_legs_back_in():
    d = _day(8, 12, None, TEE, SUMMER_TR, CHINOS, SNEAK)
    assert funnel._keeps(funnel.Ctx(d, 2), "bottoms", SUMMER_TR["id"], 0) == "cold"
    assert funnel._keeps(funnel.Ctx(d, 2, cold_ok=True), "bottoms", SUMMER_TR["id"], 0) != "cold"


# ── end to end, through /advice ────────────────────────────────────────────────────

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    return TestClient(srv.app)


def advise(api, monkeypatch, wx, closet, normals=None, recent=None):
    async def fetch(lat, lon, day):
        return wx
    monkeypatch.setattr(srv.weather, "fetch_weather", fetch)
    fake_model.install(monkeypatch, [], choices=[fake_model.choice(1)] * 4)
    body = {"lat": 1, "lon": 1, "occasion": "off", "gender": "man", "closet": closet,
            **({"normals": normals} if normals else {}), **({"recent": recent} if recent else {})}
    r = api.post("/advice", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_morning_of_2026_11_18_no_summer_trousers_on_a_cold_morning(api, monkeypatch):
    # The chinos were worn yesterday, so rotation alone would pick the linen.
    out = advise(api, monkeypatch, weather(8, 12, date="2026-11-18"),
                 [TEE, OXFORD, SWEATER, JACKET, SUMMER_TR, CHINOS, SNEAK], recent={CHINOS["id"]: 1})
    assert out["picks"]["bottoms"] == CHINOS["id"]


def test_summer_trousers_still_go_out_when_they_are_all_there_is(api, monkeypatch):
    out = advise(api, monkeypatch, weather(8, 12, date="2026-11-18"), [TEE, OXFORD, SWEATER, JACKET, SUMMER_TR, SNEAK])
    assert out["picks"]["bottoms"] == SUMMER_TR["id"], "never bare legs"
    assert "bottoms" in out["missing"], "and the shopping list hears about it"


def test_a_freak_warm_november_day_keeps_the_shorts_away(api, monkeypatch):
    closet = [TEE, SHORTS, LIGHT_TR, SNEAK]
    wx = weather(19, 24, date="2026-11-20")
    plain = advise(api, monkeypatch, wx, closet, recent={LIGHT_TR["id"]: 1})
    seasonal = advise(api, monkeypatch, wx, closet, TOKYO, recent={LIGHT_TR["id"]: 1})
    assert plain["picks"]["bottoms"] == SHORTS["id"], "rotation picks the shorts without a season"
    assert seasonal["picks"]["bottoms"] == LIGHT_TR["id"], "November is not shorts season"


def test_season_never_beats_the_actual_weather(api, monkeypatch):
    # A freak hot November day with only shorts and heavy chinos: the chinos are too
    # warm for the afternoon, so the shorts go out, season or not.
    out = advise(api, monkeypatch, weather(22, 30, date="2026-11-20"), [TEE, SHORTS, CHINOS, SNEAK], TOKYO)
    assert out["picks"]["bottoms"] == SHORTS["id"]


def test_a_cool_july_morning_gets_no_jacket_or_sweater(api, monkeypatch):
    out = advise(api, monkeypatch, weather(18, 27, date="2026-07-15"),
                 [TEE, OXFORD, CARDI, SWEATER, JACKET, CHINOS, SHORTS, SNEAK], TOKYO)
    assert not out["picks"].get("mid") and not out["picks"].get("outer"), out["picks"]


def test_a_cold_july_morning_still_gets_the_jacket(api, monkeypatch):
    # 6C in July: comfort first. The jacket is out of season and goes on anyway.
    out = advise(api, monkeypatch, weather(6, 14, date="2026-07-15"), [TEE, OXFORD, JACKET, CHINOS, SNEAK], TOKYO)
    assert out["picks"].get("outer") == JACKET["id"]


def test_all_year_shorts_stay_in_the_running_in_november(api, monkeypatch):
    shorts = {**SHORTS, "season": "all"}
    out = advise(api, monkeypatch, weather(19, 24, date="2026-11-20"), [TEE, shorts, LIGHT_TR, SNEAK], TOKYO,
                 recent={LIGHT_TR["id"]: 1})
    assert out["picks"]["bottoms"] == SHORTS["id"]


def test_an_ungraded_leg_garment_reads_as_warmth_3_never_too_cold():
    ungraded = {k: v for k, v in SUMMER_TR.items() if k != "warmth"}
    assert not scale.too_cold_for_legs(ungraded, -20)


def test_a_dress_worn_as_the_base_covers_the_legs_and_a_top_does_not():
    summer_dress = g("sundress1", "linen sundress", "onepiece", "dress", ["base"], 1)
    assert layers.covers_legs("base", summer_dress)
    assert not layers.covers_legs("base", TEE)
    assert not layers.covers_legs("mid", summer_dress)
    winter_dress = g("knitdrs01", "knit dress", "onepiece", "dress", ["base"], 3)
    assert _ud(summer_dress, "base", [summer_dress, winter_dress], 8, 12)


def test_dates_between_two_month_middles_read_off_the_line_exactly():
    # 1 July: 0.516 of the way from mid-June [19, 26] to mid-July [23, 30].
    assert season.normal_for(TOKYO, "2026-07-01") == season.Normal(21.1, 28.1)
    # 31 January: 0.484 of the way from mid-January [1, 10] to mid-February [2, 11].
    assert season.normal_for(TOKYO, "2026-01-31") == season.Normal(1.5, 10.5)


def test_normals_at_the_edges_of_the_range():
    assert season.clean_normals([[-90, 60]] + TOKYO[1:]) is not None
    assert season.clean_normals([[5, 5]] + TOKYO[1:]) is not None, "a month with no swing is a month"
    assert season.clean_normals([[-90.1, 0]] + TOKYO[1:]) is None
    assert season.clean_normals([[0, 60.1]] + TOKYO[1:]) is None
    assert season.clean_normals([[-91, -90.5]] + TOKYO[1:]) is None
    assert season.clean_normals([[60.5, 61]] + TOKYO[1:]) is None


def test_mismatches_count_each_out_of_season_garment():
    d = _day(20, 24, JUL, TEE, SWEATER, JACKET, CHINOS, SHORTS)
    assert season.mismatches(d, {"base": TEE["id"], "mid": SWEATER["id"], "outer": JACKET["id"],
                                 "bottoms": CHINOS["id"]}) == 3
    assert season.mismatches(d, {"base": TEE["id"], "bottoms": SHORTS["id"]}) == 0


def test_the_last_resort_brings_summer_legs_back_when_the_warm_pair_cannot_be_worn(api, monkeypatch):
    # Codex's reproduction (pre-push gate, 2026-11-21): jeans are banned with the only
    # top, so the warm pair is owned but unwearable. The linen goes out, not nothing.
    jeans = g("jeans0001", "blue jeans", "bottoms", "jeans", ["bottoms"], 3, colors=["blue"])
    ban = [{"kind": "avoid_pair", "a": {"type": "jeans"}, "b": {"type": "t_shirt"}}]
    async def fetch(lat, lon, day):
        return weather(8, 12, date="2026-11-18")
    monkeypatch.setattr(srv.weather, "fetch_weather", fetch)
    fake_model.install(monkeypatch, [], choices=[fake_model.choice(1)] * 4)
    r = api.post("/advice", json={"lat": 1, "lon": 1, "occasion": "off", "gender": "man", "rules": ban,
                                  "closet": [TEE, SUMMER_TR, jeans, SNEAK]})
    assert r.status_code == 200, r.text
    assert r.json()["picks"]["bottoms"] == SUMMER_TR["id"]


def test_an_out_of_season_outfit_is_not_called_cold_to_the_chooser(api, monkeypatch):
    # A mild November day: the in-season trousers are banned with the only top, so the
    # shorts are the comfortable answer, out of season (tier 1). Tier 1 is not tier 2:
    # the chooser must not hear nothing is warm enough (pre-push gate, 2026-11-21).
    ban = [{"kind": "avoid_pair", "a": {"type": "trousers"}, "b": {"type": "t_shirt"}}]
    async def fetch(lat, lon, day):
        return weather(19, 24, date="2026-11-20")
    monkeypatch.setattr(srv.weather, "fetch_weather", fetch)
    seen = fake_model.install(monkeypatch, [], choices=[fake_model.choice(1)] * 4)
    r = api.post("/advice", json={"lat": 1, "lon": 1, "occasion": "off", "gender": "man", "normals": TOKYO,
                                  "rules": ban, "closet": [TEE, SHORTS, LIGHT_TR, SNEAK]})
    assert r.status_code == 200, r.text
    assert r.json()["picks"]["bottoms"] == SHORTS["id"]
    assert seen["chooser"], "the chooser was asked"
    assert not any("warm enough" in p for p in seen["chooser"]), "out of season is not cold"
    assert "another season" in r.json()["outfit_text"], "and the note says what it is"


def test_a_garment_the_actual_morning_needs_is_never_out_of_season_for_warmth():
    # A 2C morning in July: the coat and the knit are what today calls for.
    cold_july = season.Normal(2, 10)
    coat = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
    assert season.out_of_season(coat, "outer", JUL), "by the normal alone, out"
    assert not season.out_of_season(coat, "outer", JUL, cold_july)
    assert not season.out_of_season(SWEATER, "mid", JUL, cold_july)
    assert not season.out_of_season({**coat, "season": "cold"}, "outer", JUL, cold_july)
    assert season.out_of_season({**coat, "season": "cold"}, "outer", JUL, season.Normal(20, 28))


def test_a_warm_actual_day_does_not_bring_summer_legs_back_into_season():
    assert season.out_of_season(SHORTS, "bottoms", NOV, season.Normal(19, 24))


def test_a_cold_july_morning_keeps_the_knit_under_the_coat(api, monkeypatch):
    # Codex's reproduction (pre-push gate, 2026-11-21): 2-10C on July normals.
    coat = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
    closet = [TEE, SWEATER, coat, g("jeans0001", "blue jeans", "bottoms", "jeans", ["bottoms"], 3), SNEAK]
    wx = weather(2, 10, date="2026-07-15")
    plain = advise(api, monkeypatch, wx, closet)
    seasonal = advise(api, monkeypatch, wx, closet, TOKYO)
    assert SWEATER["id"] in plain["picks"].values(), "the knit goes under the coat below 5C"
    assert seasonal["picks"] == plain["picks"], "and the season changes nothing on a day like this"


def test_the_season_note_admits_a_search_that_ran_out_of_time():
    import relaxnotes
    assert "time ran out" in relaxnotes.SEASON_UNSURE and "another season" in relaxnotes.SEASON_UNSURE


def test_a_cold_months_garment_is_in_season_from_an_actual_morning_under_12c():
    coat = {**g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4), "season": "cold"}
    assert not season.out_of_season(coat, "outer", JUL, season.Normal(11.9, 20))
    assert season.out_of_season(coat, "outer", JUL, season.Normal(12.0, 20))


def test_a_warm_months_sweater_still_goes_under_the_coat_on_a_2c_morning(api, monkeypatch):
    # Codex's reproduction (pre-push gate, 2026-11-21): 2-10C on November normals, the
    # only sweater tagged warm months. Below the coat line the layers come first.
    coat = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
    sweater = {**SWEATER, "season": "warm"}
    closet = [TEE, sweater, coat, g("jeans0001", "blue jeans", "bottoms", "jeans", ["bottoms"], 3), SNEAK]
    wx = weather(2, 10, date="2026-11-20")
    plain = advise(api, monkeypatch, wx, closet)
    seasonal = advise(api, monkeypatch, wx, closet, TOKYO)
    assert SWEATER["id"] in plain["picks"].values()
    assert seasonal["picks"] == plain["picks"]


def test_on_a_coat_morning_the_trousers_still_follow_the_season(api, monkeypatch):
    # Codex's reproduction (pre-push gate, 2026-11-21): 2C; the warm-months trousers
    # sit at the day's level, the all-year pair a step off it. The layers decide
    # nothing here, so the season holds the warm-months pair aside for the band step.
    coat = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
    warm_tr = {**g("warmtr001", "light trousers", "bottoms", "trousers", ["bottoms"], 3), "season": "warm", "level": 2}
    smart_tr = {**g("smarttr01", "wool trousers", "bottoms", "trousers", ["bottoms"], 3, colors=["grey"]), "level": 4}
    closet = [TEE, SWEATER, coat, warm_tr, smart_tr, SNEAK]
    wx = weather(2, 10, date="2026-11-20")
    assert advise(api, monkeypatch, wx, closet)["picks"]["bottoms"] == warm_tr["id"], "without a season: the level"
    assert advise(api, monkeypatch, wx, closet, TOKYO)["picks"]["bottoms"] == smart_tr["id"]


def test_a_rule_given_up_outranks_the_knit_under_the_coat():
    """The layering the weather asks for is a soft preference: it never buys a broken
    pairing rule (pre-push gate, 2026-11-24: fit.layering had moved ahead of the
    relaxation cost)."""
    import funnel
    from test_funnel import CHINOS, LOAFERS, PARKA
    from wardrobe_fixtures import UNDER, day, g
    shirt = g("chkshirt1", "checked shirt", "tops", "shirt", ["base", "mid", "outer"], 2, pattern="checked")
    knit = g("strknit01", "striped sweater", "tops", "sweater", ["base", "mid", "outer"], 4, pattern="striped")
    d = day(3, UNDER, shirt, knit, PARKA, CHINOS, LOAFERS, hi=8)
    c = funnel.Ctx(d, funnel.target_level(d.look), frozenset({"colour"}))
    base = {"inner": UNDER["id"], "base": shirt["id"], "outer": PARKA["id"], "bottoms": CHINOS["id"],
            "footwear": LOAFERS["id"]}
    shapes = [(("base", "mid", "outer"), {**base, "mid": knit["id"]}), (("base", "outer"), base)]
    today = frozenset(base) | {"mid"}
    got = sorted(funnel._evaluate(c, shapes, funnel.priority_for(c), today), key=lambda o: o.rank)
    assert got and got[0].picks.get("mid") is None and got[0].relaxed == (), [(o.picks.get("mid"), o.rank) for o in got]


def test_the_rain_outranks_the_season():
    """Rainy 15-20C on a normal 9-17C day: leather loafers kept for warm months beat
    in-season mesh sneakers, which would give up the wet rule (pre-push gate,
    2026-11-24)."""
    from test_funnel import CHINOS, LOAFERS, MESH, prefs, run
    from wardrobe_fixtures import OXFORD, UNDER
    summer = {**LOAFERS, "season": "warm"}
    _, r = run(15, UNDER, OXFORD, CHINOS, MESH, summer, hi=20, rain=80, isRain=True,
               p=prefs(normal=season.Normal(9, 17)))
    o = r.outfits[0]
    assert o.picks["footwear"] == LOAFERS["id"] and "wet" not in o.relaxed, (o.picks, o.relaxed)
    _, r = run(15, UNDER, OXFORD, CHINOS, MESH, summer, hi=20, p=prefs(normal=season.Normal(9, 17)))
    assert r.outfits[0].picks["footwear"] == MESH["id"], "dry: the season decides"
