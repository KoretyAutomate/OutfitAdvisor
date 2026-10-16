"""The "didn't wear this" reasons cross three languages with nothing joining them.

index.html writes `oa.skipped` and sends `skipped`; AdviceWorker.kt reads the same
key for the morning push; schemas.py bounds what arrives. A renamed key or a changed
cap on one side would quietly stop the push learning (or 422 nothing, since the
server drops rather than refuses). Read from source, so this cannot drift.
"""
import re
from pathlib import Path

from schemas import AdviceRequest

ROOT = Path(__file__).resolve().parent.parent.parent
JS = (ROOT / "app" / "www" / "index.html").read_text()
KT = (ROOT / "app" / "android" / "app" / "src" / "main" / "java" / "com" / "korety"
      / "outfitadvisor" / "AdviceWorker.kt").read_text()


def _js_const(name: str) -> int:
    return int(re.search(rf"\b{name}=(\d+)", JS).group(1))


def _kt_const(name: str) -> int:
    return int(re.search(rf"const val {name} = (\d+)", KT).group(1))


def test_both_sides_use_one_key():
    assert 'prefSet("oa.skipped"' in JS
    assert 'KEY_SKIPPED = "oa.skipped"' in KT


def test_both_sides_send_the_field_the_server_reads():
    assert "body.skipped=" in JS
    assert 'b.put("skipped"' in KT
    assert "skipped" in AdviceRequest.model_fields


def test_the_caps_agree_with_the_server():
    many = AdviceRequest(lat=0, lon=0, skipped=[f"r{i}" for i in range(20)]).skipped
    long = AdviceRequest(lat=0, lon=0, skipped=["x" * 500]).skipped[0]
    assert _js_const("SKIP_SEND") == _kt_const("SKIP_SEND") == len(many)
    assert _js_const("SKIP_MAX") == _kt_const("SKIP_MAX") == len(long)
