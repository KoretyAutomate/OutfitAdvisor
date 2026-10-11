"""The model looks at its own outfit again when it did not hold up (user,
2026-10-11): "no human would wear such outfit ... shouldn't we approach it with the
prompt?"

The morning this was written, a polo went over a polo. The model's answer had only
a polo on top on a cold morning; the warmth fixer added the lightest legal mid
layer — a second polo — and nothing with judgement looked at the result. Now the
model is told what had to be repaired and chooses again."""
import json

from fastapi.testclient import TestClient

import app as srv
import closet as closet_llm
import llm
import review
import style
import stylist


def g(iid, label, group, typ, roles, warmth, **kw):
    return {"id": iid, "label": label, "category": roles[0], "group": group, "type": typ,
            "roles": roles, "colors": ["navy"], "warmth": warmth, "formality": ["casual"],
            "waterproof": False, "count": 1, **kw}


POLO = g("itm-navypolo1", "navy polo shirt", "tops", "polo", ["base", "mid", "outer"], 2)
KNIT_POLO = g("itm-knitpolo1", "knit polo", "tops", "polo", ["base", "mid", "outer"], 3)
SWEATER = g("itm-sweater01", "navy v-neck sweater", "tops", "sweater", ["mid", "outer"], 4)
PANTS = g("itm-beigepnt1", "beige drawstring pants", "bottoms", "trousers", ["bottoms"], 3)
SHOES = g("itm-loafers01", "brown loafers", "footwear", "loafers", ["footwear"], 2)
CLOSET = [POLO, KNIT_POLO, SWEATER, PANTS, SHOES]


def outfit(**picks):
    full = {"inner": None, "base": None, "mid": None, "outer": None, "bottoms": None,
            "footwear": None, "accessories": None, **picks}
    return json.dumps({"picks": full, "bullets": [f"{k}: chosen" for k, v in full.items() if v],
                       "missing": [], "tip": "Have a good day."})


def client(monkeypatch, answers, stylist_replies=(), morning=10):
    """The model answers from `answers` in order (outfit prompts) and from
    `stylist_replies` for stylist prompts. Records every outfit prompt."""
    seen = {"prompts": [], "stylist": 0}
    outfits, reviews = list(answers), list(stylist_replies)

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        p = messages[0]["content"]
        if p.startswith("You are a personal stylist"):
            seen["stylist"] += 1
            return json.dumps(reviews.pop(0)) if reviews else None
        seen["prompts"].append(p)
        return outfits.pop(0) if outfits else None

    async def fake_weather(lat, lon, day):
        return {"date": "2026-10-11", "timezone": "America/New_York", "code": 61, "emoji": "🌧",
                "desc": "Rain", "lo": morning, "hi": morning + 5, "swing": 5, "feelsLo": morning,
                "feelsHi": morning + 5, "rain": 93, "wind": 3, "morning": morning, "midday": morning + 4,
                "evening": morning + 2, "isSnow": False, "isRain": True}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def post(c, closet=CLOSET):
    r = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet})
    assert r.status_code == 200, r.text
    return r.json()


def test_polo_over_polo_goes_back_to_the_model(monkeypatch):
    """This morning's outfit. The first answer has one polo on a 10C morning; the
    repair would add the knit polo over it. The model is told and picks the sweater."""
    c = client(monkeypatch, [outfit(base=POLO["id"], bottoms=PANTS["id"], footwear=SHOES["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    d = post(c)
    assert len(c.seen["prompts"]) == 2
    second = c.seen["prompts"][1]
    assert "REVISION" in second and "knit polo had to be added as the mid" in second
    assert "base: navy polo shirt" in second, "the model is shown what it chose"
    assert d["picks"]["mid"] == SWEATER["id"] and d["picks"]["base"] == POLO["id"]


def test_without_the_review_the_repair_would_have_stacked_the_polos(monkeypatch):
    """The same first answer with no time left for a second look: the code repair
    is the last resort, so it still dresses them — which is why the look matters."""
    monkeypatch.setattr(review, "REVISE_BUDGET_S", -1)
    c = client(monkeypatch, [outfit(base=POLO["id"], bottoms=PANTS["id"], footwear=SHOES["id"])])
    d = post(c)
    assert len(c.seen["prompts"]) == 1
    assert d["picks"]["mid"] == KNIT_POLO["id"]


def test_a_sound_outfit_is_asked_for_once(monkeypatch):
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    post(c)
    assert len(c.seen["prompts"]) == 1


def test_no_shoes_when_they_own_some_goes_back(monkeypatch):
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    d = post(c)
    assert "no shoes, though they own suitable ones" in c.seen["prompts"][1]
    assert d["picks"]["footwear"] == SHOES["id"]


def test_no_shoes_owned_is_not_a_problem(monkeypatch):
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"])])
    post(c, [POLO, KNIT_POLO, SWEATER, PANTS])
    assert len(c.seen["prompts"]) == 1


def test_a_poor_stylist_score_goes_back_with_what_it_said(monkeypatch):
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    good = outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"], footwear=SHOES["id"])
    c = client(monkeypatch, [good, good],
               [{"score": 2, "issue": "navy on navy hides the collar", "swap": None},
                {"score": 4, "issue": "", "swap": None}])
    post(c)
    assert c.seen["stylist"] == 2 and len(c.seen["prompts"]) == 2
    assert 'a stylist scored it 2/5: "navy on navy hides the collar"' in c.seen["prompts"][1]


def test_a_worse_revision_does_not_replace_the_first_answer(monkeypatch):
    """First: no shoes (one problem). Revision: no shoes AND nothing warm on top."""
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"]),
                             outfit(base=POLO["id"], bottoms=PANTS["id"])])
    d = post(c)
    assert len(c.seen["prompts"]) == 2 and d["picks"]["mid"] == SWEATER["id"]


def test_a_revision_that_never_comes_keeps_the_first(monkeypatch):
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"])])
    d = post(c)
    assert d["picks"]["mid"] == SWEATER["id"] and "review" not in d


def test_the_prompt_asks_for_common_sense_and_rain_is_an_umbrella(monkeypatch):
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    post(c)
    p = c.seen["prompts"][0]
    assert "DRESS LIKE A PERSON" in p and "polo over polo" in p
    assert "they carry an umbrella" in p and "waterproof outer" not in p
    assert "not waterproof" not in p, "rain never chooses a garment, so the listing does not say"


def test_the_stylist_reports_its_verdict_even_when_the_swap_is_refused(monkeypatch):
    import asyncio
    monkeypatch.setenv("OUTFIT_STYLIST", "1")

    async def fake(*a, **k):
        return json.dumps({"score": 2, "issue": "too dark", "swap": {"slot": "base", "handle": "zz"}})
    monkeypatch.setattr(llm, "_chat", fake)
    from picks import Prefs, _index
    ctx = style.ctx_of({"morning": 15, "lo": 14, "hi": 18}, _index(CLOSET), Prefs())
    v = asyncio.run(stylist.review(ctx, {"base": POLO["id"], "bottoms": PANTS["id"]}))
    assert v == stylist.Verdict(2, "too dark", None)


def test_no_trousers_when_they_own_some_goes_back(monkeypatch):
    """Found by the live test days: the sneakers in both slots, the duplicate
    cleared, and nobody's legs dressed."""
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], footwear=SHOES["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    d = post(c)
    assert "no trousers, though they own suitable ones" in c.seen["prompts"][1]
    assert d["picks"]["bottoms"] == PANTS["id"]


def test_a_revision_that_leaves_the_legs_bare_loses(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11. First: a warmth repair, trousers
    on (one problem). Revision: the sweater chosen, trousers dropped (one problem).
    Equal counts — but bare legs are worse than a repaired outfit."""
    c = client(monkeypatch, [outfit(base=POLO["id"], bottoms=PANTS["id"], footwear=SHOES["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], footwear=SHOES["id"])])
    d = post(c)
    assert len(c.seen["prompts"]) == 2
    assert d["picks"]["bottoms"] == PANTS["id"]


def test_a_revision_that_runs_past_the_deadline_keeps_the_first(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: the revision is bounded too, not
    only its start, so the phone never waits past its own limit."""
    import asyncio
    monkeypatch.setattr(review, "DEADLINE_S", 0.2)
    # The revision WOULD win (shoes added) — only the deadline keeps the first.
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    slow = llm._chat

    async def stall(messages, *a, **k):
        if "REVISION" in messages[0]["content"]:
            await asyncio.sleep(1)
        return await slow(messages, *a, **k)
    monkeypatch.setattr(closet_llm, "_chat", stall)
    d = post(c)
    assert d["picks"]["mid"] == SWEATER["id"] and not d["picks"]["footwear"]


def test_the_clock_starts_with_the_request_not_after_the_weather(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: a slow forecast counts against
    the budget, or a revision starts that the phone will not wait for."""
    import asyncio
    monkeypatch.setattr(review, "REVISE_BUDGET_S", 0.1)
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])])
    quick = srv.weather.fetch_weather

    async def slow_weather(*a):
        await asyncio.sleep(0.3)
        return await quick(*a)
    monkeypatch.setattr(srv.weather, "fetch_weather", slow_weather)
    post(c)
    assert len(c.seen["prompts"]) == 1, "the weather used the budget up"


def test_a_lower_scored_revision_does_not_replace_the_first(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: 2/5 then 1/5 is one problem each,
    and the score decides."""
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"], footwear=SHOES["id"]),
                             outfit(base=KNIT_POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"])],
               [{"score": 2, "issue": "flat", "swap": None}, {"score": 1, "issue": "worse", "swap": None}])
    d = post(c)
    assert len(c.seen["prompts"]) == 2 and d["picks"]["base"] == POLO["id"]


def test_on_snow_waterproof_boots_are_never_swapped_for_ones_that_are_not():
    """Raised by the pre-push reviewer, 2026-10-11: rain stopped choosing garments,
    snow did not."""
    from picks import Prefs, _index
    boots = g("itm-snowboot1", "snow boots", "footwear", "boots", ["footwear"], 4, waterproof=True)
    plain = g("itm-plainbt1", "suede boots", "footwear", "boots", ["footwear"], 4)
    wardrobe = _index([POLO, SWEATER, PANTS, boots, plain])
    picks = {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"], "footwear": boots["id"]}
    snowy = style.ctx_of({"morning": -2, "lo": -4, "hi": 1, "isSnow": True}, wardrobe, Prefs())
    rainy = style.ctx_of({"morning": -2, "lo": -4, "hi": 1, "isRain": True}, wardrobe, Prefs())
    assert not style.legal_swap(snowy, picks, "footwear", plain["id"], improve=False)
    assert style.legal_swap(rainy, picks, "footwear", plain["id"], improve=False)


def test_on_snow_the_warmth_fixer_reaches_for_the_waterproof_coat():
    """Raised by the pre-push reviewer, 2026-10-11."""
    import layers
    from picks import _index
    tee = g("itm-tee00001", "white tee", "tops", "t_shirt", ["base"], 1)
    cardi = g("itm-cardi0001", "grey cardigan", "tops", "cardigan", ["mid", "outer"], 4)
    coat = g("itm-coat00001", "waterproof parka", "outerwear", "coat", ["outer"], 4, waterproof=True)
    wd = _index([tee, cardi, coat, PANTS, SHOES])
    for snow, want in ((True, ("outer", coat["id"])), (False, ("mid", cardi["id"]))):
        picks = {"base": tee["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]}
        layers.tidy(picks, wd, 2, [], peak_temp=5, day=layers.Day(snow=snow))
        assert picks.get(want[0]) == want[1], (snow, picks)


def test_the_listing_says_waterproof_only_on_snow():
    import closet_prompt
    boots = g("itm-snowboot1", "snow boots", "footwear", "boots", ["footwear"], 4, waterproof=True,
              availableCount=1)
    items = [{**i, "availableCount": 1} for i in (POLO, PANTS)] + [boots]
    w = {"lo": -3, "hi": 1, "feelsLo": -6, "feelsHi": 0, "desc": "Snow", "rain": 0, "wind": 2,
         "morning": -2, "midday": 0, "evening": -1, "swing": 4, "isRain": False, "isSnow": True}
    assert "snow boots (Boots) | " in closet_prompt._closet_prompt(w, "man", "casual", items)
    assert "| waterproof" in closet_prompt._closet_prompt(w, "man", "casual", items)
    assert "waterproof |" not in closet_prompt._closet_prompt({**w, "isSnow": False, "rain": 90},
                                                             "man", "casual", items)


def test_a_revision_that_leaves_them_cold_loses():
    """Raised by the pre-push reviewer, 2026-10-11: the first answer was made warm by
    a repair; a revision that ends with nothing warm enough on top never wins, even
    with no repairs of its own."""
    from picks import _index
    wd = _index(CLOSET)
    w = {"morning": 10, "lo": 10, "hi": 15}
    warm = {"picks": {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"],
                      "footwear": SHOES["id"]},
            "review": review.Seen(None, [("mid", SWEATER["id"], "warmth")])}
    cold = {"picks": {"base": POLO["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]},
            "review": review.Seen(None, [])}
    assert not review.better(cold, warm, wd, w) and review.better(warm, cold, wd, w)


def test_an_unreviewed_revision_does_not_win_by_escaping_the_stylist(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: the first answer scored 2/5; the
    revision got no review and needed a warmth repair (polo over polo). The poor
    score is what asked for the revision — it is not evidence against the first."""
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"],
                                    footwear=SHOES["id"]),
                             outfit(base=POLO["id"], bottoms=PANTS["id"], footwear=SHOES["id"])],
               [{"score": 2, "issue": "flat", "swap": None}])
    d = post(c)
    assert len(c.seen["prompts"]) == 2 and d["picks"]["mid"] == SWEATER["id"]


def test_a_topless_revision_loses():
    """Raised by the pre-push reviewer, 2026-10-11: with nothing above the waist
    there is nothing to be cold IN, so 'still too cold' alone let it through."""
    from picks import _index
    wd = _index(CLOSET)
    w = {"morning": 20, "lo": 18, "hi": 24}
    dressed = {"picks": {"base": POLO["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]},
               "review": review.Seen(None, [("base", POLO["id"])])}
    topless = {"picks": {"bottoms": PANTS["id"], "footwear": SHOES["id"]}, "review": review.Seen(None, [])}
    assert not review.better(topless, dressed, wd, w) and review.better(dressed, topless, wd, w)


def test_lost_trousers_count_even_when_no_pair_suits_the_new_top():
    """Raised by the pre-push reviewer, 2026-10-11: a revised top that a rule forbids
    with every pair of trousers made the missing trousers vanish from the ranking.
    Coverage is now judged by what they own, so no rule can hide it — the shirt
    with no trousers loses whatever rules there are."""
    from picks import _index
    shirt = g("itm-oxford001", "blue oxford", "tops", "shirt", ["base"], 2)
    wd = _index([*CLOSET, shirt])
    w = {"morning": 10, "lo": 9, "hi": 12}
    complete = {"picks": {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"],
                          "footwear": SHOES["id"]},
                "review": review.Seen(None, [("mid", SWEATER["id"], "warmth")])}
    legless = {"picks": {"base": shirt["id"], "mid": SWEATER["id"], "footwear": SHOES["id"]},
               "review": review.Seen(None, [])}
    assert not review.better(legless, complete, wd, w) and review.better(complete, legless, wd, w)


def test_a_better_look_outranks_fewer_repairs():
    """Raised by the pre-push reviewer, 2026-10-11: 5/5 after a warmth repair beats
    1/5 that needed nothing."""
    from picks import _index
    wd = _index(CLOSET)
    w = {"morning": 10, "lo": 10, "hi": 15}
    dressed = {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]}
    good = {"picks": dressed, "review": review.Seen(stylist.Verdict(5, ""), [("mid", SWEATER["id"], "warmth")])}
    ugly = {"picks": dressed, "review": review.Seen(stylist.Verdict(1, "clashes"), [])}
    assert not review.better(ugly, good, wd, w) and review.better(good, ugly, wd, w)


def test_a_score_from_before_an_applied_swap_is_not_compared():
    """Raised by the pre-push reviewer, 2026-10-11: the stylist's swap fixed the
    revision, so its 1/5 is about an outfit that no longer exists."""
    from picks import _index
    wd = _index(CLOSET)
    w = {"morning": 15, "lo": 14, "hi": 18}
    dressed = {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]}
    first = {"picks": dressed, "review": review.Seen(stylist.Verdict(2, "flat"), [])}
    fixed = {"picks": dressed, "review": review.Seen(
        stylist.Verdict(1, "wrong shoes", ("footwear", SHOES["id"], "wrong shoes")), [])}
    assert review.better(fixed, first, wd, w)


def test_trading_bare_feet_for_bare_legs_is_a_loss(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: one lack never cancels another."""
    c = client(monkeypatch, [outfit(base=POLO["id"], mid=SWEATER["id"], bottoms=PANTS["id"]),
                             outfit(base=POLO["id"], mid=SWEATER["id"], footwear=SHOES["id"])])
    d = post(c)
    assert len(c.seen["prompts"]) == 2 and d["picks"]["bottoms"] == PANTS["id"]


def test_on_snow_a_revision_that_drops_the_waterproof_boots_loses():
    """Raised by the pre-push reviewer, 2026-10-11."""
    from picks import _index
    boots = g("itm-snowboot1", "snow boots", "footwear", "boots", ["footwear"], 4, waterproof=True)
    suede = g("itm-suedebt1", "suede boots", "footwear", "boots", ["footwear"], 4)
    wd = _index([*CLOSET, boots, suede])
    w = {"morning": -2, "lo": -4, "hi": 1, "isSnow": True}
    dressed = {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"]}
    dry = {"picks": {**dressed, "footwear": boots["id"]},
           "review": review.Seen(None, [("mid", SWEATER["id"], "warmth")])}
    wet = {"picks": {**dressed, "footwear": suede["id"]}, "review": review.Seen(None, [])}
    assert not review.better(wet, dry, wd, w) and review.better(dry, wet, wd, w)


def test_a_revision_that_overheats_loses():
    """Raised by the pre-push reviewer, 2026-10-11: a jumper as the all-day base on a
    day that peaks at 30."""
    from picks import _index
    linen = g("itm-linenshrt", "linen shirt", "tops", "shirt", ["base", "mid"], 1)
    wd = _index([*CLOSET, linen])
    w = {"morning": 10, "lo": 10, "hi": 30}
    light = {"picks": {"base": linen["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]},
             "review": review.Seen(None, [("mid", SWEATER["id"], "warmth")])}
    hot = {"picks": {"base": SWEATER["id"], "mid": linen["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]},
           "review": review.Seen(None, [])}
    assert "cooler base" in review.unresolved(hot, wd, w)
    assert not review.better(hot, light, wd, w)


def test_a_revision_that_brings_in_a_disliked_pairing_loses():
    """Raised by the pre-push reviewer, 2026-10-11: the style repair keeps a pairing
    it has no legal swap for, so the review must not accept one the first answer
    did not have."""
    from picks import _index
    wd = _index(CLOSET)
    w = {"morning": 10, "lo": 9, "hi": 12}
    look = style.Look("casual", "man", disliked=((KNIT_POLO["id"], PANTS["id"]),))
    ok = {"picks": {"base": POLO["id"], "mid": SWEATER["id"], "bottoms": PANTS["id"], "footwear": SHOES["id"]},
          "review": review.Seen(stylist.Verdict(2, "flat"), [])}
    voted_down = {"picks": {**ok["picks"], "base": KNIT_POLO["id"]},
                  "review": review.Seen(stylist.Verdict(2, "flat"), [])}
    assert not review.better(voted_down, ok, wd, w, look)


def test_a_second_slot_breaking_the_same_style_rule_is_a_second_problem():
    """Raised by the pre-push reviewer, 2026-10-11: 'smarter for today' on the shoes
    must not hide 'smarter for today' on the trousers."""
    from picks import _index
    joggers = g("itm-joggers01", "grey joggers", "bottoms", "trousers", ["bottoms"], 3, formality=["active"])
    trainers = g("itm-trainer01", "running shoes", "footwear", "sneakers", ["footwear"], 2, formality=["active"])
    wd = _index([*CLOSET, joggers, trainers])
    w = {"morning": 10, "lo": 9, "hi": 12}
    look = style.Look("smart", "man")
    top = {"base": POLO["id"], "mid": SWEATER["id"]}
    one = {"picks": {**top, "bottoms": PANTS["id"], "footwear": trainers["id"]}, "review": review.Seen()}
    two = {"picks": {**top, "bottoms": joggers["id"], "footwear": trainers["id"]}, "review": review.Seen()}
    assert not review.better(two, one, wd, w, look)
