"""
app.py — Outfit Advisor DGX server (stateless).

POST /advice   {lat, lon, gender, style, day?, closet?} -> weather + outfit_text
               + structured outfit (+ closetUsed when closet[] was sent)
POST /packing  {lat, lon, start, end, type, styles[], closet?}
                                                        -> per-day trip forecast (or
               climate normals beyond the horizon) + a packing list from the closet
POST /classify {imageB64}                               -> clothing item metadata
GET  /health                                            -> {ok, vllm}

Privacy invariant: coordinates AND closet photos are NEVER written to disk or
logs. They live only as request-scoped locals and are discarded. The closet
itself lives on the phone; this server stays stateless. We log only coarse
outcome + timing — never lat/lon, never image bytes, never item labels.

For /packing the invariant extends further: the calendar event's title, notes,
attendees and location STRING never reach this server at all. The phone resolves
the destination to coordinates itself, so the server cannot learn the destination
by name. Trip DATES are also never logged — a real date range plus a destination
is identifying in a way /advice's day=0|1 never was.

Injection posture: gender/style are Literal vocabularies. Closet labels/colors
are user-editable free text that flows into the LLM prompt — they are length-
capped and character-sanitized here, and rendered inside a fenced data block
the prompt marks as untrusted (plan amendment 1, 2026-07-09).

Run (tailnet-bound — bind the Tailscale IP, NOT 0.0.0.0, so the LAN never sees it):
    uvicorn app:app --host 100.112.171.54 --port 8787 --no-access-log
"""
import base64
import datetime as dt
import logging
import re
import time
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

import engine
import llm
import weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("outfit")

# PRIVACY: httpx logs each outbound request URL at INFO level — and the Open-Meteo
# URL contains lat/lon. Silence it so coordinates can never reach the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(title="Outfit Advisor", version="0.1")

# The Capacitor WebView serves the app from https://localhost (Android) /
# capacitor://localhost (iOS); its POST preflight needs these CORS headers or the
# browser layer rejects the response. Native callers (WakeActivity) ignore CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost", "capacitor://localhost"],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


# Free text destined for the LLM prompt: keep word chars (incl. CJK), spaces,
# and a few naming chars. Kills backticks, braces, newlines — the fence-escape
# and JSON-confusion vectors.
_TEXT_OK = re.compile(r"[^\w \-'&/()+.,]", flags=re.UNICODE)


def _clean(s: str, max_len: int) -> str:
    return _TEXT_OK.sub("", s)[:max_len].strip()


class ClosetItem(BaseModel):
    id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")
    label: str = Field(..., min_length=1, max_length=60)
    category: Literal["inner", "base", "mid", "outer", "bottoms", "footwear", "accessories"]
    colors: list[str] = Field(default_factory=list, max_length=3)
    warmth: int = Field(3, ge=1, le=5)
    formality: list[Literal["casual", "smart", "active"]] = Field(default_factory=list)
    waterproof: bool = False
    availableCount: int = Field(1, ge=1, le=99)

    @field_validator("label")
    @classmethod
    def _san_label(cls, v: str) -> str:
        v = _clean(v, 60)
        if not v:
            raise ValueError("label empty after sanitization")
        return v

    @field_validator("colors")
    @classmethod
    def _san_colors(cls, v: list[str]) -> list[str]:
        return [c for c in (_clean(x, 20) for x in v) if c]


class AdviceRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    # Closed vocabularies — free strings would flow into the LLM prompt (injection)
    # and the engine; anything else is a 422 before it touches either.
    gender: Literal["man", "woman", "neutral"] = "neutral"
    style: Literal["casual", "smart", "active"] = "casual"
    day: int = Field(0, ge=0, le=1)  # 0 = today (morning push), 1 = tomorrow
    # Phone-side closet: AVAILABLE items only (rotation already applied on the
    # phone — items in the laundry are never sent). Absent/empty = generic advice.
    closet: list[ClosetItem] | None = Field(None, max_length=100)


class ClassifyRequest(BaseModel):
    # ~3MB of raw image, base64-encoded (~4M chars). The phone downscales to
    # ~512px first, so a real request is far smaller.
    imageB64: str = Field(..., min_length=100, max_length=4_200_000)


@app.get("/health")
async def health():
    vllm_ok = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://127.0.0.1:8000/v1/models")
            vllm_ok = r.status_code == 200
    except Exception:
        vllm_ok = False
    return {"ok": True, "vllm": vllm_ok}


@app.post("/advice")
async def advice(req: AdviceRequest):
    t0 = time.monotonic()
    # NB: req.lat / req.lon are used here but intentionally NEVER logged.
    try:
        w = await weather.fetch_weather(req.lat, req.lon, req.day)
    except Exception as e:
        # PRIVACY: an httpx error message embeds the full Open-Meteo URL — lat/lon
        # included. Letting it propagate would put coordinates in the 500 traceback.
        # Log only the exception TYPE and return a coordinate-free error.
        log.warning("advice failed: weather fetch error (%s)", type(e).__name__)
        raise HTTPException(status_code=503, detail="weather unavailable")
    outfit = engine.recommend(w, req.gender, req.style)

    closet_used = False
    picks = None
    text = None
    if req.closet:
        items = [i.model_dump() for i in req.closet]
        result = await llm.closet_outfit(w, req.gender, req.style, items)
        if result is not None:
            text = result["text"]
            closet_used = True
            # Structured outfit mirrors the validated picks so the notification
            # renders the ACTUAL items. A null pick keeps the engine's GENERIC
            # recommendation (user feedback 2026-07-15): "None" told a user with
            # three registered shirts nothing about what bottoms to wear. The
            # engine value is also honest when the weather nulls a slot — it
            # already says "None needed" in heat.
            by_id = {i["id"]: i for i in items}
            for slot, item_id in result["picks"].items():
                if item_id:
                    outfit[slot] = by_id[item_id]["label"]
            # IDs are already validated against the sent closet — echo them so
            # the app can wear-log the exact items (plan amendment 2).
            picks = result["picks"]
        # result None -> honest generic fallback below, closetUsed stays False
        # (plan amendments 3 & 9: never mislabel non-closet advice).

    source = "llm"
    if not text:
        text = await llm.outfit_text(w, req.gender, req.style)
    if not text:
        text = engine.outfit_to_bullets(outfit)
        source = "rule-engine"

    dt = round(time.monotonic() - t0, 2)
    # Coarse, coordinate-free log line (closet size only — never item content).
    log.info("advice ok day=%s tz=%s lo=%s hi=%s source=%s closet=%s/%s %.2fs",
             req.day, w.get("timezone"), w["lo"], w["hi"], source,
             int(closet_used), len(req.closet or []), dt)

    return {"weather": w, "outfit": outfit, "outfit_text": text, "source": source,
            "closetUsed": closet_used, "picks": picks}


class PackingRequest(BaseModel):
    """Trip packing. NOTE what is deliberately ABSENT: the calendar event's title,
    notes, attendees, and location STRING. The phone resolves the destination to
    coordinates at confirm time and sends only those. The server never learns where
    the user is going by name, and cannot — that is the point (see PLAN.md Trips /
    privacy posture)."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    start: dt.date
    end: dt.date
    type: Literal["business", "vacation"] = "vacation"
    gender: Literal["man", "woman", "neutral"] = "neutral"
    # A business trip is smart for meetings AND casual for evenings — one scalar
    # cannot express that, so packing takes a SET of registers (plan amendment T-3).
    styles: list[Literal["casual", "smart", "active"]] = Field(
        default_factory=lambda: ["casual"], min_length=1, max_length=3)
    closet: list[ClosetItem] | None = Field(None, max_length=100)

    @field_validator("end")
    @classmethod
    def _order(cls, v: dt.date, info) -> dt.date:
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end is before start")
        if start and (v - start).days > 30:
            raise ValueError("trip longer than 30 days")
        return v


# How many of each category a trip actually needs, given its length. Only inner,
# base and bottoms scale with duration; you re-wear a coat. Used to catch a SHORTFALL
# the LLM would otherwise hide by silently packing fewer (plan amendment T-4).
def _needed(category: str, n_days: int) -> int:
    if category in ("inner", "base"):
        return n_days + 1
    if category == "bottoms":
        return max(1, -(-n_days // 3))   # ceil(n/3)
    return 1


@app.post("/packing")
async def packing(req: PackingRequest):
    t0 = time.monotonic()
    today = dt.date.today()
    if req.start < today:
        raise HTTPException(status_code=422, detail="trip has already started")

    horizon = today + dt.timedelta(days=weather.FORECAST_HORIZON_DAYS)
    truncated = False
    try:
        if req.start > horizon:
            # Beyond the forecast window entirely -> honest climate normals.
            wx = await weather.fetch_normals(req.lat, req.lon,
                                             req.start.isoformat(), req.end.isoformat())
        else:
            # Inside the window. A long trip may run PAST the horizon — clamp the
            # end and say so, rather than letting Open-Meteo 400 the whole request.
            end = min(req.end, horizon)
            truncated = end < req.end
            wx = await weather.fetch_range(req.lat, req.lon,
                                           req.start.isoformat(), end.isoformat())
    except Exception as e:
        # PRIVACY: the httpx error text embeds the Open-Meteo URL — lat/lon and the
        # trip dates included. Log the TYPE only, exactly as /advice does.
        log.warning("packing failed: weather fetch error (%s)", type(e).__name__)
        raise HTTPException(status_code=503, detail="weather unavailable")

    days, summary = wx["days"], wx["summary"]
    n = summary["nDays"]

    pack, gaps, text, closet_used = [], [], None, False
    if req.closet:
        items = [i.model_dump() for i in req.closet]
        result = await llm.packing_list(days, summary, req.gender, list(req.styles),
                                        req.type, items)
        if result is not None:
            pack, gaps, text = result["pack"], result["gaps"], result["text"]
            closet_used = True

            # Capacity reconciliation. The LLM cannot pack more than the user owns
            # (llm.py clamps qty), so a shortfall shows up as SILENCE — a 14-day
            # trip quietly packing 8 tops. Surface it as a real gap.
            #
            # Key off what the wardrobe HAS, not off what the model chose to pack:
            # a shortfall is a fact about the closet. (First cut gated this on
            # `have <= got` and stayed silent whenever the model under-packed —
            # exactly the case the check exists to catch. Caught by T1 test 4.)
            for cat in ("inner", "base", "bottoms"):
                want = _needed(cat, n)
                have = sum(i["availableCount"] for i in items if i["category"] == cat)
                if have < want:
                    gaps.append({
                        "category": cat,
                        # have==0 means the closet has NONE registered — a laundry
                        # day can't produce items you don't own, so say buy/register.
                        "need": (f"none in your closet yet — bring/buy ~{want}"
                                 if have == 0 else
                                 f"only {have} of ~{want} clean — plan a laundry day"),
                    })
        # result None -> honest generic fallback below, closetUsed stays False.

    if not text:
        # Generic packing advice: dress the trip's WORST case (coldest low, wettest
        # day) via the existing rule engine, so the user still gets something useful.
        worst = {
            "morning": None, "lo": summary["loMin"], "hi": summary["hiMax"],
            "swing": summary["swing"], "rain": max(d["rain"] for d in days),
            "wind": summary["windMax"], "isSnow": summary["isSnow"],
            "isRain": summary["isRain"],
            "code": max(days, key=lambda d: d["rain"])["code"],
        }
        text = engine.outfit_to_bullets(engine.recommend(worst, req.gender,
                                                         req.styles[0]))

    dt_s = round(time.monotonic() - t0, 2)
    # Coarse log ONLY. No coords (as /advice). And no DATES — a real date range plus
    # a destination is itself identifying, unlike /advice's day=0|1.
    log.info("packing ok n=%s mode=%s closet=%s/%s gaps=%s %.2fs",
             n, summary["mode"], int(closet_used), len(req.closet or []),
             len(gaps), dt_s)

    return {"trip": {"nDays": n, "type": req.type, "styles": req.styles,
                     "truncated": truncated},
            "forecast": {"mode": summary["mode"], "days": days, "summary": summary},
            "pack": pack, "gaps": gaps, "packing_text": text,
            "closetUsed": closet_used}


@app.post("/classify")
async def classify(req: ClassifyRequest):
    t0 = time.monotonic()
    # Tolerate a data-URI prefix; validate it IS base64 before shipping to vLLM.
    b64 = req.imageB64.split(",", 1)[-1].strip()
    try:
        base64.b64decode(b64[:400], validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="imageB64 is not valid base64")

    raw = await llm.classify_image(b64)
    if raw is None:
        log.warning("classify failed: LLM unavailable or non-JSON (%.2fs)",
                    time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="classification unavailable")

    # Re-validate the LLM's output through the same schema as incoming closet
    # items — one sanitization path for both directions.
    try:
        item = ClosetItem(
            id="pending-0000",  # phone assigns the real uuid on save
            label=str(raw.get("label") or ""),
            category=raw.get("category"),
            colors=[str(c) for c in raw.get("colors") or [] if str(c).strip()][:3],
            warmth=int(raw.get("warmth") or 3),
            formality=[f for f in (raw.get("formality") or [])
                       if f in ("casual", "smart", "active")],
            waterproof=bool(raw.get("waterproof")),
        )
    except Exception:
        log.warning("classify failed: LLM output failed validation (%.2fs)",
                    time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="classification unusable")

    # Coarse log: outcome + timing only — never the image, never the label.
    log.info("classify ok %.2fs", time.monotonic() - t0)
    d = item.model_dump()
    d.pop("id")
    d.pop("availableCount")
    return d
