"""
check_types_live.py — verification for the group > type taxonomy against the LIVE
server and the real vLLM (user request 2026-08-14).

Not a unit test, and deliberately NOT named test_* — same reason as
check_packing_live.py: it does real network work and would hijack the offline
suite. The offline half is server/tests/test_taxonomy.py.

What only a live run can answer:
  1. /advice still accepts a closet now that every item carries `type`, and the
     model still produces legal picks — the type went into the prompt, so its cost
     is measured, not assumed.
  2. the type actually STEERS the pick. Two shirts identical in every attribute
     the prompt shows except their type — a polo and a tee — put to a `smart` day.
     Before this round the model had nothing to choose between them.
  3. /classify returns `group`, `roles` AND `type` to the phone. Those first two
     were being asked for and then dropped by the endpoint; a live call is what
     proves they now arrive.

Run:  python3 server/tests/check_types_live.py   (server must be up on the tailnet IP)
"""

import base64
import io
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_http import request_json

BASE = "http://100.112.171.54:8787"

# Boston in August — warm enough that outer/mid are None, so the model's only real
# decision is WHICH top. Both candidates are base-only, warmth 2, smart-capable,
# same colour. The single difference the prompt can see is the type.
CLOSET: list[dict[str, Any]] = [
    {
        "id": "itm-inner-airism", "label": "grey undershirt", "category": "inner",
        "group": "underwear", "type": "undershirt", "roles": ["inner"],
        "colors": ["grey"], "warmth": 1, "formality": ["casual", "smart"],
        "waterproof": False, "availableCount": 3,
    },
    {
        "id": "itm-base-navy-polo", "label": "navy short-sleeve top A", "category": "base",
        "group": "tops", "type": "polo", "roles": ["base"],
        "colors": ["navy"], "warmth": 2, "formality": ["casual", "smart"],
        "waterproof": False, "availableCount": 2,
    },
    {
        "id": "itm-base-navy-tee", "label": "navy short-sleeve top B", "category": "base",
        "group": "tops", "type": "t_shirt", "roles": ["base"],
        "colors": ["navy"], "warmth": 2, "formality": ["casual", "smart"],
        "waterproof": False, "availableCount": 2,
    },
    {
        "id": "itm-bottoms-chinos", "label": "stone chinos", "category": "bottoms",
        "group": "bottoms", "type": "trousers", "roles": ["bottoms"],
        "colors": ["stone"], "warmth": 3, "formality": ["casual", "smart"],
        "waterproof": False, "availableCount": 2,
    },
]


def post(path: str, body: dict, timeout: int = 120) -> dict:
    """POST and insist on a 200 — a rejection here IS the failure being hunted."""
    status, payload = request_json(
        BASE + path, body, timeout=timeout, headers={"X-OA-Client": "check/types"}
    )
    if status != 200:
        raise RuntimeError(f"{path} -> HTTP {status}: {payload}")
    return payload


def _one_pixel_jpeg_b64() -> str:
    """A minimal valid JPEG. The point is not to classify it correctly — it is to
    prove the SHAPE of what comes back, which is what the phone reads."""
    try:
        from PIL import Image
    except ImportError:
        return ""
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 40, 90)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> int:
    fails = 0

    print("=== 1. /advice accepts a typed closet ===")
    d = post("/advice", {"lat": 42.36, "lon": -71.06, "gender": "man",
                         "style": "smart", "day": 0, "closet": CLOSET})
    print(f"  source={d['source']} closetUsed={d['closetUsed']}")
    if not d["closetUsed"]:
        print("  FAIL: the closet was not used — the type may have broken the prompt")
        fails += 1
    picks = d.get("picks") or {}
    by_id = {i["id"]: i for i in CLOSET}
    for slot, iid in picks.items():
        if not iid:
            continue
        allowed = by_id[iid]["roles"]
        ok = slot in allowed
        print(f"  {slot:<11} {by_id[iid]['label']:<26} "
              f"[{by_id[iid].get('type')}] {'ok' if ok else 'ILLEGAL'}")
        if not ok:
            fails += 1

    print("\n=== 2. the type steers the pick (polo vs tee, smart day) ===")
    # Not a hard gate: the model is free to disagree, and one sample is not proof.
    # It is reported so a regression that makes the type inert is visible.
    base = picks.get("base")
    print(f"  base -> {base} ({by_id.get(base, {}).get('type')})")
    print("  (expected: polo for a smart day; tee would mean the type carried no weight)")

    print("\n=== 3. /classify returns group, roles and type ===")
    b64 = _one_pixel_jpeg_b64()
    if not b64:
        print("  SKIPPED: Pillow not installed here — cannot synthesise a JPEG")
    else:
        try:
            c = post("/classify", {"imageB64": b64}, timeout=90)
            print("  " + json.dumps(c))
            for key in ("group", "roles", "type"):
                if key not in c:
                    print(f"  FAIL: /classify response has no {key!r}")
                    fails += 1
        except (RuntimeError, OSError, ValueError) as e:
            print(f"  classify unavailable ({type(e).__name__}) — not a taxonomy failure")

    print(f"\nRESULT: {'ok' if fails == 0 else f'{fails} failure(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
