"""Garments and days shared by the advisor's tests (2026-10-11 refactor)."""
import picks as pk
from check import Day


def g(iid, label, group, typ, roles, warmth, **kw):
    return {"id": f"itm-{iid}", "label": label, "category": roles[0], "group": group, "type": typ,
            "roles": list(roles), "colors": ["navy"], "warmth": warmth, "formality": ["casual"],
            "waterproof": False, "availableCount": 1, **kw}


UNDER = g("under0001", "grey v-neck inner", "underwear", "undershirt", ["inner"], 1)
TEE = g("tee000001", "white crew-neck T-shirt", "tops", "t_shirt", ["base"], 1, colors=["white"])
POLO = g("polo00001", "navy polo shirt", "tops", "polo", ["base", "mid", "outer"], 2)
KNIT_POLO = g("knitpolo1", "grey knit polo", "tops", "polo", ["base", "mid", "outer"], 3, colors=["grey"])
OXFORD = g("oxford001", "blue oxford shirt", "tops", "shirt", ["base", "mid", "outer"], 2, colors=["blue"])
CARDI = g("cardi0001", "charcoal cardigan", "tops", "cardigan", ["mid", "outer"], 3, colors=["charcoal"])
SWEATER = g("sweater01", "navy v-neck sweater", "tops", "sweater", ["base", "mid", "outer"], 4)
JACKET = g("jacket001", "olive field jacket", "outerwear", "jacket", ["outer"], 3, colors=["olive"])
JEANS = g("jeans0001", "blue jeans", "bottoms", "jeans", ["bottoms"], 3, colors=["blue"])
SHORTS = g("shorts001", "khaki shorts", "bottoms", "shorts", ["bottoms"], 1, colors=["khaki"])
DRESS = g("dress0001", "floral dress", "onepiece", "dress", ["base"], 2, colors=["red"])
SNEAK = g("sneaker01", "white sneakers", "footwear", "sneakers", ["footwear"], 2, colors=["white"])
BOOTS = g("snowboot1", "brown snow boots", "footwear", "boots", ["footwear"], 4, colors=["brown"],
          waterproof=True)


def weather(t, hi=None, **kw):
    hi = t + 4 if hi is None else hi
    return {"lo": t, "hi": hi, "morning": t, "midday": hi, "evening": t + 1, "feelsLo": t, "feelsHi": hi,
            "swing": hi - t, "desc": "Cloudy", "rain": 0, "wind": 2, "isRain": False, "isSnow": False,
            "code": 3, "date": "2026-10-11", "timezone": "America/New_York", **kw}


def day(t, *items, hi=None, prefs=None, **kw):
    return Day.of(weather(t, hi, **kw), pk._index(list(items)), prefs or pk.Prefs())


def ids(**slots):
    return {s: (i["id"] if i else None) for s, i in slots.items()}
