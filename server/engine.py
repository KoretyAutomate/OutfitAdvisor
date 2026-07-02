"""
engine.py — rule-based outfit engine. JS twin: recommend() in app/www/index.html — change them together.

Pure function: recommend(weather, gender, style) -> outfit dict.
Same logic as the JS so the app's offline fallback and the server agree.
Used for the structured `outfit{}` in the response and as the LLM-failure fallback.
"""


def pick(g: str, man: str, woman: str, neutral: str) -> str:
    return man if g == "man" else woman if g == "woman" else neutral


def recommend(w: dict, gender: str, style: str) -> dict:
    # plan for the cooler part of the day (morning), falling back to the midpoint
    t = w["morning"] if w.get("morning") is not None else w["lo"] + (w["hi"] - w["lo"]) / 2
    o: dict = {}

    # ── base layer ──
    if t >= 26:
        o["base"] = pick(gender, "Breathable cotton/linen tee", "Light camisole or linen blouse", "Lightweight breathable tee")
    elif t >= 18:
        o["base"] = pick(gender, "Cotton T-shirt", "Short-sleeve top or light blouse", "Cotton T-shirt")
    elif t >= 10:
        o["base"] = pick(gender, "Long-sleeve shirt", "Long-sleeve top", "Long-sleeve shirt")
    else:
        o["base"] = pick(gender, "Thermal / merino base layer", "Thermal or merino base layer", "Thermal base layer")

    # ── mid layer ──
    if t >= 22:
        o["mid"] = "None needed"
    elif t >= 15:
        o["mid"] = pick(gender, "Light overshirt or thin knit", "Light cardigan or knit", "Light layer / thin knit")
    elif t >= 7:
        o["mid"] = pick(gender, "Wool sweater or fleece", "Sweater or fleece", "Wool sweater or fleece")
    else:
        o["mid"] = pick(gender, "Heavy knit + insulating mid-layer", "Heavy knit + insulating layer", "Heavy knit / insulating layer")

    # ── outer layer ──
    if w["isSnow"]:
        o["outer"] = "Insulated waterproof parka"
    elif w["isRain"] or w["rain"] >= 50:
        o["outer"] = pick(gender, "Waterproof shell / trench", "Waterproof coat or trench", "Waterproof shell")
    elif t >= 24:
        o["outer"] = "None — but pack a thin layer for AC indoors"
    elif t >= 16:
        o["outer"] = pick(gender, "Light jacket or blazer", "Light jacket or trench", "Light jacket")
    elif t >= 8:
        o["outer"] = pick(gender, "Wool coat or padded jacket", "Wool coat or padded jacket", "Insulated jacket")
    else:
        o["outer"] = pick(gender, "Heavy winter coat / down", "Down coat or heavy wool coat", "Heavy winter coat")
    if w["wind"] >= 8 and not any(k in o["outer"].lower() for k in ("waterproof", "shell", "parka", "down")):
        o["outer"] += " (windproof)"

    # ── bottoms ──
    if t >= 26:
        o["bottoms"] = pick(gender, "Light chinos or shorts", "Skirt, dress, or light trousers", "Shorts or light trousers")
    elif t >= 16:
        o["bottoms"] = pick(gender, "Chinos or jeans", "Jeans, trousers, or midi skirt + tights", "Chinos or jeans")
    elif t >= 6:
        o["bottoms"] = pick(gender, "Jeans or wool trousers", "Trousers or jeans (consider thermal tights)", "Warm trousers or jeans")
    else:
        o["bottoms"] = pick(gender, "Lined trousers + base layer", "Thermal-lined trousers or thick tights", "Insulated / lined trousers")
    if style == "active":
        o["bottoms"] = "Stretch / technical trousers"

    # ── footwear ──
    if w["isSnow"]:
        o["footwear"] = "Insulated waterproof boots"
    elif w["isRain"] or w["rain"] >= 50:
        o["footwear"] = "Waterproof boots or shoes"
    elif t >= 24:
        o["footwear"] = pick(gender, "Loafers or breathable sneakers", "Sandals or breathable flats", "Breathable sneakers")
    elif t >= 10:
        o["footwear"] = "Leather shoes / ankle boots" if style == "smart" else "Sneakers or casual shoes"
    else:
        o["footwear"] = "Insulated boots"

    # ── accessories ──
    acc = []
    if t < 5:
        acc.append("hat, gloves & scarf")
    elif t < 10:
        acc.append("scarf")
    if w["rain"] >= 40 or w["isRain"]:
        acc.append("umbrella")
    if w["hi"] >= 24 and w["code"] in (0, 1, 2):
        acc.append("sunglasses")
    if w["swing"] >= 10:
        acc.append("a packable layer for the temp swing")
    acc_text = ", ".join(acc)
    o["accessories"] = (acc_text[0].upper() + acc_text[1:]) if acc else "None essential"

    # ── tip ──
    if w["swing"] >= 10:
        # morning/midday can be None (hourly index miss) — don't print "None° → None°"
        span = (f" ({w['morning']}° → {w['midday']}°)"
                if w.get("morning") is not None and w.get("midday") is not None else "")
        o["tip"] = (f"Big {w['swing']}° swing today{span}. "
                    "Dress in layers you can shed by midday and add back in the evening.")
    elif w["isRain"] or w["rain"] >= 50:
        o["tip"] = f"Rain likely ({w['rain']}%). Prioritise the waterproof outer + footwear."
    elif w["wind"] >= 8:
        o["tip"] = f"Strong wind ({w['wind']} m/s) — a windproof outer makes a real difference."
    elif w["hi"] >= 28:
        o["tip"] = "Hot day — favour breathable, light-coloured fabrics and stay hydrated."
    else:
        o["tip"] = "Comfortable conditions — the layers above keep you flexible through the day."

    return o


def outfit_to_bullets(o: dict) -> str:
    """Format the structured outfit as 5+1 bullets — the LLM-failure fallback text."""
    return (
        f"• Base: {o['base']}\n"
        f"• Mid: {o['mid']}\n"
        f"• Outer: {o['outer']}\n"
        f"• Bottoms: {o['bottoms']}\n"
        f"• Footwear: {o['footwear']}\n"
        f"• Accessories: {o['accessories']}\n\n"
        f"💡 {o['tip']}"
    )
