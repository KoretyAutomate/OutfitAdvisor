"""The warmth scale, measured from the wearer's home (user, 2026-08-30).

    "3 should be referred as the annual average temperature of the home location,
    5 the highest, and low the lowest. We should always take the mid point of the
    Monthly average range."

Warmth 1-5 used to be absolute: the classifier was asked for "1=summer-thin,
5=deep-winter" and the outer guard fired at a fixed 5/12/18C. One climate, shipped
to everybody. These tests pin three things:

  1. the ARITHMETIC — twelve monthly midpoints in, three anchors out, and a scale
     that maps each way without drifting;
  2. the FALLBACK — every refusal lands on the absolute table rather than on an
     exception, because a wearer with no home area still has a morning;
  3. the WIRING — that a climate sent by the phone actually reaches the guard, which
     is the half this project has broken three times with every unit correct.
"""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as srv
import closet as closet_llm
import llm
import picks as pk
import scale as sc
import weather
from schemas import ClimateAnchors

# asyncio.run rather than pytest-asyncio: this suite has no such plugin, and the
# house convention (test_shopping.py) is to run the coroutine directly.
#
# A temperate home: coldest month 0.4C, annual average 12.6C, warmest 24.3C.
COLD, AVG, HOT = 0.4, 12.6, 24.3


@pytest.fixture
def scale():
    c = sc.Climate.of(COLD, AVG, HOT)
    assert c is not None
    return c


def graded(warmth, cold=COLD, avg=AVG, hot=HOT):
    """A garment carrying the anchors its number was graded against."""
    return {"warmth": warmth, "warmthScale": "home", "warmthAnchors": [cold, avg, hot]}


# ── the anchors, from twelve monthly midpoints ────────────────────────────────

def _year(highs, lows, year=2020):
    """One year of Open-Meteo `daily`, 28 days a month so every month is present
    and each month's mean is exactly the value asked for."""
    time, hi, lo = [], [], []
    for m in range(1, 13):
        for d in range(1, 29):
            time.append(f"{year}-{m:02d}-{d:02d}")
            hi.append(highs[m - 1])
            lo.append(lows[m - 1])
    return {"time": time, "temperature_2m_max": hi, "temperature_2m_min": lo}


HIGHS = [4.0, 6.0, 11.0, 17.0, 22.0, 27.0, 30.0, 29.0, 25.0, 18.0, 12.0, 6.0]
LOWS = [-4.0, -3.0, 1.0, 6.0, 11.0, 16.0, 19.0, 18.0, 14.0, 8.0, 3.0, -2.0]
# midpoints: 0, 1.5, 6, 11.5, 16.5, 21.5, 24.5, 23.5, 19.5, 13, 7.5, 2


def test_anchors_are_the_midpoints_of_each_months_average_range(monkeypatch):
    """The user's own definition: the mid point of the monthly average range, not a
    mean of daily means. A month is dressed for by the range it spans."""
    async def fake_year(client, sem, point, window, year, daily=None):
        return _year(HIGHS, LOWS, year)

    monkeypatch.setattr(weather, "_archive_year", fake_year)
    out = asyncio.run(weather.fetch_climate_anchors(40.3, -74.6))

    assert out["months"] == [0.0, 1.5, 6.0, 11.5, 16.5, 21.5, 24.5, 23.5, 19.5, 13.0, 7.5, 2.0]
    assert out["cold"] == 0.0                     # January
    assert out["hot"] == 24.5                     # July
    assert out["avg"] == round(sum(out["months"]) / 12, 1)
    assert out["years"] == weather.NORMALS_YEARS


def test_the_range_ends_are_averaged_separately_not_pooled(monkeypatch):
    """The midpoint of the average RANGE, not the mean of every reading.

    With a complete month the two agree exactly, which is why this fixture drops
    most of one month's lows: the archive does return nulls, and a pooled mean then
    silently weights that month by its highs. Only the definition the user gave
    survives it.
    """
    async def fake_year(client, sem, point, window, year, daily=None):
        d = _year(HIGHS, LOWS, year)
        # July keeps all 28 highs and only 4 lows.
        seen = 0
        for i, t in enumerate(d["time"]):
            if t[5:7] == "07":
                seen += 1
                if seen > 4:
                    d["temperature_2m_min"][i] = None
        return d

    monkeypatch.setattr(weather, "_archive_year", fake_year)
    out = asyncio.run(weather.fetch_climate_anchors(40.3, -74.6))
    july = out["months"][6]
    assert july == round((30.0 + 19.0) / 2, 1)          # mean(highs), mean(lows)
    assert july != round((30.0 * 28 + 19.0 * 4) / 32, 1)  # what pooling would give


def test_only_the_two_temperature_variables_are_billed(monkeypatch):
    """Open-Meteo bills variables x days and this is the longest span the server
    ever asks for — paying for five variables to use two is trap 3 all over again."""
    asked: list = []

    async def fake_year(client, sem, point, window, year, daily=None):
        asked.append(daily)
        return _year(HIGHS, LOWS, year)

    monkeypatch.setattr(weather, "_archive_year", fake_year)
    asyncio.run(weather.fetch_climate_anchors(40.3, -74.6))
    assert asked and all(d == ["temperature_2m_max", "temperature_2m_min"] for d in asked)


def test_too_few_years_is_refused_rather_than_averaged(monkeypatch):
    """Two years is not a climate. A wrong anchor here is not a wrong forecast — it
    is a wardrobe scale that is wrong every day until the home changes."""
    calls = {"n": 0}

    async def fake_year(client, sem, point, window, year, daily=None):
        calls["n"] += 1
        return _year(HIGHS, LOWS, year) if calls["n"] <= 3 else None

    monkeypatch.setattr(weather, "_archive_year", fake_year)
    with pytest.raises(ValueError, match="archive years"):
        asyncio.run(weather.fetch_climate_anchors(40.3, -74.6))


def test_a_missing_month_is_refused(monkeypatch):
    """Every month, or none. A gap would put the coldest anchor on whichever month
    happened to survive, and nothing downstream could tell it had."""
    async def fake_year(client, sem, point, window, year, daily=None):
        d = _year(HIGHS, LOWS, year)
        keep = [i for i, t in enumerate(d["time"]) if t[5:7] != "07"]
        return {k: [v[i] for i in keep] for k, v in d.items()}

    monkeypatch.setattr(weather, "_archive_year", fake_year)
    with pytest.raises(ValueError, match="month"):
        asyncio.run(weather.fetch_climate_anchors(40.3, -74.6))


# ── the scale ─────────────────────────────────────────────────────────────────

def test_the_three_anchors_land_on_5_3_and_1(scale):
    # approx, because temp_for is deliberately unrounded — see its docstring.
    assert scale.temp_for(5) == pytest.approx(COLD)   # coldest month -> warmest garment
    assert scale.temp_for(3) == pytest.approx(AVG)    # annual average -> the middle
    assert scale.temp_for(1) == pytest.approx(HOT)    # warmest month -> the thinnest


def test_4_and_2_sit_between_their_neighbours(scale):
    """Piecewise through the anchors, not one straight line end to end: the annual
    average is rarely halfway between the extremes."""
    assert scale.temp_for(4) == pytest.approx((COLD + AVG) / 2)
    assert scale.temp_for(2) == pytest.approx((AVG + HOT) / 2)


def test_the_scale_reads_the_same_way_in_both_directions(scale):
    for w in range(1, 6):
        assert scale.warmth_for(scale.temp_for(w)) == w


def test_5_is_the_coldest_end_and_1_the_warmest(scale):
    """The direction the garments already had — a wool coat stays a 5, so nothing
    in anybody's closet has to be renumbered."""
    assert scale.warmth_for(COLD - 20) == 5
    assert scale.warmth_for(HOT + 20) == 1
    ws = [scale.warmth_for(t) for t in range(-10, 40)]
    assert ws == sorted(ws, reverse=True)     # never warmer clothes for a warmer day


def test_half_steps_round_the_same_way_as_the_phone():
    """Python breaks a tie to even and JS Math.round takes it upwards, so a computed
    4.5 was a 4 here and a 5 in the twin — the app's gap check and the server's
    outfit check disagreeing at exactly the thresholds they land on. Raised by the
    pre-push reviewer, 2026-08-31."""
    assert [sc._half_up(x) for x in (0.5, 1.5, 2.5, 3.5, 4.5)] == [1, 2, 3, 4, 5]
    # A scale whose midpoints fall exactly on a half step, so the tie is reached.
    s = sc.Climate.of(0.0, 10.0, 20.0)
    assert s is not None
    assert s.warmth_for(7.5) == 4          # 3 + 2*(2.5/10) = 3.5 -> 4, not 3
    assert s.warmth_for(15.0) == 2         # 3 - 2*(5/10)  = 2.0
    assert s.warmth_for(12.5) == 3         # 3 - 2*(2.5/10) = 2.5 -> 3, not 2


def test_a_hot_home_never_demands_a_parka():
    """Singapore: the guard used to be dead there — nothing was ever below 18C, so
    every garment cleared it. Now the coldest month still asks for the warmest thing
    they own, and the warmest month still asks for the thinnest."""
    s = sc.Climate.of(26.0, 27.5, 28.6)
    assert s is not None
    assert s.warmth_for(26.0) == 5
    assert s.warmth_for(28.6) == 1
    assert s.warmth_for(27.5) == 3


def test_a_cold_home_still_discriminates_below_five_degrees():
    """Oslo: the absolute table saturated at 5C, exactly where the cold starts to
    matter. -8C and +2C were both "warmth 4"; now they are not."""
    s = sc.Climate.of(-4.0, 6.0, 17.0)
    assert s is not None
    assert sc.absolute_min_warmth(-8.0) == sc.absolute_min_warmth(2.0) == 4   # the old table
    assert s.warmth_for(-8.0) > s.warmth_for(2.0)


# ── every refusal falls back, none of them raises ─────────────────────────────

@pytest.mark.parametrize("triple", [
    (None, 12.0, 24.0),          # nothing measured
    (12.0, None, 24.0),
    (12.0, 24.0, None),
    (5.0, 5.0, 5.0),             # a flat year — would divide by zero
    (24.0, 12.0, 0.0),           # the ends the wrong way round
    (12.0, 0.0, 24.0),           # an average outside its own extremes
])
def test_an_unusable_scale_is_none_not_an_exception(triple):
    assert sc.Climate.of(*triple) is None


def test_no_scale_means_the_absolute_table_everybody_had_before():
    """Pinned by value. This is the path for a wearer who has set no home area, and
    a silent drift here would re-grade every closet that has no climate."""
    assert [sc.min_outer_warmth(t) for t in (0, 4.9, 5, 11.9, 12, 17.9, 18, 30)] == \
        [4, 4, 3, 3, 2, 2, 1, 1]


def test_a_garment_is_judged_on_the_scale_IT_was_numbered_on(scale):
    """The migration question, and the answer to it.

    A "warmth 4" written under "1=summer-thin, 5=deep-winter" is not the same claim
    as a 4 graded against a wearer's year — the absolute table's implicit 3 is about
    8C where a real annual average is nearer 13. Reading the old number with the new
    ruler demotes every garment already in the closet, all at once, without anybody
    touching them. Raised by the pre-push reviewer, 2026-08-31.
    """
    old = {"warmth": 4}                                    # no stamp = the old scale
    # 2C is below this home's coldest month, so its own scale asks for a 5.
    assert scale.warmth_for(2.0) == 5
    assert sc.warm_enough(old, 2.0)                        # judged by the old table
    assert not sc.warm_enough(graded(4), 2.0)              # judged by the new one
    # And an explicit "absolute" reads the same as an absent one.
    assert sc.warm_enough({"warmth": 4, "warmthScale": "absolute"}, 2.0)


def test_a_garment_says_WHICH_year_it_was_graded_against():
    """"home" alone says a garment was graded against somebody's year without saying
    whose. A jumper graded in Singapore, read against Oslo's anchors after a move, is
    re-interpreted by a climate that never saw it — the same silent re-grade the
    stamp exists to prevent, one house move later. Raised by the pre-push reviewer,
    2026-08-31."""
    singapore = graded(3, 26.3, 27.1, 27.7)
    # A Singapore warmth-3 is a garment for a 27C day. Judged on ITS OWN year it is
    # nowhere near enough for a 2C Oslo morning, whatever Oslo's own scale says.
    assert not sc.warm_enough(singapore, 2.0)
    assert sc.warm_enough(singapore, 27.1)
    # Anchors that cannot make a scale fall back, like every other refusal here.
    assert sc.graded_on({"warmth": 3, "warmthScale": "home"}) is None
    assert sc.graded_on({"warmth": 3, "warmthScale": "home", "warmthAnchors": [9, 9, 9]}) is None
    assert sc.graded_on({"warmth": 3, "warmthAnchors": [COLD, AVG, HOT]}) is None


def test_the_guard_reads_the_scale_when_there_is_one():
    """The whole point: a garment GRADED on a wearer's year and found too thin for
    it is cleared, where the absolute table would have let it stand."""
    assert pk._warmth_violations({"outer": "i1"}, {"i1": {"warmth": 4}}, 2.0) == []
    assert pk._warmth_violations({"outer": "i1"}, {"i1": graded(4)}, 2.0) == ["outer"]


def test_an_empty_outer_slot_is_never_a_warmth_violation():
    assert pk._warmth_violations({"outer": None}, {}, -30.0) == []


# ── the wiring ────────────────────────────────────────────────────────────────

def test_from_anchors_reads_the_request_model():
    assert sc.from_anchors(None) is None
    c = sc.from_anchors(ClimateAnchors(cold=COLD, avg=AVG, hot=HOT))
    assert c is not None and c.temp_for(3) == pytest.approx(AVG)
    # A degenerate body is accepted by pydantic and refused by the scale — the
    # wearer loses their calibration, never their advice.
    assert sc.from_anchors(ClimateAnchors(cold=9.0, avg=9.0, hot=9.0)) is None


def test_the_classify_prompt_states_the_scale_in_degrees(scale):
    """'1=summer-thin, 5=deep-winter' asks the model to guess a climate it was never
    told. Given the anchors it is told in degrees instead."""
    generic = llm._warmth_line(None)
    local = llm._warmth_line(scale)
    assert "summer-thin" in generic and "C" not in generic
    assert "0C" in local and "13C" in local and "24C" in local
    assert "coldest month" in local and "warmest month" in local


@pytest.fixture
def client(monkeypatch):
    """The real server with only the network edges replaced — the LLM, the weather
    and the climate archive."""
    seen: dict = {}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        content = messages[0]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        seen.setdefault("prompts", []).append(prompt)
        if "Classify the clothing item" in prompt:
            return '{"label": "wool coat", "group": "outerwear", "type": "coat", ' \
                   '"category": "outer", "roles": ["outer"], "colors": ["grey"], ' \
                   '"warmth": 5, "formality": ["smart"], "waterproof": false}'
        return '{"picks": {"inner": null, "base": "i1", "mid": null, "outer": null, ' \
               '"bottoms": null, "footwear": null, "accessories": null}, ' \
               '"bullets": ["Base: the tee"], "tip": "Fine."}'

    async def fake_weather(lat, lon, day):
        return {"date": "2026-08-31", "timezone": "America/New_York", "code": 3,
                "emoji": "⛅", "desc": "Cloudy", "lo": 1, "hi": 6, "swing": 5,
                "feelsLo": 0, "feelsHi": 5, "rain": 10, "wind": 3, "morning": 2,
                "midday": 5, "evening": 3, "isSnow": False, "isRain": False}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    monkeypatch.setattr(closet_llm, "_chat", fake_chat)
    async def fake_range(lat, lon, start, end):
        days = [{"date": "2026-09-10", "code": 3, "emoji": "⛅", "desc": "Cloudy",
                 "lo": 10, "hi": 18, "rain": 10, "wind": 3, "isSnow": False,
                 "isRain": False}]
        return {"mode": "forecast", "days": days,
                "summary": {"mode": "forecast", "timezone": "America/New_York",
                            "nDays": 1, "loMin": 10, "hiMax": 18, "swing": 8,
                            "rainDays": 0, "windMax": 3, "isSnow": False,
                            "isRain": False}}

    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    monkeypatch.setattr(srv.weather, "fetch_range", fake_range)
    monkeypatch.setattr(srv.weather, "fetch_normals", fake_range)
    c = TestClient(srv.app)
    c.seen = seen
    return c


FAKE_IMAGE = (
    "aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgZW5vdWdoIHN0cmluZyB0byBwYXNzIHRoZSBt"
    "aW5pbXVtIGxlbmd0aCB2YWxpZGF0aW9uIGNoZWNrIGZvciB0aGUgZW5kcG9pbnQu"
)
TEE = {"id": "itm-00000001", "label": "white tee", "category": "base",
       "group": "tops", "type": "t_shirt", "roles": ["base"], "colors": ["white"],
       "warmth": 1, "formality": ["casual"], "waterproof": False, "availableCount": 1}


def test_climate_endpoint_answers_the_anchors(client, monkeypatch):
    async def fake_anchors(lat, lon):
        return {"months": [0.0] * 12, "cold": 0.0, "avg": 12.6, "hot": 24.3, "years": 10}

    monkeypatch.setattr(srv.weather, "fetch_climate_anchors", fake_anchors)
    d = client.post("/climate", json={"lat": 40.3, "lon": -74.6}).json()
    assert (d["cold"], d["avg"], d["hot"], d["years"]) == (0.0, 12.6, 24.3, 10)


def test_climate_endpoint_refuses_rather_than_inventing(client, monkeypatch):
    """Too little archive is a 503, so the phone keeps the absolute scale instead of
    anchoring every garment it owns to noise."""
    async def short(lat, lon):
        raise ValueError("only 3/10 archive years available (need 8)")

    async def down(lat, lon):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(srv.weather, "fetch_climate_anchors", short)
    assert client.post("/climate", json={"lat": 40.3, "lon": -74.6}).status_code == 503
    monkeypatch.setattr(srv.weather, "fetch_climate_anchors", down)
    assert client.post("/climate", json={"lat": 40.3, "lon": -74.6}).status_code == 502


def test_advice_takes_a_wardrobe_graded_either_way(client):
    """The scale is a property of a GARMENT here, not of the request: what has to be
    known at 06:45 is what each number meant when it was written."""
    body = {"lat": 40.3, "lon": -74.6, "closet": [TEE]}
    assert client.post("/advice", json=body).status_code == 200
    body["closet"] = [dict(TEE, warmthScale="home", warmthAnchors=[COLD, AVG, HOT])]
    assert client.post("/advice", json=body).status_code == 200


def test_a_garments_bad_anchors_cost_its_calibration_not_the_morning(client):
    """The one thing this must never do. A flat year, the ends the wrong way round,
    or a number off the end of the earth falls back to the absolute table for THAT
    garment — it does not 422 a request the rest of the wardrobe is fine in."""
    for bad in ([30.0, 10.0, 0.0], [9.0, 9.0, 9.0], [-400.0, 10.0, 20.0], [1.0, 2.0]):
        body = {"lat": 40.3, "lon": -74.6,
                "closet": [dict(TEE, warmthScale="home", warmthAnchors=bad)]}
        r = client.post("/advice", json=body)
        assert r.status_code == 200, bad
        assert r.json()["outfit_text"], bad


def test_an_out_of_range_anchor_is_rejected_on_the_endpoint_that_states_one(client):
    """/classify still takes the scale as a request field — it is grading a new
    photo against it — and there a nonsense triple is a nonsense request."""
    assert client.post("/classify", json={"imageB64": FAKE_IMAGE,
                                          "climate": {"cold": -400.0, "avg": 10.0,
                                                      "hot": 20.0}}).status_code == 422


def test_classify_stamps_which_scale_it_graded_on(client):
    """The stamp is what lets an old closet and a new one live side by side."""
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE}).json()
    assert d["warmthScale"] == "absolute"
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE,
                                       "climate": {"cold": COLD, "avg": AVG, "hot": HOT}}).json()
    assert d["warmthScale"] == "home"
    # And WHICH year it graded against, so a house move cannot re-interpret it.
    assert d["warmthAnchors"] == [COLD, AVG, HOT]


@pytest.mark.parametrize("answered", [0, 99, -3])
def test_a_number_the_TYPE_TABLE_filled_is_never_stamped_home(client, monkeypatch, answered):
    """The model was told the wearer's degrees — but only if it answered USABLY.
    Where it did not, TYPE_DEFAULTS filled the number, and that table is written in
    the absolute units it always was.

    99 is the case "did it answer at all?" gets wrong: the model has said something,
    the table quietly replaces it, and the replacement gets stamped as graded
    against a year that never saw it. Raised by the pre-push reviewer, 2026-08-31.
    """
    async def mute(messages, max_tokens, timeout=45, **kw):
        return '{"label": "wool coat", "group": "outerwear", "type": "coat", ' \
               '"category": "outer", "roles": ["outer"], "colors": [], ' \
               f'"warmth": {answered}, "formality": [], "waterproof": false}}'

    monkeypatch.setattr(llm, "_chat", mute)
    d = client.post("/classify", json={"imageB64": FAKE_IMAGE,
                                       "climate": {"cold": COLD, "avg": AVG, "hot": HOT}}).json()
    assert d["warmth"] == 4                    # filled from the type table
    assert d["warmthScale"] == "absolute"      # and stamped in the table's own units
    assert d["warmthAnchors"] is None


def test_an_old_closet_is_not_regraded_by_an_update(client):
    """The advice path, end to end. The morning after this ships, a closet whose
    numbers were all written on the old scale must be judged exactly as it was."""
    coat = {"id": "itm-00000009", "label": "wool coat", "category": "outer",
            "group": "outerwear", "type": "coat", "roles": ["outer"], "colors": [],
            "warmth": 4, "formality": ["casual"], "waterproof": False,
            "availableCount": 1}
    body = {"lat": 40.3, "lon": -74.6, "closet": [TEE, coat]}
    # The stub weather plans around 2C, where this home's own scale asks for a 5 —
    # so the coat stands only for as long as nobody re-reads its 4 on that scale.
    assert client.post("/advice", json=body).status_code == 200
    body["closet"] = [TEE, dict(coat, warmthScale="home",
                                warmthAnchors=[COLD, AVG, HOT])]
    assert client.post("/advice", json=body).status_code == 200


def test_a_graded_garment_states_its_units_to_the_model(client):
    """"warmth 3/5" is a number on an unnamed scale, and there are two of them now.

    The outfit path can afford that — every pick is checked afterwards — but PACKING
    has no such guard: the model's answer IS the answer, so a home-scale 3 read as
    an absolute 3 packs the wrong clothes and nothing notices. Raised by the
    pre-push reviewer, 2026-08-31.
    """
    # warmth 3 on this year is a garment for a ~13C day.
    graded = dict(TEE, warmth=3, warmthScale="home", warmthAnchors=[COLD, AVG, HOT])
    client.post("/packing", json={"lat": 40.3, "lon": -74.6, "start": "2026-09-10",
                                  "end": "2026-09-12", "closet": [graded]})
    packed = [p for p in client.seen["prompts"] if "warmth" in p]
    assert packed and any("for days around 13C" in p for p in packed), packed[-1][:400]

    # And an ungraded one keeps the bare number rather than being handed a
    # temperature nobody measured it against.
    client.seen["prompts"].clear()
    client.post("/packing", json={"lat": 40.3, "lon": -74.6, "start": "2026-09-10",
                                  "end": "2026-09-12", "closet": [TEE]})
    packed = [p for p in client.seen["prompts"] if "warmth" in p]
    assert packed and not any("for days around" in p for p in packed), packed[-1][:400]


def test_the_outfit_prompt_says_it_too(client):
    """One phrasing for both prompts — the two must not describe one wardrobe
    differently."""
    graded = dict(TEE, warmth=3, warmthScale="home", warmthAnchors=[COLD, AVG, HOT])
    client.post("/advice", json={"lat": 40.3, "lon": -74.6, "closet": [graded]})
    assert any("for days around 13C" in p for p in client.seen["prompts"])


def test_the_classifier_is_told_the_wearers_scale(client):
    """Wired, not merely implemented. /classify had been asking for `group` and
    `roles` for eight days while dropping both one line before the response."""
    client.post("/classify", json={"imageB64": FAKE_IMAGE})
    assert not any("coldest month" in p for p in client.seen["prompts"])
    client.seen["prompts"].clear()
    client.post("/classify", json={"imageB64": FAKE_IMAGE,
                                   "climate": {"cold": COLD, "avg": AVG, "hot": HOT}})
    assert any("coldest month" in p for p in client.seen["prompts"])
