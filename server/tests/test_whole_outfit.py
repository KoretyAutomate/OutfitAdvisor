"""The whole outfit, not only its pairs (user, 2026-10-24; v1.57).

2026-10-23 15:09, under v1.56 and breaking no rule: a white long-sleeve crewneck, a
light blue knit polo, a grey waffle-knit cardigan, an olive hooded parka, dark grey
trousers, grey mesh sneakers and a red leather belt, at 5-12C felt. User: "Do you
think any fashion advisor would allow Knit on knit combination?" 2026-10-24 08:07: a
navy patterned button-up shirt under a grey marl sweater — "Pattern shirt x kind of
patterned knit looks off to me". Fixes agreed: the layers fit the day ("Coat over the
top"), no undershirt under a T-shirt ("No undershirt rule is for T-shirt and not
shirts"), the coat and the belt in the register, no knit on knit, a textured knit
counts as the pattern, and the chooser may turn every outfit down.
"""
import check
import chooser
import fake_model
import funnel
import garment
import pairing
from test_funnel import CHINOS, assert_valid, dress, prefs, run, strict
from wardrobe_fixtures import JEANS, SNEAK, TEE, g, weather

INNER = g("innerls01", "white long-sleeve crewneck", "underwear", "thermal", ["inner"], 2, colors=["white"])
LB_POLO = g("lbpolo001", "Light blue long-sleeve polo", "tops", "polo", ["base", "mid", "outer"], 2,
            colors=["light blue"])
WAFFLE = g("waffle001", "grey waffle-knit cardigan", "tops", "cardigan", ["mid", "outer"], 3, colors=["grey"])
PARKA = g("hparka001", "olive hooded parka", "outerwear", "coat", ["outer"], 4, colors=["olive"])
TROUSERS = g("dgtrous01", "dark grey trousers", "bottoms", "trousers", ["bottoms"], 3, colors=["dark grey"])
MESH_SNK = g("greysnk01", "grey sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["grey"],
             material="mesh")
RED_BELT = g("redbelt01", "Red leather belt", "accessories", "belt", ["accessories"], 1, colors=["red"])
PRINT_SHIRT = g("prshirt01", "navy patterned button-up shirt", "tops", "shirt", ["base", "mid", "outer"], 2)
MARL = g("marlswt01", "grey marl crew-neck sweater", "tops", "sweater", ["base", "mid", "outer"], 4,
         colors=["grey"], pattern="solid")
PLAIN_SWT = g("plainswt1", "navy crew-neck sweater", "tops", "sweater", ["base", "mid", "outer"], 4)
WHITE_SHIRT = g("whshirt01", "white button-up shirt", "tops", "shirt", ["base", "mid", "outer"], 2,
                colors=["white"])


def _picks(**slots):
    return {s: i["id"] for s, i in slots.items()}


# ── 2026-10-23 15:09, replayed ────────────────────────────────────────────────────

def test_2026_10_23_1509_no_knit_polo_under_a_cardigan_and_no_knit_under_the_coat():
    d, r = run(5, INNER, LB_POLO, WAFFLE, PARKA, TROUSERS, MESH_SNK, RED_BELT, hi=12)
    assert_valid(d, r)
    for o in r.outfits:
        assert not (o.picks["base"] == LB_POLO["id"] and o.picks["mid"] == WAFFLE["id"]), o.picks
        # The parka is warm enough over the polo by itself at 5C: no knit between.
        assert o.picks["mid"] is None and o.picks["outer"] == PARKA["id"], o.picks
        assert o.picks["accessories"] != RED_BELT["id"], "a red belt with grey mesh sneakers"
        assert o.relaxed == ()


def test_knit_on_knit_is_a_texture_clash_and_a_turtleneck_under_a_cardigan_is_not():
    turtle = g("turtle001", "black merino turtleneck", "tops", "sweater", ["base", "mid"], 3, colors=["black"])
    ctx = strict(9, LB_POLO, WAFFLE, PLAIN_SWT, turtle, JEANS, SNEAK, hi=15)
    assert funnel.clash(ctx, _picks(base=LB_POLO, mid=WAFFLE)) == "texture"
    assert funnel.clash(ctx, _picks(base=PLAIN_SWT, mid=WAFFLE)) == "texture"
    assert funnel.clash(ctx, _picks(base=LB_POLO, outer=PLAIN_SWT)) == "texture"
    assert funnel.clash(ctx, _picks(base=turtle, mid=WAFFLE)) is None
    assert funnel.clash(ctx, _picks(base=turtle, mid=PLAIN_SWT)) is not None, "a cardigan only"


# ── 2026-10-24 08:07, replayed ────────────────────────────────────────────────────

def test_2026_10_24_0807_a_print_shirt_never_goes_under_a_marl_sweater():
    d, r = run(-1, INNER, PRINT_SHIRT, WHITE_SHIRT, MARL, PLAIN_SWT, PARKA, TROUSERS, MESH_SNK, hi=13)
    assert_valid(d, r)
    for o in r.outfits:
        assert {o.picks["base"], o.picks["mid"]} != {PRINT_SHIRT["id"], MARL["id"]}, o.picks
        # Below 5C felt: knit AND coat, as on 2026-10-18.
        assert o.picks["mid"] and o.picks["outer"] == PARKA["id"], o.picks
    ctx = strict(-1, PRINT_SHIRT, MARL, hi=13)
    assert funnel.clash(ctx, _picks(base=PRINT_SHIRT, mid=MARL)) == "colour"


def test_a_textured_knit_and_a_patterned_name_are_read():
    assert garment.textured(MARL) and garment.textured(WAFFLE) and not garment.textured(PLAIN_SWT)
    assert not garment.textured({**TEE, "label": "heather grey tee"}), "knitwear only"
    import style
    assert style.pattern_of(PRINT_SHIRT) == "print"


# ── the layers fit the day ────────────────────────────────────────────────────────

def test_a_light_coat_on_a_cold_morning_still_gets_the_knit():
    light = {**PARKA, "warmth": 3}
    d, r = run(6, INNER, LB_POLO, PLAIN_SWT, light, TROUSERS, MESH_SNK, hi=12)
    assert_valid(d, r)
    assert r.outfits[0].picks["mid"] == PLAIN_SWT["id"] and r.outfits[0].picks["outer"] == light["id"]


def test_below_five_it_is_knit_and_coat_whatever_the_coat():
    warm = {**PARKA, "warmth": 5}
    d, r = run(3, INNER, WHITE_SHIRT, PLAIN_SWT, warm, TROUSERS, MESH_SNK, hi=10)
    assert_valid(d, r)
    assert r.outfits[0].picks["mid"] == PLAIN_SWT["id"]


def test_a_mild_day_wears_a_knit_or_a_jacket_not_both():
    jacket = g("ljacket01", "navy light jacket", "outerwear", "jacket", ["outer"], 3)
    d, r = run(10, WHITE_SHIRT, PLAIN_SWT, jacket, TROUSERS, MESH_SNK, hi=16)
    assert_valid(d, r)
    for o in r.outfits:
        assert not (o.picks["mid"] and o.picks["outer"]), o.picks


# ── the undershirt: under a shirt, never under a T-shirt ─────────────────────────

def test_no_undershirt_under_a_tee_and_one_under_a_shirt():
    under = g("vinner001", "white v-neck undershirt", "underwear", "undershirt", ["inner"], 1, sleeve="short")
    d, r = run(18, under, TEE, JEANS, SNEAK, hi=24)
    assert_valid(d, r)
    assert all(o.picks["inner"] is None for o in r.outfits)
    picks = {**r.outfits[0].picks, "inner": under["id"]}
    assert "inner-tee" in check.hard(check.issues(picks, d))
    d, r = run(18, under, WHITE_SHIRT, CHINOS, SNEAK, hi=24)
    assert r.outfits[0].picks["inner"] == under["id"]


# ── the coat and the belt in the register ─────────────────────────────────────────

def test_a_sporty_coat_never_goes_over_a_blazer():
    blazer = g("blazer009", "navy blazer", "outerwear", "blazer", ["mid", "outer"], 3, level=4)
    puffer = g("puffer009", "black puffer", "outerwear", "puffer", ["outer"], 5, colors=["black"], level=2)
    ctx = strict(3, WHITE_SHIRT, blazer, puffer, CHINOS, hi=8)
    assert pairing._register(ctx, _picks(base=WHITE_SHIRT, mid=blazer, outer=puffer)) is False
    assert pairing._register(ctx, _picks(base=WHITE_SHIRT, mid=blazer, outer=puffer, bottoms=CHINOS)) is False
    assert pairing._register(ctx, _picks(base=WHITE_SHIRT, outer=puffer, bottoms=CHINOS)) is True


def test_an_accent_belt_matches_the_shoes():
    red_shoes = g("redsnk001", "red leather sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["red"])
    ctx = strict(14, RED_BELT, MESH_SNK, red_shoes, hi=20)
    assert funnel.clash(ctx, _picks(footwear=MESH_SNK, accessories=RED_BELT)) == "belt"
    assert funnel.clash(ctx, _picks(footwear=red_shoes, accessories=RED_BELT)) is None


# ── the chooser sees the whole and may turn every outfit down ────────────────────

def test_the_chooser_is_told_the_filter_sees_only_pairs():
    assert "PAIR" in chooser.SYSTEM and "Knit on knit" in chooser.SYSTEM
    assert "never pick the least bad" in chooser.SYSTEM


def test_turned_down_every_time_is_served_with_the_reason_and_searches_at_most_twice(monkeypatch):
    shirts = [g(f"shrt{n:05d}", f"white shirt {n}", "tops", "shirt", ["base"], 2, colors=["white"]) for n in range(4)]
    no = fake_model.choice(0, reason="the shoes are too sporty for the trousers")
    out, seen = dress(monkeypatch, [*shirts, CHINOS, MESH_SNK, JEANS, SNEAK], weather(16, 22), prefs(),
                      [no, no, no, no])
    assert len(seen["chooser"]) <= 1 + 2, len(seen["chooser"])
    assert "the shoes are too sporty for the trousers" in out["text"]
    assert "looked right to the stylist" in out["text"]
