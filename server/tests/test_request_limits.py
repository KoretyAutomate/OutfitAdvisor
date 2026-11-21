"""A request may not make the server buffer more than a photo's worth of bytes.

Why this exists (security audit, 2026-11-18): pydantic bounds every field, but only
after the whole body is in memory and parsed, and no endpoint asks who is calling.
Any device on the tailnet could post a body of any size. Each test here was seen to
fail with the middleware removed from app.py: the oversized bodies came back 422 —
read in full, parsed, and only then refused for the field's length.
"""
import json

from fastapi.testclient import TestClient

import app as srv
import limits
from schemas import ClassifyRequest

client = TestClient(srv.app)

# /rule is the cheapest endpoint to aim at: an over-long `text` fails validation
# before any model is called, so an unrefused body shows up as a 422, not a hang.
OVER = json.dumps({"text": "x" * (limits.MAX_BODY_BYTES + 1)}).encode()


def test_a_declared_oversized_body_is_refused_with_413():
    r = client.post("/rule", content=OVER, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "request body too large"}


def test_an_undeclared_oversized_body_is_refused_as_it_arrives():
    """Chunked: no Content-Length to read, so only the running count can stop it."""
    def chunks():
        for k in range(0, len(OVER), 256 * 1024):
            yield OVER[k:k + 256 * 1024]

    r = client.post("/rule", content=chunks(), headers={"content-type": "application/json"})
    assert "content-length" not in {k.lower() for k in r.request.headers}
    assert r.status_code == 413


def test_the_refusal_is_readable_by_the_app():
    """CORS wraps the limit, not the other way round — or the WebView would report a
    refused upload as "couldn't reach the server"."""
    r = client.post("/rule", content=OVER,
                    headers={"content-type": "application/json", "origin": "https://localhost"})
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == "https://localhost"


def test_a_body_at_the_limit_is_still_read():
    """Both sides of the boundary: exactly MAX_BODY_BYTES is let through to
    validation (422 for the over-long text), one byte more is not."""
    pad = limits.MAX_BODY_BYTES - len(json.dumps({"text": ""}).encode())
    at = json.dumps({"text": "x" * pad}).encode()
    assert len(at) == limits.MAX_BODY_BYTES
    assert client.post("/rule", content=at, headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/rule", content=at + b" ",
                       headers={"content-type": "application/json"}).status_code == 413


def test_the_largest_photo_the_schema_allows_fits_under_the_limit():
    """The limit must never be what refuses an honest /classify or /cutout: the
    biggest imageB64 the schema accepts, with its climate anchors, has room."""
    longest = next(m.max_length for m in ClassifyRequest.model_fields["imageB64"].metadata
                   if getattr(m, "max_length", None))
    body = json.dumps({"imageB64": "A" * longest, "climate": {"cold": -10.5, "avg": 11.25, "hot": 27.75}})
    assert len(body.encode()) + 64 * 1024 < limits.MAX_BODY_BYTES


def test_an_ordinary_request_is_untouched():
    r = client.post("/rule", content=b"{}", headers={"content-type": "application/json"})
    assert r.status_code == 422      # the schema's own refusal, not the limit's
