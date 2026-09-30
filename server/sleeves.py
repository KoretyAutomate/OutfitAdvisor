"""
sleeves.py — how far a garment's sleeves reach, and when two of them clash.

User, 2026-09-30: a long-sleeve tee under a t-shirt. The cuffs show below the short
sleeve, and nobody dresses like that on purpose. layers.py repairs an outfit that
has one; this is the reading and the test, on their own so the replacement search
in picks.py can refuse a clashing garment too — picks.py cannot import layers.py,
which imports it.
"""
import re

SLEEVES = ("short", "long", "none")

# The torso, bottom to top. `outer` is left out of the sleeve rule: a gilet is
# sleeveless on purpose, and a short-sleeved jacket over a long sleeve is rare
# enough that guessing at it would cost more than it saves.
SLEEVE_STACK = ("inner", "base", "mid")

# Read off the NAME, for garments saved before the field existed. Checked long ->
# none -> short, so "long-sleeve tee" is long and not a tee's default. English and
# the Japanese the wearer actually writes ("ロンT" is how a long-sleeve tee is
# sold in Japan).
_LONG = re.compile(r"long[\s\-]*(sleeve[sd]?|t\b|tee)|longsleeve|\bl/s\b|長袖|ロン\s*[tTｔＴ]",
                   re.IGNORECASE)
_NONE = re.compile(r"sleeveless|\btank\b|camisole|\bcami\b|ノースリーブ|タンク", re.IGNORECASE)
_SHORT = re.compile(r"short[\s\-]*sleeve[sd]?|\bs/s\b|半袖", re.IGNORECASE)

# What a KIND implies when neither the wearer nor the name says. Only kinds where
# the answer is near-universal: a "tee" with no qualifier is short-sleeved, a
# cardigan is long. Shirts and thermals come both ways, so they stay unknown — and
# an unknown sleeve never triggers the rule. Guessing wrong would take away a
# garment the wearer chose for no reason they could see.
TYPE_SLEEVE = {
    "t_shirt": "short", "polo": "short", "tank": "none", "waistcoat": "none",
    "sweater": "long", "cardigan": "long", "hoodie": "long", "fleece": "long",
}


def sleeve_of(item: dict) -> str | None:
    """The garment's sleeve: stated, else read from its name, else its kind's."""
    s = item.get("sleeve")
    if s in SLEEVES:
        return s
    label = str(item.get("label") or "")
    for pat, answer in ((_LONG, "long"), (_NONE, "none"), (_SHORT, "short")):
        if pat.search(label):
            return answer
    return TYPE_SLEEVE.get(str(item.get("type") or ""))


def sleeve_clashes(picks: dict, by_item: dict) -> list[tuple[str, str]]:
    """(lower, upper) pairs where a long sleeve sits under a short one."""
    worn = [(c, sleeve_of(by_item.get(picks[c]) or {})) for c in SLEEVE_STACK if picks.get(c)]
    return [(lo, hi) for i, (lo, s_lo) in enumerate(worn) if s_lo == "long"
            for hi, s_hi in worn[i + 1:] if s_hi == "short"]
