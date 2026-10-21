"""Footwear, accessories and outerwear never go in the laundry; socks do (user,
2026-10-17; outerwear 2026-10-21).

index.html decides it for everything the app holds, and FeedbackReceiver.kt decides
it again for the notification's "Wearing it" before the app has folded that wear in.
If the two disagreed, a pair of shoes worn from the notification would be held back
from the next morning's push while the app called them wearable. Read from source,
so the twins cannot drift.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JS = (ROOT / "app" / "www" / "index.html").read_text()
PKG = ROOT / "app" / "android" / "app" / "src" / "main" / "java" / "com" / "korety" / "outfitadvisor"
RECEIVER = (PKG / "FeedbackReceiver.kt").read_text()


def _match(pattern: str, src: str) -> re.Match:
    m = re.search(pattern, src, re.S)
    assert m, f"{pattern} not found"
    return m


def test_both_sides_name_the_same_groups_and_the_socks_exception():
    js = _match(r'const neverWashed=it=>!!it&&\(it\.group==="(\w+)"\|\|it\.group==="(\w+)"'
                r'\|\|\(it\.group==="(\w+)"&&it\.type!=="(\w+)"\)\);', JS)
    kt = _match(r'fun neverWashed\(o: JSONObject\): Boolean \{\s*val g = o\.optString\("group"\)\s*'
                r'return g == "(\w+)" \|\| g == "(\w+)" \|\| \(g == "(\w+)" && o\.optString\("type"\) != "(\w+)"\)',
                RECEIVER)
    assert js.groups() == kt.groups() == ("accessories", "outerwear", "footwear", "socks")


def test_the_native_hold_skips_them():
    hold = _match(r"fun applyNativeWears.*?o\.put\(\"availableCount\", n - 1\)", RECEIVER).group(0)
    assert "if (neverWashed(o)) continue" in hold


def test_the_push_items_carry_what_the_rule_reads():
    meta = _match(r"const itemMeta=i=>\(\{(.*?)\}\);", JS).group(1)
    assert "group:i.group" in meta and "type:normType(" in meta


def test_socks_are_a_footwear_kind():
    assert '"socks"]' in _match(r"footwear:\[([^\]]*\])", JS).group(0)
