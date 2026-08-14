"""Every header the app sends must be allowed by CORS.

Why this exists (regression 2026-08-14): adding `X-OA-Client` to the web layer's
fetch — for debugging, of all things — made the WebView send a CORS preflight.
The header was not in `allow_headers`, so the preflight failed with 400, the
browser blocked the POST, fetch() threw, and the app rendered "offline estimate".
Every in-app advice request was broken for days. It hid because the NATIVE push
is not subject to CORS and kept working, so the server log looked healthy and the
symptom looked like a dead LLM.

This reads the REAL app/www/index.html, extracts every header it sends to the
advisor, and checks each against the server's real CORS configuration. It cannot
drift, because both sides are read from source rather than restated here.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server"))

INDEX = ROOT / "app" / "www" / "index.html"


def _allowed_headers() -> set[str]:
    """The headers the running app actually permits, lowercased."""
    import app as server_app

    for mw in server_app.app.user_middleware:
        opts = getattr(mw, "kwargs", None) or getattr(mw, "options", {})
        if "allow_headers" in opts:
            return {h.lower() for h in opts["allow_headers"]}
    raise AssertionError("no CORS middleware with allow_headers found")


def _headers_the_app_sends() -> set[str]:
    """Custom headers in index.html's fetch calls, lowercased.

    Deliberately scans the whole file rather than one call site: the next header
    will be added somewhere else, and this must notice it too.
    """
    src = INDEX.read_text()
    found = set()
    # headers:{ ... "X-Name":... } and setRequestProperty-style string keys
    for block in re.findall(r"headers\s*:\s*\{([^}]*)\}", src):
        for key in re.findall(r'["\']([A-Za-z][A-Za-z0-9-]*)["\']\s*:', block):
            found.add(key.lower())
    return found


def test_every_header_the_app_sends_is_allowed():
    allowed = _allowed_headers()
    sent = _headers_the_app_sends()
    # CORS always permits these without being listed.
    safelisted = {"accept", "accept-language", "content-language", "content-type"}
    missing = {h for h in sent if h not in allowed and h not in safelisted}
    assert not missing, (
        f"index.html sends {sorted(missing)} but the server's CORS allow_headers is "
        f"{sorted(allowed)}. The WebView preflight will fail with 400 and every "
        f"in-app request will silently fall back to the offline estimate."
    )


def test_the_debugging_header_specifically_is_allowed():
    # Named explicitly: this is the one that actually broke, and a generic scan
    # would stop covering it the moment the fetch call is refactored.
    assert "x-oa-client" in _allowed_headers()


def test_the_capacitor_origins_are_allowed():
    import app as server_app

    for mw in server_app.app.user_middleware:
        opts = getattr(mw, "kwargs", None) or getattr(mw, "options", {})
        if "allow_origins" in opts:
            origins = set(opts["allow_origins"])
            # The Android WebView serves from https://localhost, iOS from
            # capacitor://localhost. Losing either silently kills the app layer.
            assert "https://localhost" in origins
            assert "capacitor://localhost" in origins
            return
    raise AssertionError("no CORS middleware with allow_origins found")
