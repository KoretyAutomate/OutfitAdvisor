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
