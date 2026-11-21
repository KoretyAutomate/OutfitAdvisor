"""limits.py — a ceiling on how much one request may send (security audit, 2026-11-18).

Every request body here is JSON that pydantic bounds field by field — but only
AFTER the whole body has been read into memory and parsed. `imageB64` is capped at
4.2M characters, and nothing capped the bytes that arrive before that check runs:
any device on the tailnet (the endpoints take no credentials) could post a body of
any size and have this process buffer all of it, on a box that also runs the model.

So the bytes are counted as they arrive. The largest honest request is a photo for
/classify or /cutout — 4.2M characters of base64 plus a few fields — so 6 MiB leaves
room and still stops a body three orders of magnitude larger.

A pure ASGI middleware rather than BaseHTTPMiddleware: it has to wrap `receive`,
and it must refuse on the declared length before reading anything at all.
"""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 6 * 1024 * 1024
_TOO_LARGE = "request body too large"


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # The declared length first: an honest oversized client is refused before a
        # byte of the body is read. A length that is not a number is not trusted
        # either way — the count below is what actually holds.
        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await JSONResponse({"detail": _TOO_LARGE}, status_code=413)(scope, receive, send)
            return

        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body") or b"")
                if seen > self.max_bytes:
                    # No length declared (chunked), or a false one. An HTTPException
                    # because FastAPI re-raises exactly that from its body parsing,
                    # and turns anything else into a 400.
                    raise HTTPException(status_code=413, detail=_TOO_LARGE)
            return message

        await self.app(scope, counted, send)
