"""The one place the live checks talk HTTP.

`check_packing_live.py` and `check_types_live.py` each grew their own `post()`
around `urllib`, which meant the S310 exception had to be granted per file and
grew by two every time a new live check was written. There is one urlopen now,
in one file, and the exception is granted once — see the entry in ruff.toml.

An HTTP error status is RETURNED, never raised: these checks assert on 4xx as
much as on 200, so a rejection is data, not an exception.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

JSON_HEADERS = {"Content-Type": "application/json"}


def request_json(
    url: str,
    body: dict | None = None,
    *,
    timeout: int = 120,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """GET `url` (no body) or POST `body` to it. Returns `(status, payload)`.

    `payload` is the decoded JSON on success, or the first 200 characters of the
    error body when the server rejects the request.
    """
    data = None if body is None else json.dumps(body).encode()
    sent = dict(JSON_HEADERS) if data is not None else {}
    sent.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=sent)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:200]
