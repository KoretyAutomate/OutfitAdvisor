"""In-app update channel: /version and /apk.

Split out of app.py on 2026-09-06 when that file crossed the 600-line ceiling —
this block is the one unit in it with no dependency on the advice path.

The user's pain was losing settings and closet photos on every update. That was
never sideloading's fault — it was CI signing each build with a fresh ephemeral
key, fixed by the persistent keystore + cert-drift gate. Same package + same key
= Android updates in place and keeps app data, exactly like Play does.

What was still missing is DELIVERY. These two endpoints let the app notice a new
build and install it itself, so nothing leaves the tailnet and there is no Play
account, no review, and no targetSdk upgrade.

Publish a build with:  python3 server/publish_apk.py <path-to-app-debug.apk>
"""
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

log = logging.getLogger("outfit")
router = APIRouter()

DIST = Path(os.environ.get("OA_DIST", Path(__file__).resolve().parent.parent / "dist"))


@router.get("/version")
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


@router.get("/apk")
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
