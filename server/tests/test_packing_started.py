"""A trip already under way can still get its packing list (user, 2026-09-10, from
Tokyo). The suitcase is declared from that list, and "already started" had shut
the only door to it once away from home. Only a trip already OVER is refused."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import app as srv
import llm

ANCH = {"warmthScale": "home", "warmthAnchors": [0.7, 12.9, 25.6]}
TEE = {"id": "itm-00000010", "label": "tee", "category": "base", "group": "tops", "type": "t_shirt",
       "roles": ["base"], "colors": ["white"], "warmth": 1, "formality": ["casual"], "waterproof": False,
       "availableCount": 3, **ANCH}
CHINOS = {"id": "itm-00000001", "label": "chinos", "category": "bottoms", "group": "bottoms", "type": "chinos",
          "roles": ["bottoms"], "colors": ["navy"], "warmth": 2, "formality": ["casual"], "waterproof": False,
          "availableCount": 2, **ANCH}


@pytest.fixture
def api(monkeypatch):
    seen: dict = {}

    async def fake_range(lat, lon, start, end):
        seen["range"] = (start, end)
        d0 = dt.date.fromisoformat(start)
        n = (dt.date.fromisoformat(end) - d0).days + 1
        days = [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "lo": 19, "hi": 22, "desc": "Cloudy",
                 "rain": 20, "wind": 3, "code": 3, "emoji": "☁️"} for i in range(n)]
        return {"days": days, "summary": {"nDays": n, "loMin": 19, "hiMax": 22, "swing": 3, "windMax": 3,
                                          "isSnow": False, "isRain": False, "rainDays": 0, "mode": "forecast"}}

    async def fake_chat(messages, max_tokens, timeout=45, **kw):
        seen.setdefault("prompts", []).append(messages[0]["content"])
        return ('{"pack": [{"id": "itm-00000010", "qty": 2, "why": "a"}, {"id": "itm-00000001", "qty": 1, "why": "b"}],'
                ' "gaps": [], "bullets": ["Tops: tees"], "plan": [{"base": "itm-00000010", "bottoms": "itm-00000001"}],'
                ' "tip": "x"}')

    monkeypatch.setattr(srv.weather, "fetch_range", fake_range)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    c = TestClient(srv.app)
    c.seen = seen
    return c


def _req(start_off, end_off, today_off=0):
    today = dt.date.today()
    return {"lat": 35.68, "lon": 139.77, "start": (today + dt.timedelta(days=start_off)).isoformat(),
            "end": (today + dt.timedelta(days=end_off)).isoformat(), "type": "business", "gender": "man",
            "styles": ["casual"], "closet": [TEE, CHINOS], "travelKm": 10800,
            "today": (today + dt.timedelta(days=today_off)).isoformat()}


def test_a_trip_under_way_is_packed_from_today(api):
    d = api.post("/packing", json=_req(-3, 4)).json()
    assert d["trip"]["started"] is True and d["trip"]["nDays"] == 5
    assert api.seen["range"][0] == dt.date.today().isoformat(), "the weather starts today, not three days ago"
    assert d["closetUsed"] is True and d["pack"]


def test_once_there_only_the_journey_home_remains(api):
    d = api.post("/packing", json=_req(-3, 4)).json()
    assert d["travel"] is True, "the trip still involves a cabin — the flight home"
    p = api.seen["prompts"][0]
    assert "TRAVEL DAYS: day 1" not in p and "journey home" in p
    assert d["plan"] and d["plan"][0]["travel"] is False, "day 1 is an ordinary morning there"


def test_the_travellers_date_wins_when_it_is_a_day_ahead(api):
    """A Tokyo morning is still last night on this server. The remaining trip runs
    from THEIR today (the reviewer's case)."""
    d = api.post("/packing", json=_req(-3, 4, today_off=1)).json()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    assert api.seen["range"][0] == tomorrow
    assert d["trip"]["nDays"] == 4


def test_an_implausible_date_is_ignored(api):
    d = api.post("/packing", json=_req(-3, 4, today_off=9)).json()
    assert api.seen["range"][0] == dt.date.today().isoformat() and d["trip"]["nDays"] == 5


def test_a_trip_starting_today_is_not_started(api):
    d = api.post("/packing", json=_req(0, 3)).json()
    assert d["trip"]["started"] is False and d["travel"] is True


def test_a_trip_already_over_is_refused_with_its_own_words(api):
    r = api.post("/packing", json=_req(-9, -1))
    assert r.status_code == 422 and r.json()["detail"] == "trip is over"
