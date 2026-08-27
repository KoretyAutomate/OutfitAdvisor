"""
app.py — Outfit Advisor DGX server (stateless).

POST /advice   {lat, lon, gender, style, day?, closet?} -> weather + outfit_text
               + structured outfit (+ closetUsed when closet[] was sent)
POST /packing  {lat, lon, start, end, type, styles[], closet?}
                                                        -> per-day trip forecast (or
               climate normals beyond the horizon) + a packing list from the closet
POST /classify {imageB64}                               -> clothing item metadata
POST /triage   {title, location, nights, start, end}    -> is this calendar entry a
               trip, and which CITY (so the app stops asking the user to confirm
               every candidate; 2026-08-14)
GET  /health                                            -> {ok, vllm}
GET  /version                                           -> the published APK's build
               metadata, so the app can offer an in-app update instead of the user
               sideloading by hand (2026-07-28)
GET  /apk                                               -> that APK's bytes

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
import json
import logging
import os
import time
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

import closet as closet_llm
import engine
import llm
import rules
import shopping as shopping_llm
import vocab
import weather
from schemas import (
    AdviceRequest,
    ClosetItem,
    RuleRequest,
    ShoppingRequest,
    TriageRequest,
    _clean,
)

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
    # x-oa-client MUST be listed. A custom request header makes the WebView send a
    # CORS preflight, and a header missing from this list fails it with 400 — the
    # browser then blocks the POST, fetch() throws, and the app silently renders
    # "offline estimate". Adding the header for debugging (v1.6) therefore broke
    # every in-app advice request until 2026-08-14, while the native push, which
    # is not subject to CORS, kept working and hid it.
    allow_headers=["content-type", "x-oa-client"],
)


class ClassifyRequest(BaseModel):
    # ~3MB of raw image, base64-encoded (~4M chars). The phone downscales to
    # ~512px first, so a real request is far smaller.
    imageB64: str = Field(..., min_length=100, max_length=4_200_000)


# ---- in-app update channel (2026-07-28) -------------------------------------
# The user's pain was losing settings and closet photos on every update. That was
# never sideloading's fault — it was CI signing each build with a fresh ephemeral
# key, fixed by the persistent keystore + cert-drift gate. Same package + same key
# = Android updates in place and keeps app data, exactly like Play does.
#
# What was still missing is DELIVERY. These two endpoints let the app notice a new
# build and install it itself, so nothing leaves the tailnet and there is no Play
# account, no review, and no targetSdk upgrade.
#
# Publish a build with:  python3 server/publish_apk.py <path-to-app-debug.apk>
DIST = Path(os.environ.get("OA_DIST", Path(__file__).resolve().parent.parent / "dist"))


@app.get("/version")
async def version():
    """Metadata for the currently published APK, or 404 when none is published."""
    meta = DIST / "version.json"
    if not meta.is_file():
        raise HTTPException(status_code=404, detail="no build published")
    try:
        d = json.loads(meta.read_text())
    except Exception:
        log.warning("version.json is unreadable")
        raise HTTPException(status_code=500, detail="bad build metadata") from None
    if not (DIST / d.get("file", "")).is_file():
        log.warning("version.json points at a missing apk")
        raise HTTPException(status_code=404, detail="apk missing")
    return d


@app.get("/apk")
async def apk():
    """The published APK. The app verifies the sha256 from /version before it
    hands the file to the system installer."""
    meta = DIST / "version.json"
    if not meta.is_file():
        raise HTTPException(status_code=404, detail="no build published")
    try:
        name = json.loads(meta.read_text()).get("file", "")
    except Exception:
        raise HTTPException(status_code=500, detail="bad build metadata") from None
    # Never let the metadata escape DIST — it is local, but a path traversal here
    # would turn a config typo into an arbitrary-file read over the tailnet.
    path = (DIST / name).resolve()
    if not name or DIST.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="apk missing")
    log.info("apk served (%s)", name)
    return FileResponse(path, media_type="application/vnd.android.package-archive", filename=name)


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
async def advice(req: AdviceRequest, x_oa_client: str = Header(default="?")):
    t0 = time.monotonic()
    # NB: req.lat / req.lon are used here but intentionally NEVER logged.
    try:
        w = await weather.fetch_weather(req.lat, req.lon, req.day)
    except Exception as e:
        # PRIVACY: an httpx error message embeds the full Open-Meteo URL — lat/lon
        # included. Letting it propagate would put coordinates in the 500 traceback.
        # Log only the exception TYPE and return a coordinate-free error.
        log.warning("advice failed: weather fetch error (%s)", type(e).__name__)
        raise HTTPException(status_code=503, detail="weather unavailable") from None
    # Personal calibration: recommend against SHIFTED temps, but keep `w` — the real
    # forecast — for the response. The weather card and the notification header must
    # never show a temperature the user isn't actually going to walk out into.
    wc = engine.apply_temp_offset(w, req.tempOffset)
    outfit = engine.recommend(wc, req.gender, req.style)

    closet_used = False
    picks = None
    text = None
    # Slots the wardrobe could not fill. Returned to the phone, which keeps a
    # running record of them — that record is the evidence /shopping reasons from,
    # rather than an opinion about what a wardrobe ought to contain.
    missing: list[str] = []
    if req.closet:
        items = [i.model_dump() for i in req.closet]
        prefs = closet_llm.Prefs.of(rules.clean_rules(req.rules), req.closetOnly)
        result = await closet_llm.closet_outfit(wc, req.gender, req.style, items, prefs)
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
                elif req.closetOnly:
                    # The wardrobe is declared COMPLETE, so the engine's generic
                    # suggestion is not a helpful hint — it is a garment the user
                    # has told us they do not own and cannot put on (2026-08-27).
                    # An empty slot is an empty slot, and which KIND of empty is
                    # what the model reported in `missing`.
                    outfit[slot] = ("None — nothing in your closet for this"
                                    if slot in result["missing"] else "None needed")
            missing = result["missing"]
            # IDs are already validated against the sent closet — echo them so
            # the app can wear-log the exact items (plan amendment 2).
            picks = result["picks"]
        # result None -> honest generic fallback below, closetUsed stays False
        # (plan amendments 3 & 9: never mislabel non-closet advice).

    source = "llm"
    if not text:
        text = await llm.outfit_text(wc, req.gender, req.style)
    if not text:
        text = engine.outfit_to_bullets(outfit)
        source = "rule-engine"

    dt = round(time.monotonic() - t0, 2)
    # Coarse, coordinate-free log line (closet size only — never item content).
    # tempOffset is a personal comfort scalar, not identifying — safe to log.
    # `src` says which client and which build called. Previously this had to be
    # inferred from whether a closet was attached — which is how a phone running a
    # three-versions-old build went unnoticed for two days (2026-08-11).
    log.info(
        "advice ok src=%s day=%s tz=%s lo=%s hi=%s off=%s source=%s closet=%s/%s %.2fs",
        _clean(x_oa_client, 24) or "?",
        req.day,
        w.get("timezone"),
        w["lo"],
        w["hi"],
        req.tempOffset,
        source,
        int(closet_used),
        len(req.closet or []),
        dt,
    )

    # tempOffset is echoed for the same reason closetUsed is: the app shows the user
    # what was actually applied rather than assuming the server honoured it.
    return {
        "weather": w,
        "outfit": outfit,
        "outfit_text": text,
        "source": source,
        "closetUsed": closet_used,
        "missing": missing,
        "picks": picks,
        "tempOffset": req.tempOffset,
    }


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
        default_factory=lambda: ["casual"], min_length=1, max_length=3
    )
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
        return max(1, -(-n_days // 3))  # ceil(n/3)
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
            wx = await weather.fetch_normals(req.lat, req.lon, req.start.isoformat(), req.end.isoformat())
        else:
            # Inside the window. A long trip may run PAST the horizon — clamp the
            # end and say so, rather than letting Open-Meteo 400 the whole request.
            end = min(req.end, horizon)
            truncated = end < req.end
            wx = await weather.fetch_range(req.lat, req.lon, req.start.isoformat(), end.isoformat())
    except Exception as e:
        # PRIVACY: the httpx error text embeds the Open-Meteo URL — lat/lon and the
        # trip dates included. Log the TYPE only, exactly as /advice does.
        log.warning("packing failed: weather fetch error (%s)", type(e).__name__)
        raise HTTPException(status_code=503, detail="weather unavailable") from None

    days, summary = wx["days"], wx["summary"]
    n = summary["nDays"]

    pack, gaps, text, closet_used = [], [], None, False
    if req.closet:
        items = [i.model_dump() for i in req.closet]
        result = await llm.packing_list(days, summary, req.gender, list(req.styles), req.type, items)
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
                    gaps.append(
                        {
                            "category": cat,
                            # have==0 means the closet has NONE registered — a laundry
                            # day can't produce items you don't own, so say buy/register.
                            "need": (
                                f"none in your closet yet — bring/buy ~{want}"
                                if have == 0
                                else f"only {have} of ~{want} clean — plan a laundry day"
                            ),
                        }
                    )
        # result None -> honest generic fallback below, closetUsed stays False.

    if not text:
        # Generic packing advice: dress the trip's WORST case (coldest low, wettest
        # day) via the existing rule engine, so the user still gets something useful.
        worst = {
            "morning": None,
            "lo": summary["loMin"],
            "hi": summary["hiMax"],
            "swing": summary["swing"],
            "rain": max(d["rain"] for d in days),
            "wind": summary["windMax"],
            "isSnow": summary["isSnow"],
            "isRain": summary["isRain"],
            "code": max(days, key=lambda d: d["rain"])["code"],
        }
        text = engine.outfit_to_bullets(engine.recommend(worst, req.gender, req.styles[0]))

    dt_s = round(time.monotonic() - t0, 2)
    # Coarse log ONLY. No coords (as /advice). And no DATES — a real date range plus
    # a destination is itself identifying, unlike /advice's day=0|1.
    log.info(
        "packing ok n=%s mode=%s closet=%s/%s gaps=%s %.2fs",
        n,
        summary["mode"],
        int(closet_used),
        len(req.closet or []),
        len(gaps),
        dt_s,
    )

    return {
        "trip": {"nDays": n, "type": req.type, "styles": req.styles, "truncated": truncated},
        "forecast": {"mode": summary["mode"], "days": days, "summary": summary},
        "pack": pack,
        "gaps": gaps,
        "packing_text": text,
        "closetUsed": closet_used,
    }


@app.post("/shopping")
async def shopping(req: ShoppingRequest, x_oa_client: str = Header(default="")):
    """What is worth adding to the wardrobe, argued from what actually went wrong.

    The user asked for this weekly (2026-08-27). The temptation is to ask a model
    "what should they buy?", which produces a catalogue — a model asked that always
    has an answer. So it is handed evidence instead: the slots the advisor could not
    fill, the weather on those mornings, the thermal calibration, and the bans. A
    wardrobe with no gaps is told it has none.

    PRIVACY: the same posture as everywhere else. Item labels and the gap counts are
    used and discarded; nothing is written down, and the log carries only how many
    suggestions came back.
    """
    t0 = time.monotonic()
    items = [i.model_dump() for i in (req.closet or [])]
    out = await shopping_llm.shopping_list(
        items,
        [g.model_dump() for g in req.gaps],
        rules.clean_rules(req.rules),
        {"tempOffset": req.tempOffset},
    )
    dt = round(time.monotonic() - t0, 2)
    if out is None:
        log.info("shopping failed src=%s %.2fs", _clean(x_oa_client, 24) or "?", dt)
        raise HTTPException(503, "Couldn't work out any suggestions just now.")
    log.info("shopping ok src=%s n=%s gaps=%s %.2fs",
             _clean(x_oa_client, 24) or "?", len(out["suggestions"]), len(req.gaps), dt)
    return out


@app.post("/rule")
async def rule(req: RuleRequest):
    """Turn one line of feedback into a rule this server can CHECK.

    "I got white V-neck inner + white T recommendation. this combination shall be
    banned." (user, 2026-08-24)

    The model reads that sentence once, here, and never again — everything after is
    rules.violations(), a table lookup. That split is the point. The PPK week was a
    long demonstration that a model is excellent at reading a sentence and
    unreliable at remembering it on every future generation, and a prohibition that
    holds most mornings is not a prohibition.

    Returns 422 when the feedback cannot be turned into something enforceable. That
    is the honest answer: a rule stored but unenforceable would leave the user
    believing the advisor had been told.

    PRIVACY: the sentence is used and discarded. Only the shape of the outcome is
    logged — never what the rule says, which is a statement about what somebody
    wears.
    """
    t0 = time.monotonic()
    parsed = await llm.parse_rule(req.text)
    dt = round(time.monotonic() - t0, 2)
    if not parsed:
        log.info("rule not understood %.2fs", dt)
        raise HTTPException(422, "Couldn't turn that into a rule.")
    log.info("rule ok kind=%s %.2fs", parsed["kind"], dt)
    return parsed


@app.post("/triage")
async def triage(req: TriageRequest, x_oa_client: str = Header(default="")):
    """Is this calendar entry a trip, and to which city?

    PRIVACY: the entry's text is used and discarded. Nothing about it is logged —
    not the title, not the location, not the resolved city, not the dates. A title
    plus a date range is far more identifying than anything else this server sees,
    which is why the log line carries only the outcome shape.
    """
    t0 = time.monotonic()
    out = await llm.triage_event(req.title, req.location, req.nights, req.start, req.end,
                                 known=[k.model_dump() for k in req.known])
    dt = round(time.monotonic() - t0, 2)
    if out is None:
        log.info("triage failed %.2fs", dt)
        raise HTTPException(status_code=503, detail="could not judge this entry")
    # `src` is the build that called, same as /advice logs. Without it, a report of
    # "the calendar is still wrong" cannot be told apart from "the phone never got
    # the fix" — which cost a whole round of shipping to the wrong problem
    # (2026-08-23). Still no event text: only which client, and the outcome shape.
    log.info("triage ok src=%s isTrip=%s hasCity=%s conf=%.2f %.2fs",
             _clean(x_oa_client, 24) or "?",
             out["isTrip"], bool(out["city"]), out["confidence"], dt)
    return out


@app.post("/classify")
async def classify(req: ClassifyRequest):
    t0 = time.monotonic()
    # Tolerate a data-URI prefix; validate it IS base64 before shipping to vLLM.
    b64 = req.imageB64.split(",", 1)[-1].strip()
    try:
        base64.b64decode(b64[:400], validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="imageB64 is not valid base64") from None

    raw = await llm.classify_image(b64)
    if raw is None:
        log.warning("classify failed: LLM unavailable or non-JSON (%.2fs)", time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="classification unavailable")

    # Re-validate the LLM's output through the same schema as incoming closet
    # items — one sanitization path for both directions.
    #
    # group/roles/type are FORWARDED, not dropped. The prompt has asked for `group`
    # and `roles` since 2026-08-10, but this constructor never passed them on, so
    # the validator re-derived both from `category` and every classified item came
    # back with roles=[category] — the seasonal-role feature the model was already
    # answering correctly was thrown away one line before it reached the phone, and
    # the folder was re-derived from the single riskiest guess in the answer.
    # reconcile() in _derive still has the last word, so forwarding adds no trust in
    # the model's output.
    raw_type = str(raw.get("type") or "") or None
    # The type is the narrowest thing the model said about this garment, so where it
    # answered nothing usable for warmth/formality, the type's defaults are a better
    # source than the bare 3/["casual"] fallbacks. FILL only — a stated value is
    # about THIS garment, and the table only knows the average one.
    warmth, formality = vocab.apply_type_defaults(
        vocab.normalize_type(raw_type, vocab.canonical_group(raw.get("group"))),
        int(raw.get("warmth") or 0) or None,
        [f for f in (raw.get("formality") or []) if f in vocab.STYLES],
    )
    try:
        item = ClosetItem(
            id="pending-0000",  # phone assigns the real uuid on save
            label=str(raw.get("label") or ""),
            category=raw.get("category"),
            group=vocab.canonical_group(raw.get("group")),
            type=raw_type,
            roles=[r for r in (raw.get("roles") or []) if r in vocab.CATEGORIES],
            colors=[str(c) for c in raw.get("colors") or [] if str(c).strip()][:3],
            warmth=warmth,
            formality=formality,
            waterproof=bool(raw.get("waterproof")),
        )
    except Exception:
        log.warning("classify failed: LLM output failed validation (%.2fs)", time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="classification unusable") from None

    # Coarse log: outcome + timing only — never the image, never the label.
    log.info("classify ok %.2fs", time.monotonic() - t0)
    d = item.model_dump()
    d.pop("id")
    d.pop("availableCount")
    return d
