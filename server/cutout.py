"""Garment cutouts: the background removed, the picture made presentable (2026-09-07).

The closet is photos of clothes on a bed, a chair, a floor. A wardrobe app reads
as a wardrobe when each garment sits alone on white at the same scale — the look
the paper & ink redesign assumed. The phone already sends the photo here for
/classify, stateless and never stored, so the cutout is one more transform in the
same trip; the phone keeps owning the file.

The matte comes from rembg (ONNX, CPU, `isnet-general-use`), loaded once, lazily,
so a server without it still starts — /cutout then answers 503 and the phone
keeps the original. Everything after the matte is plain Pillow: crop to the
garment, pad, centre on a square white canvas. No levels, no colour work: a first
cut applied autocontrast and the white canvas skewed the histogram so a
(40,70,180) blue came back (0,0,146) — a shirt a colour it is not (live probe,
2026-09-07). The cutout and the framing ARE the "nice"; the colours stay the
camera's.

PRIVACY: the image is used and discarded. Only timings reach the journal.
"""
import base64
import importlib.util
import io
import logging
import os
import time

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

log = logging.getLogger("outfit")
router = APIRouter()

# Which rembg model. An environment override WITH a default, deliberately: this
# server has no .env — every setting it reads (OA_DIST here, OA_IP in the watchdog)
# is an environment variable with a default, and the vLLM model is a constant in
# llm.py. The default is the documented install path (rembg fetches it on first
# use); a deployment with another model provisioned names it without a code change.
MODEL = os.environ.get("OA_CUTOUT_MODEL", "isnet-general-use")
CANVAS = 1024          # square, so every tile shows the whole garment at one scale
PAD = 0.08             # of the garment's longer side, on every edge
ALPHA_MIN = 16         # below this the matte is treated as background
QUALITY = 88
MIN_COVERAGE = 0.01    # foreground PIXELS below this share of the photo is "nothing found"

_session = None        # rembg session, built on first use


class CutoutRequest(BaseModel):
    # Same bound as /classify: ~3 MB of image, base64. The phone sends ~512 px.
    imageB64: str = Field(..., min_length=100, max_length=4_200_000)


def available() -> bool:
    """Is rembg installed here? A presence check, not an import — the import is
    slow and happens once, in _matte, on the first real request."""
    return importlib.util.find_spec("rembg") is not None


def _matte(img: Image.Image) -> Image.Image:
    """RGBA with the background made transparent. Isolated so tests can fake it."""
    global _session
    from rembg import new_session, remove
    if _session is None:
        _session = new_session(MODEL)
    out = remove(img, session=_session)
    return out.convert("RGBA")


def compose(rgba: Image.Image) -> Image.Image | None:
    """The cutout on white: cropped to the garment, padded, square. Colours untouched.

    None when the matte found nothing worth keeping — the phone then keeps its
    original rather than a blank white square.
    """
    alpha = rgba.getchannel("A").point(lambda a: 255 if a >= ALPHA_MIN else 0)
    box = alpha.getbbox()
    if not box:
        return None
    w, h = box[2] - box[0], box[3] - box[1]
    # Coverage is counted in PIXELS, not as the box's area: a few specks far apart
    # span a box the size of the photo while keeping almost nothing, and that
    # near-blank square would have replaced the wearer's original (the pre-push
    # reviewer, 2026-09-07).
    kept = alpha.histogram()[255]
    if kept < MIN_COVERAGE * rgba.width * rgba.height:
        return None
    # Crop to the garment itself, then give the CANVAS the margin: clamping a
    # padded crop to the photo's edges lost the margin on any side the garment
    # touched (the pre-push reviewer, 2026-09-07). This way every side gets it.
    pad = int(round(max(w, h) * PAD))
    cut = rgba.crop(box)
    side = max(cut.width, cut.height) + 2 * pad
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    canvas.alpha_composite(cut, ((side - cut.width) // 2, (side - cut.height) // 2))
    flat = canvas.convert("RGB")
    if side != CANVAS:
        flat = flat.resize((CANVAS, CANVAS), Image.LANCZOS)
    return flat


def _decode(b64: str) -> Image.Image:
    raw = base64.b64decode(b64.split(",", 1)[-1].strip(), validate=True)
    img = Image.open(io.BytesIO(raw))
    img.load()
    return ImageOps.exif_transpose(img).convert("RGBA")


def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def cutout(b64: str) -> str | None:
    """Base64 JPEG in, base64 JPEG cutout out; None when nothing was found."""
    img = _decode(b64)
    result = compose(_matte(img))
    return _encode(result) if result is not None else None


@router.post("/cutout")
async def cutout_route(req: CutoutRequest):
    t0 = time.monotonic()
    if not available():
        raise HTTPException(status_code=503, detail="cutout unavailable on this server")
    try:
        # ONNX inference is CPU work of a second or more; on the event loop it
        # would stall /advice and /health for everyone while a closet is tidied.
        out = await run_in_threadpool(cutout, req.imageB64)
    except HTTPException:
        raise
    except (ValueError, OSError):
        raise HTTPException(status_code=422, detail="imageB64 is not a readable image") from None
    except Exception as e:
        # The class only. A matte failure's message could carry paths or shapes; the
        # image itself never reaches the journal.
        log.warning("cutout failed (%s) %.2fs", type(e).__name__, time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="cutout failed") from None
    if out is None:
        log.info("cutout found nothing %.2fs", time.monotonic() - t0)
        raise HTTPException(status_code=502, detail="nothing found to cut out")
    log.info("cutout ok %.2fs", time.monotonic() - t0)
    return {"imageB64": out}
