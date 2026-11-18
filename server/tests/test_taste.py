"""What I wore, and the days like today (user, 2026-11-14): "I want to keep a log of
what I wore with parameters which influence decision (occasion, weather, temperature)
so that suggestion naturally fits into my taste." PLAN.md, 2026-11-14."""
import datetime as dt
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app as srv
import engine
import funnel
import llm
import picks as pk
import style
import taste
from schemas import AdviceRequest
from wardrobe_fixtures import JEANS, OXFORD, SNEAK, TEE, day, g, weather

TODAY = "2026-10-11"          # wardrobe_fixtures.weather's date
COAT = g("coat00001", "navy wool coat", "outerwear", "coat", ["outer"], 4)
TEE_B = g("teeb00001", "grey crew-neck T-shirt", "tops", "t_shirt", ["base"], 1, colors=["grey"])


def ago(n: int) -> str:
    return (dt.date.fromisoformat(TODAY) - dt.timedelta(days=n)).isoformat()


def E(days_ago, occasion="off", temp=20.0, rain=0, chose=(), **picks):
    return {"day": ago(days_ago), "occasion": occasion, "temp": temp, "peak": temp + 4, "rain": rain, "wind": 2,
            "picks": {s: i["id"] for s, i in picks.items()}, "chose": list(chose), "at": 1}


def build(entries, closet, recent=None, occasion="off", temp=20.0, **w):
    return taste.build(taste.clean_worn(entries), closet, recent or {}, occasion, temp, weather(temp, **w))


def prefs(occasion="off", t=None, **kw):
    return replace(pk.Prefs(**kw), look=style.Look("casual", "man", occasion), taste=t)


def search(temp, *items, p, hi=None):
    d = day(temp, *items, hi=hi, prefs=p)
    return funnel.search(funnel.Ctx(d, funnel.target_level(d.look)))


# ── how much a past day is like today ─────────────────────────────────────────────

@pytest.mark.parametrize("occ,today,want", [("off", "off", 1.0), ("office", "off", 0.25), (None, "off", 0.5),
                                            ("off", None, 0.5)])
def test_occasion_weight(occ, today, want):
    assert taste.weight({"occasion": occ, "temp": 20.0, "rain": 0}, today, 20.0, False, 0) == want


@pytest.mark.parametrize("delta,want", [(0, 1.0), (3, 0.5), (5.9, 1 - 5.9 / 6), (6, 0.0), (7, 0.0), (-3, 0.5)])
def test_temperature_weight_both_sides_of_six_degrees(delta, want):
    got = taste.weight({"occasion": "off", "temp": 20.0 + delta, "rain": 0}, "off", 20.0, False, 0)
    assert got == pytest.approx(want)


def test_wet_and_recency_weight():
    e = {"occasion": "off", "temp": 20.0, "rain": 80}
    assert taste.weight(e, "off", 20.0, True, 0) == 1.0
    assert taste.weight(e, "off", 20.0, False, 0) == 0.5
    assert taste.weight({**e, "rain": 49}, "off", 20.0, False, 0) == 1.0, "49% is a dry day"
    assert taste.weight({**e, "rain": 50}, "off", 20.0, True, 0) == 1.0, "50% is a wet one"
    assert taste.weight({**e, "rain": 0}, "off", 20.0, False, 60) == pytest.approx(0.5)


# ── the log, as it arrives: dropped, never refused ────────────────────────────────

def test_clean_worn_drops_each_malformed_entry_and_keeps_the_rest():
    good = E(1, base=TEE)
    bad = [
        "not a dict", {**good, "day": "2026-13-01"}, {**good, "day": "yesterday"}, {**good, "temp": True},
        {**good, "temp": 61}, {**good, "temp": -91}, {**good, "temp": "20"}, {**good, "picks": "x"},
        {**good, "picks": {"base": "short"}}, {**good, "picks": {"hat": TEE["id"]}},
        {**good, "picks": {"base": TEE["id"], "mid": TEE["id"]}},     # one garment in two slots
        {**good, "temp": float("nan")},
    ]
    assert taste.clean_worn(bad + [good]) == [taste._entry(good)]
    assert taste.clean_worn("nope") == [] and taste.clean_worn(None) == []


def test_clean_worn_keeps_an_entry_with_no_occasion_and_trims_bad_fields():
    e = taste.clean_worn([{**E(1, base=TEE, mid=OXFORD), "occasion": "", "rain": True, "chose": ["mid", "x"],
                           "picks": {"base": TEE["id"], "mid": OXFORD["id"], "accessories": SNEAK["id"]}}])
    assert e == [{"day": ago(1), "occasion": None, "temp": 20.0, "rain": 0.0,
                  "picks": {"base": TEE["id"], "mid": OXFORD["id"]}, "chose": ["mid"]}]


def test_unhashable_choices_are_dropped_not_raised():
    """Pre-push gate, 2026-11-16: `[{}] in worn` raised TypeError and cost /advice."""
    for bad in ([{}], [[]], [None, 3, "base"]):
        got = taste.clean_worn([{**E(1, base=TEE), "chose": bad}])
        assert len(got) == 1 and got[0]["chose"] == (["base"] if "base" in bad else [])
    assert len(AdviceRequest(lat=1, lon=1, worn=[{**E(1, base=TEE), "chose": [{}]}]).worn) == 1


def test_the_last_entry_of_a_day_wins_whatever_its_timestamp():
    first, last = {**E(1, base=TEE), "at": 99999999999999}, {**E(1, base=TEE_B), "at": 1}
    assert [e["picks"]["base"] for e in taste.clean_worn([first, last])] == [TEE_B["id"]]


def test_only_the_last_90_entries_are_read():
    log = [E(n % 100, base=TEE) for n in range(91)]
    assert len(log[-90:]) == 90 and taste.clean_worn(log) == taste.clean_worn(log[-90:])


def test_a_malformed_log_never_costs_the_request():
    r = AdviceRequest(lat=1, lon=1, worn=[{"day": 3}, "x", E(1, base=TEE)])
    assert len(r.worn) == 1
    assert AdviceRequest(lat=1, lon=1, worn="garbage").worn == []


# ── a request's taste ──────────────────────────────────────────────────────────────

def test_no_log_is_no_taste():
    t = build([], [TEE, JEANS])
    assert t.confidence == 0 and t.bonus(TEE["id"], "base") == 0 and t.pair({"base": TEE["id"]}) == 0


def test_tomorrow_ages_the_log_from_tomorrow():
    tomorrow = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=1)).isoformat()
    e = {**E(0, base=TEE), "day": tomorrow}
    assert build([e], [TEE]).days == 0, "after today's forecast: in the future"
    t = taste.build(taste.clean_worn([e]), [TEE], {}, "off", 20.0, weather(20, date=tomorrow))
    assert t.days == 1, "tomorrow's forecast: today, age 0"


def test_the_log_is_aged_against_the_forecast_date_not_this_server():
    assert build([E(120, base=TEE)], [TEE]).days == 1
    assert build([E(121, base=TEE)], [TEE]).days == 0, "older than 120 days"


def test_garments_since_removed_add_nothing_not_even_confidence():
    gone = g("gone00001", "old tee", "tops", "t_shirt", ["base"], 1)
    t = build([E(1, base=gone), E(2, base=gone), E(3, base=gone)], [TEE])
    assert t.confidence == 0 and t.days == 0


def test_confidence_grows_with_similar_days():
    assert build([E(0, base=TEE)], [TEE]).confidence == pytest.approx(1 / 3)
    assert build([E(0, base=TEE)] * 1 + [E(n, base=TEE) for n in range(5)], [TEE]).confidence == 1.0


def test_their_own_pick_counts_more_than_accepting_ours():
    t = build([E(0, base=TEE), E(0, base=TEE_B, chose=["base"])][1:] + [E(1, base=TEE)], [TEE, TEE_B])
    # TEE_B: weight(0) × 1.5; TEE: weight(1 day) × 1 — the chosen one is the slot's best.
    assert t.items[(TEE_B["id"], "base")] == 1.0 and t.items[(TEE["id"], "base")] < 0.67


def test_much_worn_trousers_do_not_mute_the_tops():
    t = build([E(n, base=TEE, bottoms=JEANS) for n in range(5)] + [E(n, bottoms=JEANS) for n in range(5, 20)],
              [TEE, JEANS])
    assert t.items[(TEE["id"], "base")] == 1.0, "normalised within its own slot"


def test_nothing_is_added_to_a_garment_worn_today_or_yesterday():
    log = [E(n, base=TEE, bottoms=JEANS, outer=COAT) for n in range(2, 8)]
    for n, mult in ((0, 0.0), (1, 0.0), (2, 1 / 3), (4, 1.0), (9, 1.0)):
        t = build(log, [TEE, JEANS, COAT], recent={TEE["id"]: n})
        assert t.bonus(TEE["id"], "base") == pytest.approx(3.0 * mult), n
    t = build(log, [TEE, JEANS, COAT], recent={TEE["id"]: 1, COAT["id"]: 0})
    assert t.pair({"base": TEE["id"], "bottoms": JEANS["id"]}) == 0, "a just-worn garment's pairs neither"
    assert t.potential(TEE["id"], "base") == 0
    assert t.bonus(COAT["id"], "outer") == 3.0, "a coat is worn day after day: rotation never moves it"
    assert t.pair({"outer": COAT["id"], "bottoms": JEANS["id"]}) > 0, "and its pairs stay"


def test_the_same_request_builds_the_same_taste():
    log = [E(n, base=TEE, bottoms=JEANS) for n in range(4)]
    a, b = build(log, [TEE, JEANS]), build(log, [TEE, JEANS])
    assert (a.items, a.pairs_, a.confidence) == (b.items, b.pairs_, b.confidence)


def test_taste_stays_out_of_what_they_said():
    t = build([E(0, base=TEE)], [TEE])
    assert pk.Prefs(taste=t) == pk.Prefs() and hash(pk.Prefs(taste=t)) == hash(pk.Prefs())


# ── the funnel ─────────────────────────────────────────────────────────────────────

def test_of_two_equal_tops_the_one_worn_on_days_like_today_is_served():
    closet = [TEE, TEE_B, JEANS, SNEAK]
    plain = search(20, *closet, p=prefs(), hi=24).outfits[0].picks["base"]
    other = TEE_B if plain == TEE["id"] else TEE
    t = build([E(n, base=other, bottoms=JEANS, footwear=SNEAK) for n in range(1, 6)], closet)
    r = search(20, *closet, p=prefs(t=t), hi=24)
    assert all(o.picks["base"] == other["id"] for o in r.outfits), "only outfits like theirs are offered"


def test_a_different_kind_of_day_counts_less_and_a_far_temperature_not_at_all():
    closet = [TEE, TEE_B, JEANS, SNEAK]
    log = [E(n, occasion="office", base=TEE_B, bottoms=JEANS) for n in range(1, 6)]
    assert build(log, closet).confidence < build([{**e, "occasion": "off"} for e in log], closet).confidence
    t = build([E(n, temp=29, base=TEE_B) for n in range(1, 6)], closet)
    assert t.confidence == 0
    assert search(20, *closet, p=prefs(t=t), hi=24).outfits[0].picks == \
        search(20, *closet, p=prefs(), hi=24).outfits[0].picks


def test_taste_never_brings_back_what_was_worn_yesterday():
    a, b = {**TEE, "_ago": 1}, {**TEE_B, "_ago": 6}
    log = [E(n, base=TEE, bottoms=JEANS, footwear=SNEAK, chose=["base"]) for n in range(2, 12)]
    t = build(log, [a, b, JEANS, SNEAK], recent={TEE["id"]: 1, TEE_B["id"]: 6})
    p = prefs(t=t, prefers=({"slot": "base", "id": TEE["id"], "label": "tee", "n": 9},))
    assert search(20, a, b, JEANS, SNEAK, p=p, hi=24).outfits[0].picks["base"] == TEE_B["id"]


def test_taste_never_puts_a_shirt_on_a_day_off():
    closet = [TEE, OXFORD, JEANS, SNEAK]
    t = build([E(n, base=OXFORD, bottoms=JEANS, chose=["base"]) for n in range(1, 30)], closet)
    for o in search(20, *closet, p=prefs(t=t), hi=24).outfits:
        assert o.picks["base"] == TEE["id"], "the day-off cap ranks first"


def test_taste_never_breaks_their_rule():
    closet = [TEE, TEE_B, JEANS, SNEAK]
    ban = {"kind": "avoid_item", "a": {"color": "grey", "type": "t_shirt"}, "text": "no grey tees"}
    t = build([E(n, base=TEE_B, bottoms=JEANS) for n in range(1, 30)], closet)
    for o in search(20, *closet, p=prefs(t=t, rules=(ban,)), hi=24).outfits:
        assert o.picks["base"] == TEE["id"]


TEES = [g(f"tee{c}000000", f"{c} crew-neck T-shirt", "tops", "t_shirt", ["base"], 1, colors=["white"])
        for c in "abcdefghijk"]
JEANSES = [g(f"jns{c}000000", f"{c} jeans", "bottoms", "jeans", ["bottoms"], 3, colors=["blue"])
           for c in "abcdefghi"]
SHOES = [g(f"snk{c}000000", f"{c} sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["white"])
         for c in "abcd"]
# Last by id, so past the first pass's six-a-slot cut whenever priorities tie.
FAV_TEE = g("zzfavtee01", "favourite tee", "tops", "t_shirt", ["base"], 1, colors=["white"])
FAV_JEANS = g("zzfavjns01", "favourite jeans", "bottoms", "jeans", ["bottoms"], 3, colors=["blue"])
BIG = TEES + JEANSES + SHOES + [FAV_TEE, FAV_JEANS]


def big_log():
    """Every garment worn alone on two days, but the favourites only TOGETHER: each
    garment's own score is the same, and only the pair stands out."""
    log, n = [], 0
    for i in TEES + JEANSES + SHOES:
        slot = i["roles"][0]
        log += [E(n, **{slot: i}), E(n + 1, **{slot: i})]
        n += 2
    return log + [E(n, base=FAV_TEE, bottoms=FAV_JEANS), E(n + 1, base=FAV_TEE, bottoms=FAV_JEANS)]


def test_without_the_log_the_favourite_pair_is_cut_before_the_search():
    """The control: this closet really does cut the favourites, or the next test
    proves nothing."""
    r = search(22, *BIG, p=prefs(), hi=26)
    assert all(o.picks["base"] != FAV_TEE["id"] for o in r.outfits)


def test_a_favourite_pair_survives_hundreds_of_equal_combinations(monkeypatch):
    monkeypatch.setattr(taste, "weight", lambda *a: 1.0)      # every day equally like today
    t = build(big_log(), BIG)
    assert {t.items[(i["id"], "base")] for i in TEES + [FAV_TEE]} == {1.0}, "no garment favoured alone"
    r = search(22, *BIG, p=prefs(t=t), hi=26)
    assert (r.outfits[0].picks["base"], r.outfits[0].picks["bottoms"]) == (FAV_TEE["id"], FAV_JEANS["id"])


def test_potential_guides_the_search_but_never_scores_an_outfit(monkeypatch):
    monkeypatch.setattr(taste, "weight", lambda *a: 1.0)
    t = build(big_log(), BIG)
    assert t.potential(FAV_TEE["id"], "base") > 0
    d0, d1 = day(22, *BIG, hi=26, prefs=prefs()), day(22, *BIG, hi=26, prefs=prefs(t=t))
    picks = {"base": FAV_TEE["id"], "bottoms": JEANSES[0]["id"], "footwear": SHOES[0]["id"]}
    c0, c1 = funnel.Ctx(d0, 2), funnel.Ctx(d1, 2)
    s0 = funnel._score(c0, picks, funnel.priority_for(c0), ())
    s1 = funnel._score(c1, picks, funnel.priority_for(c1), ())
    bonus = sum(t.bonus(picks[s], s) for s in picks) / len(picks)
    assert t.pair(picks) == 0, "its partner is not in this outfit"
    assert s1 - s0 == pytest.approx(bonus), "the item bonus only: no potential in a finished outfit"


def test_the_chooser_is_offered_only_outfits_close_to_their_taste():
    class Out:
        def __init__(self, base):
            self.picks = {"base": base["id"], "bottoms": JEANS["id"]}
    t = build([E(n, base=TEE, bottoms=JEANS) for n in range(1, 6)], [TEE, TEE_B, JEANS])
    tier = [Out(TEE_B), Out(TEE)]
    assert [o.picks["base"] for o in t.within(tier)] == [TEE["id"]]
    weak = build([E(1, base=TEE)], [TEE, TEE_B, JEANS])
    assert weak.confidence < taste.CONFIDENT and weak.within(tier) == tier, "too few days: unchanged"


# ── the phone's numbers ────────────────────────────────────────────────────────────

def test_raw_temperatures_come_from_the_forecast_never_by_subtracting_the_offset():
    w = weather(10, 14, morning=10, feelsLo=10)
    shifted = engine.apply_temp_offset(w, 0.5)
    raw = taste.raw_temps(w)
    assert raw["rawPlanTemp"] == round(llm._plan_temp(w), 1)
    assert round(llm._plan_temp(shifted), 1) - 0.5 != raw["rawPlanTemp"], "the offset is added, then rounded"


def test_advice_returns_the_raw_temperatures_and_takes_a_log(monkeypatch):
    async def mild(lat, lon, day):
        return weather(20, 24)
    monkeypatch.setattr(srv.weather, "fetch_weather", mild)
    api = TestClient(srv.app)
    r = api.post("/advice", json={"lat": 1, "lon": 1, "tempOffset": 0.5, "occasion": "off",
                                  "worn": [E(1, base=TEE), {"bad": 1}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rawPlanTemp"] == round(llm._plan_temp(weather(20, 24)), 1) and "rawPeakTemp" in d


def _first_pass_candidates(t):
    d = day(22, *BIG, hi=26, prefs=prefs(t=t))
    ctx = funnel.Ctx(d, funnel.target_level(d.look))
    cands, _ = funnel.candidates(ctx, funnel.priority_for(ctx))
    return cands


def test_potential_alone_puts_a_favourite_pair_s_members_first(monkeypatch):
    monkeypatch.setattr(taste, "weight", lambda *a: 1.0)
    t = build(big_log(), BIG)
    monkeypatch.setattr(taste.Taste, "strong_pairs", lambda self: [])
    cands = _first_pass_candidates(t)
    assert cands["base"][0] == FAV_TEE["id"] and cands["bottoms"][0] == FAV_JEANS["id"]


def test_the_strong_pair_alone_gets_its_members_past_the_cut(monkeypatch):
    monkeypatch.setattr(taste, "weight", lambda *a: 1.0)
    t = build(big_log(), BIG)
    assert _first_pass_candidates(build([], BIG))["base"].count(FAV_TEE["id"]) == 0, "the cut drops it"
    monkeypatch.setattr(taste.Taste, "potential", lambda self, i, s: 0.0)
    cands = _first_pass_candidates(t)
    assert FAV_TEE["id"] in cands["base"] and FAV_JEANS["id"] in cands["bottoms"]
