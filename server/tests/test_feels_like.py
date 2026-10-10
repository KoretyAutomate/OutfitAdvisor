"""Dress for how the day FEELS, 08:00-19:00, or until an evening event ends
(user, 2026-10-10): "20 degrees on a sunny non windy day feels much warmer than the
20 degrees on a cloudy windy day ... feels like temperature between 8am and 7pm
unless there is an event in our calendar"."""
from fastapi.testclient import TestClient

import app as srv
import engine
import llm
import reroll
import weather
from schemas import AdviceRequest

# hour, air, feels-like. A windy, cloudy day: it feels 6C colder than it is at 08:00
# (bounded to 4), and the evening drops to 9C.
HOURS = [[8, 14.0, 8.0], [10, 16.0, 13.0], [13, 20.0, 24.5], [16, 18.0, 17.0],
         [19, 15.0, 13.0], [20, 13.0, 11.0], [22, 11.0, 9.0], [23, 10.0, 8.0]]


def day(**kw):
    return {"date": "2026-10-10", "timezone": "UTC", "code": 3, "emoji": "☁", "desc": "Overcast",
            "lo": 10, "hi": 20, "swing": 10, "feelsLo": 8, "feelsHi": 25, "rain": 0, "wind": 9,
            "morning": 14, "midday": 20, "evening": 15, "isSnow": False, "isRain": False,
            "hours": HOURS, **kw}


def test_feels_like_moves_an_hour_but_only_so_far():
    assert weather.felt(14, 8) == 10          # 6 colder, bounded to 4
    assert weather.felt(20, 24.5) == 23       # 4.5 warmer, bounded to 3
    assert weather.felt(16, 13) == 13         # inside the bounds: as felt
    assert weather.felt(16, None) == 16       # no feels-like: the air


def test_the_day_is_8_to_19_by_default():
    w = weather.with_plan(day())
    assert w["planLo"] == 10 and w["planHi"] == 23 and w["planUntil"] == 19
    assert engine.plan_temp(w) == 10, "the coldest felt hour, not the 14C air at 08:00"
    assert engine.peak(w) == 23


def test_an_evening_event_stretches_the_day_to_its_end():
    w = weather.with_plan(day(), 22)
    assert w["planUntil"] == 22 and w["planLo"] == 9, "22:00 feels 9C"
    w = weather.with_plan(day(), 24)
    assert w["planLo"] == 8, "until midnight reaches the last hour of the day"
    assert weather.with_plan(day(), 18)["planUntil"] == 19, "an earlier end never shortens the day"


def test_without_hourly_data_the_morning_still_decides():
    w = weather.with_plan(day(hours=[]))
    assert "planLo" not in w and engine.plan_temp(w) == 14 and engine.peak(w) == 20


def test_the_thermal_offset_moves_the_window_too():
    w = engine.apply_temp_offset(weather.with_plan(day()), 2)
    assert w["planLo"] == 12 and w["planHi"] == 25


def test_out_until_is_an_evening_hour_or_nothing():
    base = {"lat": 0, "lon": 0}
    assert AdviceRequest(**base, outUntil=22).outUntil == 22
    for bad in (18, 25, "late", None, -1):
        assert AdviceRequest(**base, outUntil=bad).outUntil is None


def test_the_prompt_says_what_the_day_feels_like():
    flags = " ".join(llm._weather_flags(weather.with_plan(day(), 22)))
    assert "FEELS: 9C at the coldest and 23C at the warmest between 08:00 and 22:00" in flags


def test_advice_plans_for_the_evening_the_phone_reports(monkeypatch):
    async def fake_weather(lat, lon, d):
        return day()
    async def no_model(*a, **kw):
        return None
    monkeypatch.setattr(srv.weather, "fetch_weather", fake_weather)
    monkeypatch.setattr(llm, "_chat", no_model)
    c = TestClient(srv.app)
    plain = c.post("/advice", json={"lat": 40.3, "lon": -74.6}).json()
    late = c.post("/advice", json={"lat": 40.3, "lon": -74.6, "outUntil": 22}).json()
    assert plain["planTemp"] == 10 and late["planTemp"] == 9
    assert late["peakTemp"] == 23
    assert late["weather"]["planUntil"] == 22, "the phone shows what the day was planned for"
    assert reroll.peak_temp(late["weather"], 9) == 23


def test_every_heat_check_reads_the_felt_peak():
    """Air high 20, felt peak 16: the prompt, the validator, the style pass and the
    re-roll must all judge 16. Raised by the pre-push reviewer, 2026-10-10 — three
    of them still read the air high, so a warmth-3 trouser was swapped as too warm
    by one check and offered by another."""
    import style
    from picks import Prefs, _index
    cool = day(hours=[[8, 12.0, 10.0], [14, 20.0, 16.0], [19, 14.0, 12.0]])
    w = weather.with_plan(cool)
    assert w["planHi"] == 16 and w["hi"] == 20       # 20 felt as 16: within the 4-colder bound
    plan = llm._plan_temp(w)
    assert llm._peak_temp(w, plan) == reroll.peak_temp(w, plan) == 16
    assert style.ctx_of(w, _index([]), Prefs()).peak == 16


def _kotlin_video_pattern():
    """The phone's own pattern, lifted out of EveningOut.kt so this suite runs the
    real thing rather than a copy of it (no Kotlin toolchain on this box)."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "app" / "android" / "app" / "src" / "main" / "java"
           / "com" / "korety" / "outfitadvisor" / "EveningOut.kt").read_text()
    body = src[src.index("private val VIDEO = Regex("):]
    body = body[:body.index("RegexOption")]
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    return re.compile("".join(p.encode().decode("unicode_escape") for p in parts), re.I)


def test_a_place_with_a_map_link_is_still_a_night_out():
    """Only a conferencing service or a bare 'online' means the event is not out.
    Raised by the pre-push reviewer, 2026-10-10."""
    video = _kotlin_video_pattern()
    for out in ("Blue Note, 131 W 3rd St https://maps.app.goo.gl/abc", "Carnegie Hall",
                "Dinner at Joe's https://joes.example.com", "Phone shop, 5th Ave"):
        assert not video.search(out), out
    for online in ("https://us02web.zoom.us/j/123", "Microsoft Teams Meeting https://teams.microsoft.com/l/x",
                   "meet.google.com/abc-defg-hij", "Online", " virtual ", "Zoom"):
        assert video.search(online), online
