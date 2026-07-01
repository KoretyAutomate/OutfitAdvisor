"""
app.py — Outfit Advisor DGX server (stateless).

POST /advice  {lat, lon, gender, style, day?}  -> weather + outfit_text + structured outfit
GET  /health                                   -> {ok, vllm}

Privacy invariant: coordinates are NEVER written to disk or logs. They live only as
request-scoped locals, are passed to Open-Meteo + the engine, and discarded. We log
only coarse outcome + timing, never lat/lon. Run uvicorn with access_log disabled so
the framework can't leak the request line.

Run (tailnet-bound):
    uvicorn app:app --host 0.0.0.0 --port 8787
"""
import logging
import time

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

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


class AdviceRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    gender: str = "neutral"   # man | woman | neutral
    style: str = "casual"     # casual | smart | active
    day: int = Field(0, ge=0, le=1)  # 0 = today (morning push), 1 = tomorrow


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
    w = await weather.fetch_weather(req.lat, req.lon, req.day)
    outfit = engine.recommend(w, req.gender, req.style)

    text = await llm.outfit_text(w, req.gender, req.style)
    source = "llm"
    if not text:
        text = engine.outfit_to_bullets(outfit)
        source = "rule-engine"

    dt = round(time.monotonic() - t0, 2)
    # Coarse, coordinate-free log line.
    log.info("advice ok day=%s tz=%s lo=%s hi=%s source=%s %.2fs",
             req.day, w.get("timezone"), w["lo"], w["hi"], source, dt)

    return {"weather": w, "outfit": outfit, "outfit_text": text, "source": source}
