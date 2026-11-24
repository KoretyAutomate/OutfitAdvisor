"""The accessories, one slot per body area (user, 2026-11-24: "Accessories needs to be
split. Belt and scarf can go together"). accessories.py; vocab.ACCESSORY_SLOTS."""
import accessories
import funnel
import garment
import gaps
import rules
import schemas
import vocab
from test_funnel import CHINOS, LOAFERS, PARKA, prefs, run
from wardrobe_fixtures import JEANS, OXFORD, SHORTS, SNEAK, SWEATER, UNDER, day, g, weather

BELT = g("abelt0001", "brown leather belt", "accessories", "belt", ["belt"], 1, colors=["brown"])
BLACK_BELT = g("akbelt001", "black leather belt", "accessories", "belt", ["belt"], 1, colors=["black"])
SCARF = g("ascarf001", "grey wool scarf", "accessories", "scarf", ["neck"], 4, colors=["grey"])
GLOVES = g("agloves01", "leather gloves", "accessories", "gloves", ["hands"], 4, colors=["brown"])
BEANIE = g("abeanie01", "wool beanie", "accessories", "hat", ["head"], 4, colors=["grey"])
CAP = g("acap00001", "baseball cap", "accessories", "hat", ["head"], 1, colors=["navy"])
UMBRELLA = g("aumbrel01", "black umbrella", "accessories", "umbrella", ["umbrella"], 1, colors=["black"])
TIE = g("atie00001", "navy tie", "accessories", "tie", ["neck"], 1)
CLOTHES = [UNDER, OXFORD, SWEATER, PARKA, CHINOS, LOAFERS]
ALL = [BELT, SCARF, GLOVES, BEANIE, UMBRELLA]


def best(t, *items, **w):
    d, r = run(t, *items, **w)
    assert r.outfits, "something survives"
    return d, r.outfits[0].picks


# ── the user's case ──────────────────────────────────────────────────────────────

def test_belt_and_scarf_go_together():
    _, p = best(3, *CLOTHES, BELT, SCARF, hi=8)
    assert p["belt"] == BELT["id"] and p["neck"] == SCARF["id"], p


def test_a_cold_wet_morning_in_trousers_wears_all_five():
    _, p = best(2, *CLOTHES, *ALL, hi=6, rain=70, isRain=True)
    assert {s: p[s] for s in vocab.ACCESSORY_SLOTS} == {
        "belt": BELT["id"], "neck": SCARF["id"], "head": BEANIE["id"], "hands": GLOVES["id"],
        "umbrella": UMBRELLA["id"]}, p


def test_the_accessories_never_change_the_clothes():
    _, bare = best(2, *CLOTHES, hi=6, rain=70, isRain=True)
    _, dressed = best(2, *CLOTHES, *ALL, BLACK_BELT, hi=6, rain=70, isRain=True)
    assert {s: dressed[s] for s in vocab.CATEGORIES if s not in vocab.ACCESSORY_SLOTS} == \
        {s: bare[s] for s in vocab.CATEGORIES if s not in vocab.ACCESSORY_SLOTS}


# ── each reason, both sides of its line ────────────────────────────────────────────

def test_a_belt_only_with_trousers_or_jeans():
    _, p = best(14, UNDER, OXFORD, CHINOS, SNEAK, BELT, hi=20)
    assert p["belt"] == BELT["id"]
    _, p = best(14, UNDER, OXFORD, JEANS, SNEAK, BELT, hi=20)
    assert p["belt"] == BELT["id"]
    _, p = best(24, UNDER, OXFORD, SHORTS, SNEAK, BELT, hi=30)
    assert p["belt"] is None, "no belt with shorts"


def test_the_belt_matches_the_shoes():
    _, p = best(14, UNDER, OXFORD, CHINOS, LOAFERS, BLACK_BELT, hi=20)
    assert p["belt"] is None, "a black belt with brown loafers stays home"
    _, p = best(14, UNDER, OXFORD, CHINOS, LOAFERS, BLACK_BELT, BELT, hi=20)
    assert p["belt"] == BELT["id"], "the brown one goes instead"


def test_a_scarf_below_the_coat_line_only():
    d = day(layers_line() - 0.1, *CLOTHES, SCARF)
    assert accessories.reason("neck", SCARF, d, {})
    d = day(layers_line(), *CLOTHES, SCARF)
    assert not accessories.reason("neck", SCARF, d, {})
    _, p = best(12, *CLOTHES, SCARF, hi=18)
    assert p["neck"] is None, "no scarf on a mild day"


def layers_line():
    import layers
    return layers.COAT_BELOW_C


def test_hat_and_gloves_below_five_only():
    for t, want in ((accessories.COLD_HANDS_C - 0.1, True), (accessories.COLD_HANDS_C, False)):
        d = day(t, *CLOTHES, GLOVES, BEANIE)
        assert accessories.reason("hands", GLOVES, d, {}) is want
        assert accessories.reason("head", BEANIE, d, {}) is want
    _, p = best(7, *CLOTHES, GLOVES, BEANIE, SCARF, hi=10)
    assert p["hands"] is None and p["head"] is None and p["neck"] == SCARF["id"], p


def test_a_cap_is_no_cold_weather_hat():
    _, p = best(1, *CLOTHES, CAP, hi=4)
    assert p["head"] is None


def test_an_umbrella_on_a_wet_day_only():
    for rain, want in ((garment.WET_RAIN_PCT, True), (garment.WET_RAIN_PCT - 1, False)):
        assert accessories.reason("umbrella", UMBRELLA, day(14, UMBRELLA, rain=rain), {}) is want
    assert accessories.reason("umbrella", UMBRELLA, day(14, UMBRELLA, rain=0, isRain=True), {})
    _, p = best(14, UNDER, OXFORD, CHINOS, SNEAK, UMBRELLA, hi=20)
    assert p["umbrella"] is None


def test_a_tie_is_still_never_chosen():
    _, p = best(3, *CLOTHES, TIE, hi=8, p=prefs("office", "smart"))
    assert p["neck"] is None


def test_an_accessory_worn_without_a_reason_costs():
    d = day(20, UNDER, OXFORD, SHORTS, SNEAK, BELT, SCARF)
    assert accessories.score(d, {"bottoms": SHORTS["id"], "belt": BELT["id"], "neck": SCARF["id"]}) == -2.0
    d = day(3, UNDER, OXFORD, CHINOS, SNEAK, BELT, SCARF)
    assert accessories.score(d, {"bottoms": CHINOS["id"], "belt": BELT["id"], "neck": SCARF["id"]}) == 1.0


def test_the_look_is_the_clothes():
    assert funnel.look({"base": "a", "belt": "b", "neck": "c"}) == frozenset({"a"})


# ── gaps: an accessory slot only when the day calls for it ────────────────────────

def test_no_umbrella_is_a_gap_only_on_a_wet_day():
    dry = day(14, UNDER, OXFORD, CHINOS, SNEAK)
    picks = {"inner": UNDER["id"], "base": OXFORD["id"], "bottoms": CHINOS["id"], "footwear": SNEAK["id"]}
    assert "umbrella" not in gaps.missing(picks, dry, ["umbrella"])
    wet = day(14, UNDER, OXFORD, CHINOS, SNEAK, rain=80, isRain=True)
    assert "umbrella" in gaps.missing(picks, wet, ["umbrella"])


# ── what older phones send ───────────────────────────────────────────────────────

def test_an_old_accessory_is_filed_by_its_type():
    for typ, slot in (("belt", "belt"), ("scarf", "neck"), ("tie", "neck"), ("hat", "head"),
                      ("gloves", "hands"), ("umbrella", "umbrella"), (None, "neck")):
        it = schemas.ClosetItem(id="old-item-1", label="x", category="accessories", group="accessories",
                                type=typ, roles=["accessories"])
        assert (it.category, it.roles) == (slot, [slot]), typ


def test_an_old_accessory_rule_still_bans_the_accessory_and_nothing_else():
    r = rules.clean_rule({"kind": "avoid_item", "a": {"role": "accessories", "color": "red"}})
    assert r["a"] == {"group": "accessories", "color": "red"}
    by = {"b": {**BELT, "id": "b", "colors": ["red"]}, "t": {**OXFORD, "id": "t", "colors": ["red"]}}
    assert [v["slot"] for v in rules.violations([r], {"belt": "b", "base": "t"}, by)] == ["belt"]


def test_an_old_rule_naming_no_accessory_stays_inert():
    r = rules.clean_rule({"kind": "avoid_item", "a": {"role": "accessories", "group": "tops"}})
    assert r["a"]["role"] == "accessories"
    by = {"t": {**OXFORD, "id": "t"}}
    assert not rules.violations([r], {"base": "t"}, by)


def test_an_old_pair_of_two_accessories_stays_dead():
    pair = {"kind": "avoid_pair", "a": {"role": "accessories"}, "b": {"role": "accessories"}}
    assert rules.clean_rule(pair) is None


def test_an_old_accessories_gap_is_dropped_from_shopping():
    req = schemas.ShoppingRequest(gaps=[{"slot": "accessories", "n": 3}, {"slot": "umbrella", "n": 2}])
    assert [x.slot for x in req.gaps] == ["umbrella"]


def test_the_five_fold_into_one_line_for_an_older_card():
    o = {"belt": "brown belt", "neck": "grey scarf", "head": "None needed", "hands": "None needed",
         "umbrella": "None needed", "accessories": "scarf"}
    vocab.fold_accessories(o)
    assert o["accessories"] == "brown belt, grey scarf"
    o = {s: "None needed" for s in vocab.ACCESSORY_SLOTS}
    vocab.fold_accessories(o)
    assert o["accessories"] == "None needed"
    o = {s: "None — the advisor couldn't answer just now" for s in vocab.ACCESSORY_SLOTS}
    vocab.fold_accessories(o)
    assert o["accessories"] == "None — the advisor couldn't answer just now"
    generic = {"accessories": "hat, gloves & scarf"}
    vocab.fold_accessories(generic, {})
    assert generic == {"accessories": "hat, gloves & scarf"}
    picks = {"belt": None, "neck": "s1", "hands": "g1"}
    vocab.fold_accessories({s: "x" for s in vocab.ACCESSORY_SLOTS}, picks)
    assert picks["accessories"] == "s1"
    none = {"belt": None}
    vocab.fold_accessories({s: "None needed" for s in vocab.ACCESSORY_SLOTS}, none)
    assert "accessories" not in none


def test_advice_end_to_end_from_an_old_phone(monkeypatch):
    """/advice with a closet as v1.61 saved it: every accessory category and role
    "accessories". The belt and the scarf both come back, and the old card's one line
    names both."""
    from fastapi.testclient import TestClient

    import app as srv
    import fake_model

    async def cold(lat, lon, day_):
        return weather(3, 8)
    monkeypatch.setattr(srv.weather, "fetch_weather", cold)
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    fake_model.install(monkeypatch, [], choices=[None])
    old = [{**i, "category": "accessories", "roles": ["accessories"]} for i in (BELT, SCARF)]
    closet = [{k: v for k, v in i.items() if k != "availableCount"} for i in (*CLOTHES, *old)]
    r = TestClient(srv.app).post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["picks"]["belt"] == BELT["id"] and body["picks"]["neck"] == SCARF["id"], body["picks"]
    assert body["outfit"]["accessories"] == f"{BELT['label']}, {SCARF['label']}", body["outfit"]
    assert body["picks"]["accessories"] == BELT["id"], "the old card's closet-only view and photo read it"


def test_the_warm_hat_line_both_sides():
    d = day(1, BEANIE)
    assert accessories.reason("head", {**BEANIE, "warmth": accessories.WARM_HAT}, d, {})
    assert not accessories.reason("head", {**BEANIE, "warmth": accessories.WARM_HAT - 1}, d, {})


def test_an_unknown_accessory_id_scores_nothing():
    d = day(3, UNDER, OXFORD, CHINOS, SNEAK, BELT)
    assert accessories.score(d, {"bottoms": CHINOS["id"], "belt": BELT["id"], "neck": "gone-0001"}) == 0.5


def test_accessories_already_chosen_are_kept():
    d, _ = run(3, *CLOTHES, BELT, SCARF, hi=8)
    ctx = funnel.Ctx(d, funnel.target_level(d.look))
    mine = {"bottoms": CHINOS["id"], "footwear": LOAFERS["id"], "neck": SCARF["id"]}
    out = accessories.dress(ctx, mine, lambda i, s: 0.0)
    assert out == mine, "a model's or a re-roll's own accessory is not re-dressed"


def test_a_relaxed_day_never_brings_in_an_avoidable_belt_mismatch():
    """Drawstring trousers on an office day need a later step of the ladder, which
    also relaxes the belt rule; a black belt beside brown loafers is still left home
    (pre-push gate, 2026-11-24)."""
    from test_funnel import DRAWSTR, MERINO, RAINJKT, WHITE_OX
    from test_funnel import prefs as office_prefs
    d, r = run(10, UNDER, WHITE_OX, MERINO, RAINJKT, DRAWSTR, LOAFERS, BLACK_BELT, hi=19, p=office_prefs("office"))
    o = r.outfits[0]
    assert o.picks["bottoms"] == DRAWSTR["id"] and o.relaxed, o
    assert o.picks["belt"] is None and "belt" not in o.relaxed, (o.picks, o.relaxed)


def test_an_out_of_season_accessory_is_left_home():
    """A belt they keep for summer is not worn on a mild winter day: it would make the
    outfit out of season for nothing (pre-push gate, 2026-11-24)."""
    import season
    summer = {**BELT, "season": "warm"}
    _, p = best(14, UNDER, OXFORD, CHINOS, SNEAK, summer, hi=20, p=prefs(normal=season.Normal(1, 10)))
    assert p["belt"] is None
    _, p = best(14, UNDER, OXFORD, CHINOS, SNEAK, summer, hi=20, p=prefs(normal=season.Normal(20, 28)))
    assert p["belt"] == BELT["id"]


def test_no_wardrobe_outlives_its_request():
    """The accessory candidates are cached on the request's Day, never in the module
    (README: the server stores nothing; pre-push gate, 2026-11-24)."""
    assert not hasattr(accessories, "_CANDS")
    d, _ = run(3, *CLOTHES, BELT, SCARF, hi=8)
    assert "accessories.candidates" in d.memo
