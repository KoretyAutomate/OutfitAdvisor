"""
engine.py — rule-based outfit engine. JS twin: recommend() in app/www/index.html — change them together.

Pure function: recommend(weather, gender, style) -> outfit dict.
Same logic as the JS so the app's offline fallback and the server agree.
Used for the structured `outfit{}` in the response and as the LLM-failure fallback.
"""

import math


def pick(g: str, man: str, woman: str, neutral: str) -> str:
    return man if g == "man" else woman if g == "woman" else neutral


# Temperature fields the personal calibration shifts. JS twin: TEMP_KEYS in index.html.
_TEMP_KEYS = ("lo", "hi", "feelsLo", "feelsHi", "morning", "midday", "evening")


def apply_temp_offset(w: dict, offset: float) -> dict:
    """Return a COPY of the weather with the user's thermal calibration applied.

    `offset` is ADDED to the temperatures the recommender sees: a user who reported
    feeling too warm gets a positive offset, the engine/LLM think it is warmer than
    it is, and they dress the user lighter. Getting this sign backwards is a silent
    failure, hence the explicit note here and in PLAN.md.

    Only temperatures move. rain/wind/code/isRain/isSnow are not thermal preference,
    and `swing` (= hi - lo) is invariant under a uniform shift, so it is left alone.

    The caller must keep the ORIGINAL weather for display — the app must never show
    a temperature that is not the real forecast.
    JS twin: applyTempOffset() in app/www/index.html — change them together.
    """
    if not offset:
        return w
    out = dict(w)
    for k in _TEMP_KEYS:
        v = out.get(k)
        if v is not None:
            # floor(x + 0.5), NOT round(). Python's round() is banker's rounding
            # (round-half-to-EVEN) while JS Math.round() is half-UP, so the twins
            # disagree on exact .5 values — and .5 is reachable: five "a bit warm"
            # taps give offset 1.5, which on an integer 10C morning yields 10 here
            # and 11 in the app. That is a different outfit at a threshold, from
            # the same input, depending on whether the DGX was reachable.
            out[k] = math.floor(v + offset + 0.5)
    return out


def _is_wet(w: dict) -> bool:
    """Rain heavy enough to drive the waterproof outer + footwear. Snow is checked
    separately by callers because it outranks this."""
    return bool(w["isRain"]) or w["rain"] >= 50


def _inner(t: float, gender: str) -> str:
    # always worn — user feedback 2026-07-15
    if t >= 24:
        return "Sweat-wicking breathable inner (AIRism-type)"
    if t >= 15:
        return pick(
            gender,
            "Light cotton undershirt",
            "Light inner camisole or undershirt (worn under the top)",
            "Light cotton undershirt",
        )
    if t >= 5:
        return "Warm inner (Heattech-type)"
    return "Heavyweight thermal inner"


def _base(t: float, gender: str) -> str:
    if t >= 26:
        return pick(
            gender, "Breathable cotton/linen tee", "Light camisole or linen blouse", "Lightweight breathable tee"
        )
    if t >= 18:
        return pick(gender, "Cotton T-shirt", "Short-sleeve top or light blouse", "Cotton T-shirt")
    if t >= 10:
        return pick(gender, "Long-sleeve shirt", "Long-sleeve top", "Long-sleeve shirt")
    return pick(gender, "Thermal / merino base layer", "Thermal or merino base layer", "Thermal base layer")


def _mid(t: float, gender: str) -> str:
    if t >= 22:
        return "None needed"
    if t >= 15:
        return pick(gender, "Light overshirt or thin knit", "Light cardigan or knit", "Light layer / thin knit")
    if t >= 7:
        return pick(gender, "Wool sweater or fleece", "Sweater or fleece", "Wool sweater or fleece")
    return pick(
        gender,
        "Heavy knit + insulating mid-layer",
        "Heavy knit + insulating layer",
        "Heavy knit / insulating layer",
    )


def _outer(t: float, w: dict, gender: str) -> str:
    if w["isSnow"]:
        outer = "Insulated waterproof parka"
    elif _is_wet(w):
        outer = pick(gender, "Waterproof shell / trench", "Waterproof coat or trench", "Waterproof shell")
    elif t >= 24:
        outer = "None — but pack a thin layer for AC indoors"
    elif t >= 16:
        outer = pick(gender, "Light jacket or blazer", "Light jacket or trench", "Light jacket")
    elif t >= 8:
        outer = pick(gender, "Wool coat or padded jacket", "Wool coat or padded jacket", "Insulated jacket")
    else:
        outer = pick(gender, "Heavy winter coat / down", "Down coat or heavy wool coat", "Heavy winter coat")
    # garments that are already wind-stopping must not be labelled twice
    if w["wind"] >= 8 and not any(k in outer.lower() for k in ("waterproof", "shell", "parka", "down")):
        outer += " (windproof)"
    return outer


def _bottoms(t: float, gender: str, style: str) -> str:
    if style == "active":  # overrides every temperature band
        return "Stretch / technical trousers"
    if t >= 26:
        return pick(gender, "Light chinos or shorts", "Skirt, dress, or light trousers", "Shorts or light trousers")
    if t >= 16:
        return pick(gender, "Chinos or jeans", "Jeans, trousers, or midi skirt + tights", "Chinos or jeans")
    if t >= 6:
        return pick(
            gender, "Jeans or wool trousers", "Trousers or jeans (consider thermal tights)", "Warm trousers or jeans"
        )
    return pick(
        gender,
        "Lined trousers + base layer",
        "Thermal-lined trousers or thick tights",
        "Insulated / lined trousers",
    )


def _footwear(t: float, w: dict, gender: str, style: str) -> str:
    if w["isSnow"]:
        return "Insulated waterproof boots"
    if _is_wet(w):
        return "Waterproof boots or shoes"
    if t >= 24:
        return pick(gender, "Loafers or breathable sneakers", "Sandals or breathable flats", "Breathable sneakers")
    if t >= 10:
        return "Leather shoes / ankle boots" if style == "smart" else "Sneakers or casual shoes"
    return "Insulated boots"


def _accessories(t: float, w: dict) -> str:
    acc = []
    if t < 5:
        acc.append("hat, gloves & scarf")
    elif t < 10:
        acc.append("scarf")
    if w["rain"] >= 40 or w["isRain"]:  # lower bar than the waterproof outer
        acc.append("umbrella")
    if w["hi"] >= 24 and w["code"] in (0, 1, 2):
        acc.append("sunglasses")
    if w["swing"] >= 10:
        acc.append("a packable layer for the temp swing")
    if not acc:
        return "None essential"
    text = ", ".join(acc)
    return text[0].upper() + text[1:]


def _tip(w: dict) -> str:
    if w["swing"] >= 10:
        # morning/midday can be None (hourly index miss) — don't print "None° → None°"
        span = (
            f" ({w['morning']}° → {w['midday']}°)"
            if w.get("morning") is not None and w.get("midday") is not None
            else ""
        )
        return (
            f"Big {w['swing']}° swing today{span}. Dress in layers you can shed "
            "by midday and add back in the evening."
        )
    if _is_wet(w):
        return f"Rain likely ({w['rain']}%). Prioritise the waterproof outer + footwear."
    if w["wind"] >= 8:
        return f"Strong wind ({w['wind']} m/s) — a windproof outer makes a real difference."
    if w["hi"] >= 28:
        return "Hot day — favour breathable, light-coloured fabrics and stay hydrated."
    return "Comfortable conditions — the layers above keep you flexible through the day."


def recommend(w: dict, gender: str, style: str) -> dict:
    """Assemble the 6+1 outfit. Each layer is its own function above, in the same
    order as the blocks of the JS twin in app/www/index.html — keep them aligned.

    Behaviour is pinned by server/tests/test_engine_characterization.py; change a
    threshold here and the golden diff shows exactly which outfits move."""
    # plan for the cooler part of the day (morning), falling back to the midpoint
    t = w["morning"] if w.get("morning") is not None else w["lo"] + (w["hi"] - w["lo"]) / 2
    return {
        "inner": _inner(t, gender),
        "base": _base(t, gender),
        "mid": _mid(t, gender),
        "outer": _outer(t, w, gender),
        "bottoms": _bottoms(t, gender, style),
        "footwear": _footwear(t, w, gender, style),
        "accessories": _accessories(t, w),
        "tip": _tip(w),
    }


def outfit_to_bullets(o: dict) -> str:
    """Format the structured outfit as 6+1 bullets — the LLM-failure fallback text."""
    return (
        f"• Inner: {o['inner']}\n"
        f"• Base: {o['base']}\n"
        f"• Mid: {o['mid']}\n"
        f"• Outer: {o['outer']}\n"
        f"• Bottoms: {o['bottoms']}\n"
        f"• Footwear: {o['footwear']}\n"
        f"• Accessories: {o['accessories']}\n\n"
        f"💡 {o['tip']}"
    )
