"""The outfit advisor (advisor.py, 2026-10-11): a personal stylist asked to dress
one person, told what a fact check found, and asked again.

User, 2026-10-11: "It needs to act as an outfit advisor." These pin the shape of
that conversation; the live test days (check_common_sense_live.py) pin how well the
real model plays its part."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import advisor
import app as srv
import fake_model
import picks as pk
import style
from fake_model import outfit
from wardrobe_fixtures import CARDI, JEANS, KNIT_POLO, POLO, SNEAK, SWEATER, TEE, UNDER, weather

CLOSET = [UNDER, POLO, KNIT_POLO, CARDI, JEANS, SNEAK]


@pytest.fixture
def api(monkeypatch):
    async def cold_morning(lat, lon, day):
        return weather(10)
    monkeypatch.setattr(srv.weather, "fetch_weather", cold_morning)
    return TestClient(srv.app)


def post(api, closet=CLOSET, **body):
    r = api.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": closet, **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_model_is_a_stylist_told_who_it_dresses_and_what_they_own(api, monkeypatch):
    seen = fake_model.install(monkeypatch, [outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"],
                                                   bottoms=JEANS["id"], footwear=SNEAK["id"])])
    post(api, gender="man", style="casual")
    assert "You are a personal stylist" in seen["system"][0]
    prompt = seen["prompts"][0]
    for part in ("TODAY", "THE PERSON: a man who wants a casual look", "THEIR WARDROBE", '"look"'):
        assert part in prompt, part
    assert prompt.index('"look"') < prompt.index('"picks"'), "it pictures the outfit before it picks"
    assert POLO["id"] not in prompt, "handles, never ids"


def test_polo_over_polo_goes_back_with_the_reason_and_the_revision_stands(api, monkeypatch):
    """The 2026-10-11 morning, now: the model is told, and chooses again."""
    seen = fake_model.install(monkeypatch, [
        outfit(inner=UNDER["id"], base=POLO["id"], mid=KNIT_POLO["id"], bottoms=JEANS["id"], footwear=SNEAK["id"]),
        outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])])
    d = post(api)
    assert len(seen["prompts"]) == 2
    assert "two tops stacked" in seen["prompts"][1]
    assert d["picks"]["mid"] == CARDI["id"]


def test_if_it_insists_the_fallback_does_what_a_person_would(api, monkeypatch):
    stacked = outfit(inner=UNDER["id"], base=POLO["id"], mid=KNIT_POLO["id"], bottoms=JEANS["id"],
                     footwear=SNEAK["id"])
    seen = fake_model.install(monkeypatch, [stacked] * 3)
    d = post(api)
    assert len(seen["prompts"]) == 1 + advisor.MAX_REVISIONS
    assert d["picks"]["mid"] == CARDI["id"], "the second polo comes off, knitwear goes on"
    assert "• charcoal cardigan" in d["outfit_text"], "rebuilt from the final outfit"


def test_a_revision_never_trades_one_hole_for_another(api, monkeypatch):
    seen = fake_model.install(monkeypatch, [
        outfit(base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"]),              # no shoes
        outfit(base=POLO["id"], mid=CARDI["id"], footwear=SNEAK["id"]),             # no trousers
        outfit(base=POLO["id"], mid=CARDI["id"], footwear=SNEAK["id"])])
    d = post(api)
    assert len(seen["prompts"]) == 3
    assert d["picks"]["bottoms"] == JEANS["id"], "bare legs never beat bare feet"

    # After the fallback both end dressed alike, so the choice itself is pinned:
    import check
    first = advisor.Answer({}, {}, [check.Issue("no-footwear", "", True)])
    revised = advisor.Answer({}, {}, [check.Issue("no-bottoms", "", True)])
    assert not advisor._better(revised, first), "bare legs never pay for shoes"


def test_a_poor_look_goes_back_with_the_stylists_words(api, monkeypatch):
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    good = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    seen = fake_model.install(monkeypatch, [good, good],
                              [{"score": 2, "issue": "navy on navy hides the collar"}, {"score": 4, "issue": ""}])
    post(api)
    assert seen["stylist"] == 2
    assert 'a second stylist scored it 2/5: "navy on navy hides the collar"' in seen["prompts"][1]


def test_a_lower_scored_revision_does_not_replace_the_first(api, monkeypatch):
    monkeypatch.setenv("OUTFIT_STYLIST", "1")
    seen = fake_model.install(monkeypatch, [
        outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"]),
        outfit(inner=UNDER["id"], base=KNIT_POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"]),
        None], [{"score": 2, "issue": "flat"}, {"score": 1, "issue": "worse"}])
    d = post(api)
    assert d["picks"]["base"] == POLO["id"] and seen["calls"] >= 2


def test_no_reply_is_asked_once_and_the_app_answers_without_the_closet(api, monkeypatch):
    seen = fake_model.install(monkeypatch, [None])

    async def generic(*a, **k):
        return "• a sensible outfit"
    monkeypatch.setattr(srv.llm, "outfit_text", generic)
    d = post(api)
    assert seen["calls"] == 1 and d["closetUsed"] is False


def test_the_deadline_bounds_the_whole_conversation(monkeypatch):
    """A slow model: the answer stands as it is when time runs out."""
    monkeypatch.setattr(advisor, "DEADLINE_S", 0.3)

    async def slow(messages, max_tokens, timeout=45, **kw):
        await asyncio.sleep(1)
        return None
    monkeypatch.setattr(advisor, "_chat", slow)
    look = style.Look("casual", "man")
    assert asyncio.run(advisor.dress(weather(10), CLOSET, pk.Prefs(look=look))) is None


def test_a_reroll_samples_wider_and_says_so_when_nothing_else_suits(api, monkeypatch):
    same = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    seen = fake_model.install(monkeypatch, [same])
    shown = {s: v for s, v in same["picks"].items() if v}
    d = post(api, closet=[UNDER, POLO, CARDI, JEANS, SNEAK], shown=shown)
    assert seen["temperature"] == 0.9
    assert d["outfit_text"].startswith("• Same outfit again")


def test_what_they_wore_lately_is_on_the_garments_line(api, monkeypatch):
    seen = fake_model.install(monkeypatch, [outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"],
                                                   bottoms=JEANS["id"], footwear=SNEAK["id"])])
    post(api, recent={POLO["id"]: 1, "itm-unknown": 2, CARDI["id"]: 99})
    line = next(ln for ln in seen["prompts"][0].splitlines() if "navy polo shirt" in ln)
    assert "worn yesterday" in line
    assert "99" not in seen["prompts"][0], "out-of-range days are dropped by the schema"


def test_the_notification_reads_the_advisors_own_words(api, monkeypatch):
    """No catalogue garment beside the closet answer: an empty slot carries the
    advisor's own line, and the tip is the advisor's."""
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["outer"] = "None needed — the cardigan is enough."
    a["tip"] = "Push the sleeves up by noon."
    fake_model.install(monkeypatch, [a])
    d = post(api)
    assert d["outfit"]["outer"] == "None needed", "the phone's empty marker, not a garment tile"
    assert d["outfit"]["tip"] == "Push the sleeves up by noon."
    assert d["outfit"]["base"] == "navy polo shirt"
    assert "peakTemp" in d and "planTemp" in d


def test_a_worn_garment_always_has_a_line(api, monkeypatch):
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=SWEATER["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"] = {}
    fake_model.install(monkeypatch, [a])
    d = post(api, closet=[UNDER, POLO, SWEATER, JEANS, SNEAK])
    assert "navy polo shirt" in d["outfit_text"] and d["source"] == "llm"


def test_a_garment_the_fallback_took_off_is_not_recommended_by_another_line(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: the undershirt goes for a rule,
    and the base line and the tip must stop recommending it."""
    ban = {"kind": "avoid_pair", "a": {"type": "undershirt"}, "b": {"type": "polo"}}
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["base"] = "The navy polo over your grey v-neck inner."
    a["tip"] = "Keep the grey v-neck inner on under it."
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, rules=[ban])
    assert d["picks"]["inner"] is None
    assert "grey v-neck inner" not in d["outfit_text"], d["outfit_text"]


def test_a_removed_garment_described_by_its_kind_is_not_recommended(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: named "Airism", described as
    "your white undershirt"."""
    airism = {**UNDER, "label": "Airism"}
    ban = {"kind": "avoid_pair", "a": {"type": "undershirt"}, "b": {"type": "polo"}}
    a = outfit(inner=airism["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["base"] = "The navy polo over your white undershirt."
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, closet=[airism, POLO, CARDI, JEANS, SNEAK], rules=[ban])
    assert d["picks"]["inner"] is None and "undershirt" not in d["outfit_text"].lower(), d["outfit_text"]


def test_the_tip_goes_when_the_fallback_changed_the_outfit(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: "no mid-layer needed" under the
    cardigan the fallback just added."""
    cold = outfit(inner=UNDER["id"], base=POLO["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    cold["tip"] = "No mid-layer is needed today."
    fake_model.install(monkeypatch, [cold] * 3)
    d = post(api, closet=[UNDER, POLO, CARDI, JEANS, SNEAK])
    assert d["picks"]["mid"] == CARDI["id"] and "No mid-layer" not in d["outfit_text"]


def test_a_garment_the_fallback_moved_is_not_a_gap(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: a mid-only hoodie filed as base,
    moved to mid — the wearer has a top on, nothing to buy."""
    from wardrobe_fixtures import g
    hoodie = g("hoodie001", "grey hoodie", "tops", "hoodie", ["mid", "outer"], 3)
    wrong = outfit(base=hoodie["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    fake_model.install(monkeypatch, [wrong] * 3)
    d = post(api, closet=[hoodie, JEANS, SNEAK], closetOnly=True)
    assert hoodie["id"] in d["picks"].values() and "base" not in d["missing"], d["missing"]


def test_a_replaced_garment_named_by_colour_and_kind_is_not_recommended(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: "Airism" (a white tee) banned and
    replaced by a black tee — "your white T-shirt" must go too."""
    from wardrobe_fixtures import g
    airism = g("airism001", "Airism", "tops", "t_shirt", ["base"], 1, colors=["white"])
    black = g("blacktee1", "black tee", "tops", "t_shirt", ["base"], 1, colors=["black"])
    ban = {"kind": "avoid_item", "a": {"type": "t_shirt", "color": "white"}}
    a = outfit(base=airism["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["bottoms"] = "Blue jeans go with your white T-shirt."
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, closet=[airism, black, JEANS, SNEAK], rules=[ban])
    assert d["picks"]["base"] == black["id"] and "white t-shirt" not in d["outfit_text"].lower(), d["outfit_text"]


def test_an_unneeded_slot_reaches_the_phone_as_its_empty_marker(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: the phone draws anything not
    starting "None" as a garment tile."""
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["outer"] = "No jacket needed in the mild morning."
    fake_model.install(monkeypatch, [a])
    assert post(api)["outfit"]["outer"] == "None needed"


def test_same_again_is_only_blamed_on_the_wardrobe_when_true(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: a suitable polo sat unused."""
    same = outfit(inner=UNDER["id"], base=TEE["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    fake_model.install(monkeypatch, [same] * 3)
    shown = {s: v for s, v in same["picks"].items() if v}
    d = post(api, closet=[UNDER, TEE, POLO, CARDI, JEANS, SNEAK], shown=shown)
    assert "nothing else you own suits today" not in d["outfit_text"]


def test_after_a_fallback_no_line_contradicts_the_final_outfit(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11, three rounds running: removed
    garments by name or punctuation-ended label, an added layer denied by another
    line, a tip about the old outfit. The text is rebuilt from the final picks."""
    odd = {**UNDER, "label": "Airism (white)"}
    ban = {"kind": "avoid_pair", "a": {"type": "undershirt"}, "b": {"type": "polo"}}
    a = outfit(inner=odd["id"], base=POLO["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"] = {"base": "Your navy polo alone; no cardigan needed.",
                  "bottoms": "Blue jeans go well with your Airism (white).", "footwear": "Sneakers."}
    a["tip"] = "Skip the cardigan."
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, closet=[odd, POLO, CARDI, JEANS, SNEAK], rules=[ban])
    t = d["outfit_text"]
    assert d["picks"]["inner"] is None and d["picks"]["mid"] == CARDI["id"]
    assert "Airism" not in t and "no cardigan" not in t and "Skip the cardigan" not in t, t


def test_an_invented_handle_on_a_hot_day_is_not_shopping_evidence(monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11."""
    async def hot(lat, lon, day):
        return weather(28, hi=31)
    monkeypatch.setattr(srv.weather, "fetch_weather", hot)
    bad = outfit(base=TEE["id"], outer="i99", bottoms=JEANS["id"], footwear=SNEAK["id"])
    fake_model.install(monkeypatch, [bad] * 3)
    d = post(TestClient(srv.app), closet=[TEE, JEANS, SNEAK], closetOnly=True)
    assert d["missing"] == [], d["missing"]


def test_after_a_fallback_a_half_registered_closet_keeps_its_generic_suggestion(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11."""
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=KNIT_POLO["id"], bottoms=JEANS["id"])
    a["lines"]["footwear"] = "White leather sneakers (not in your closet yet)."
    a["missing"] = ["footwear"]
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, closet=[UNDER, POLO, KNIT_POLO, CARDI, JEANS])
    assert d["picks"]["mid"] == CARDI["id"], "the fallback ran"
    assert "White leather sneakers (not in your closet yet)." in d["outfit_text"]


def test_a_garment_the_fallback_banned_is_not_kept_as_a_generic_suggestion(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11."""
    ban = {"kind": "avoid_item", "a": {"type": "undershirt"}}
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    a["lines"]["inner"] = "Wear your grey v-neck inner."
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, rules=[ban])
    assert d["picks"]["inner"] is None and "grey v-neck inner" not in d["outfit_text"]
    assert "grey v-neck inner" not in str(d["outfit"]["inner"])


def test_an_absence_reaches_the_phone_as_its_empty_marker(api, monkeypatch):
    """Raised by the pre-push reviewer, 2026-10-11: the only undershirt banned — the
    phone must not draw "nothing in your closet" as a garment tile."""
    ban = {"kind": "avoid_item", "a": {"type": "undershirt"}}
    a = outfit(inner=UNDER["id"], base=POLO["id"], mid=CARDI["id"], bottoms=JEANS["id"], footwear=SNEAK["id"])
    fake_model.install(monkeypatch, [a] * 3)
    d = post(api, rules=[ban])
    assert "inner" in d["missing"] and d["outfit"]["inner"].startswith("None"), d["outfit"]["inner"]


def test_snow_never_demands_boots_they_have_banned():
    """Raised by the pre-push reviewer, 2026-10-11: an impossible correction asked
    three times."""
    import check
    from wardrobe_fixtures import BOOTS, day, ids
    ban = {"kind": "avoid_item", "a": {"type": "boots"}}
    d = day(-3, UNDER, SWEATER, JEANS, SNEAK, BOOTS, isSnow=True, prefs=pk.Prefs(rules=(ban,)))
    found = check.issues(ids(inner=UNDER, base=SWEATER, bottoms=JEANS, footwear=SNEAK), d)
    assert not any(i.kind == "snow-footwear" for i in found)


def test_the_morning_push_forwards_recent_wear_counted_at_fire_time():
    """The worker turns the snapshot's `recentAt` times into `recent` days when it
    fires (Kotlin cannot run here; this pins the seam against the server's field)."""
    from pathlib import Path
    kt = (Path(__file__).resolve().parents[2] / "app" / "android" / "app" / "src" / "main" / "java"
          / "com" / "korety" / "outfitadvisor" / "AdviceWorker.kt").read_text()
    body = kt[kt.index("private fun attachWardrobe"):]
    assert 'optJSONObject("recentAt")' in body and 'body.put("recent", recent)' in body
    assert "daysAgo(at.optLong(id), System.currentTimeMillis())" in body
    import schemas
    assert "recent" in schemas.AdviceRequest.model_fields
