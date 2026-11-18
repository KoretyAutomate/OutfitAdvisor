"""What I wore, end to end through /advice (2026-11-14): the same closet and weather,
with and without the phone's outfit log, on a day off and an office day. The chooser
is a fake that picks the SECOND outfit it is offered whenever there is one — the
model's eye going its own way — so what is pinned is what it is allowed to choose."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import app as srv
import fake_model
from wardrobe_fixtures import CARDI, JACKET, JEANS, OXFORD, POLO, SNEAK, TEE, UNDER, g, weather

GREY_TEE = g("greytee01", "grey crew-neck T-shirt", "tops", "t_shirt", ["base"], 1, colors=["grey"])
WHITE_OX = g("whiteox01", "white oxford shirt", "tops", "shirt", ["base", "mid", "outer"], 2, colors=["white"])
MERINO = g("merino001", "navy merino crew sweater", "tops", "sweater", ["base", "mid", "outer"], 3)
CHINOS = g("chinos001", "navy chinos", "bottoms", "trousers", ["bottoms"], 3, formality=["casual", "smart"])
GREY_TR = g("greytr001", "grey wool trousers", "bottoms", "trousers", ["bottoms"], 3, colors=["grey"],
            formality=["smart"])
LOAFERS = g("loafers01", "brown leather loafers", "footwear", "loafers", ["footwear"], 2, colors=["brown"])
DERBY = g("derby0001", "black derby shoes", "footwear", "derbies", ["footwear"], 3, colors=["black"])
CLOSET = [UNDER, TEE, GREY_TEE, POLO, OXFORD, WHITE_OX, MERINO, CARDI, JACKET, JEANS, CHINOS, GREY_TR,
          SNEAK, LOAFERS, DERBY]
TODAY = weather(15)["date"]


def ago(n):
    return (dt.date.fromisoformat(TODAY) - dt.timedelta(days=n)).isoformat()


def entry(n, occasion, temp, **picks):
    return {"day": ago(n), "occasion": occasion, "temp": temp, "peak": temp + 5, "rain": 0, "wind": 2,
            "picks": {s: i["id"] for s, i in picks.items()}, "chose": ["base"], "at": n}


OFF_LOG = [entry(n, "off", 14 + n % 3, base=TEE, mid=CARDI, bottoms=CHINOS, footwear=SNEAK) for n in range(2, 9)]
OFFICE_LOG = [entry(n, "office", 14 + n % 3, base=WHITE_OX, mid=MERINO, bottoms=GREY_TR, footwear=DERBY)
              for n in range(9, 16)]


@pytest.fixture
def api(monkeypatch):
    async def mild(lat, lon, day):
        return weather(15, 20)
    monkeypatch.setattr(srv.weather, "fetch_weather", mild)
    monkeypatch.setenv("OUTFIT_ENGINE", "funnel")
    return TestClient(srv.app)


def advise(api, monkeypatch, occasion, worn):
    fake_model.install(monkeypatch, [], choices=[fake_model.choice(2), fake_model.choice(1)])
    body = {"lat": 1, "lon": 1, "occasion": occasion, "style": "smart" if occasion == "office" else "casual",
            "gender": "man", "closet": CLOSET, **({"worn": worn} if worn else {})}
    r = api.post("/advice", json=body)
    assert r.status_code == 200, r.text
    return r.json()["picks"]


def names(picks):
    by = {i["id"]: i["label"] for i in CLOSET}
    return {s: by[i] for s, i in picks.items() if i}


def test_a_day_off_follows_what_they_wore_on_days_like_it(api, monkeypatch):
    plain = advise(api, monkeypatch, "off", None)
    mine = advise(api, monkeypatch, "off", OFF_LOG)
    print("\nday off, no log:  ", names(plain))
    print("day off, with log:", names(mine))
    assert plain["base"] != TEE["id"] or plain["bottoms"] != CHINOS["id"], "the log has something to change"
    assert mine["base"] == TEE["id"] and mine["bottoms"] == CHINOS["id"], "what they wear on days off like this"


def test_an_office_day_follows_their_office_days_not_their_weekends(api, monkeypatch):
    plain = advise(api, monkeypatch, "office", None)
    mine = advise(api, monkeypatch, "office", OFFICE_LOG + OFF_LOG)
    print("\noffice, no log:   ", names(plain))
    print("office, with log: ", names(mine))
    assert mine["base"] == WHITE_OX["id"] and mine["bottoms"] == GREY_TR["id"]
    assert mine["base"] != TEE["id"], "the weekend log does not dress the office"


def test_a_log_from_much_warmer_days_changes_nothing(api, monkeypatch):
    hot = [{**e, "temp": 29.0} for e in OFF_LOG]
    assert advise(api, monkeypatch, "off", hot) == advise(api, monkeypatch, "off", None)
