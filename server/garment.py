"""
garment.py — what the funnel reads about ONE garment (user, 2026-10-20).

"Out of the available items, occasion removes certain items ... weather removes
additional items": a filter can only remove what it can read. Three readings, each
the wearer's or the classifier's stated field first, else derived from the name, the
kind and the fabric — the same posture as sleeves.sleeve_of and style.pattern_of:

    level      dress level 1-5: 1 sport · 2 weekend · 3 smart casual ·
               4 business casual · 5 formal
    material   what a shoe's upper is made of (rain: mesh and canvas soak through)
    gauge      how heavy a sweater or cardigan's knit is (a chunky knit goes over
               a tee or a shirt only — user, 2026-10-18)

An unknown reading never removes a garment by itself: `material` None passes the
wet-shoe filter, `gauge` falls back to "mid", and `level` always has an answer from
the kind.

Keywords are English and the Japanese the wearer writes; matched case-insensitively.
"""
import re
import unicodedata

LEVELS = (1, 2, 3, 4, 5)
MATERIALS = ("leather", "suede", "canvas", "mesh", "knit", "rubber", "synthetic")
GAUGES = ("fine", "mid", "chunky")
# Shoe uppers that soak through on a wet commute.
WET_THROUGH = frozenset({"mesh", "canvas", "suede", "knit"})

# The kind's usual level, before the name says otherwise.
TYPE_LEVEL = {
    "t_shirt": 2, "tank": 2, "polo": 3, "shirt": 3, "blouse": 3,
    "sweater": 3, "cardigan": 3, "hoodie": 2, "fleece": 2, "waistcoat": 4,
    "jacket": 2, "blazer": 4, "coat": 4, "puffer": 2, "rainwear": 2,
    "trousers": 3, "jeans": 2, "shorts": 2, "skirt": 3, "leggings": 1,
    "dress": 3, "jumpsuit": 3, "overalls": 2,
    "sneakers": 2, "dress_shoes": 4, "boots": 3, "loafers": 3, "sandals": 1,
}
_GROUP_LEVEL = {"tops": 2, "outerwear": 2, "bottoms": 3, "onepiece": 3, "footwear": 2}

# Checked in order; the first that matches decides. Lowering words first: "track
# jacket" is sportswear whatever a jacket usually is.
_LEVEL_WORDS: tuple[tuple[re.Pattern, int], ...] = (
    (re.compile(r"jogger|track\s*(pant|suit|jacket|top)|sweat\s*(pant|short|suit)|gym|running|"
                r"ジョガー|スウェット|ジャージ", re.I), 1),
    (re.compile(r"drawstring|elastic|cargo|lounge|graphic|logo tee|mesh|canvas|trainer|flip[\s\-]?flop|"
                r"slide|crocs|parka|anorak|イージー|カーゴ|ドローコード|パーカー", re.I), 2),
    # Not the "suit" in jumpsuit, tracksuit or swimsuit (pre-push gate, 2026-10-20).
    (re.compile(r"(?<![a-z])suit\b|tuxedo|dinner jacket|(?<!ジャンプ)(?<!ジャージ)スーツ", re.I), 5),
    (re.compile(r"dress shirt|wool trouser|dress trouser|slacks|tailored|derby|brogue|oxford shoe|"
                r"overcoat|blazer|スラックス|ドレスシャツ", re.I), 4),
    (re.compile(r"oxford|chino|merino|cashmere|leather sneaker|chukka|knit polo|"
                r"チノ|オックスフォード|カシミア", re.I), 3),
)
_DARK_DENIM = re.compile(r"dark|black|raw|indigo|selvedge|rinse|濃紺|ブラック", re.I)

_MATERIAL_WORDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"mesh|メッシュ", re.I), "mesh"),
    (re.compile(r"canvas|キャンバス", re.I), "canvas"),
    (re.compile(r"suede|スエード|スウェード", re.I), "suede"),
    (re.compile(r"knit|flyknit|ニット", re.I), "knit"),
    (re.compile(r"rubber|rain\s*boot|wellington|ラバー|長靴|レインブーツ", re.I), "rubber"),
    (re.compile(r"leather|patent|レザー|革", re.I), "leather"),
)
_FABRIC_MATERIAL = {"leather": "leather", "knit": "knit", "synthetic": "synthetic"}
# Kinds whose upper is near-always leather when nothing says otherwise.
_LEATHER_KINDS = frozenset({"dress_shoes", "loafers"})

_CHUNKY = re.compile(r"chunky|cable|aran|fair\s*isle|nordic|reindeer|snowflake|heavy|fisherman|"
                     r"ノルディック|ケーブル|ローゲージ", re.I)
_FINE = re.compile(r"merino|fine|cashmere|lightweight|light\s*weight|extra\s*fine|silk|"
                   r"ハイゲージ|メリノ|カシミア", re.I)
KNITS = frozenset({"sweater", "cardigan"})

# Trousers that belong with tees and sweatshirts, never with a collar or fine knit
# (style.LOOK_PRINCIPLES; user, 2026-10-18 and 2026-10-20).
_UTILITY = re.compile(r"cargo|jogger|drawstring|elastic|track|sweat|lounge|easy\s*pant|"
                      r"カーゴ|ジョガー|イージー|スウェット|ドローコード", re.I)


def _label(item: dict) -> str:
    """NFKC first: a name typed in full-width letters (ＭＥＳＨ) reads like any other."""
    return unicodedata.normalize("NFKC", str(item.get("label") or ""))


# The old Casual / Smart / Active tags a stated level implies, for what still reads
# them: trip packing, the rollback engine, the phone's laundry soil (user, 2026-10-22).
LEVEL_FORMALITY = {1: ["active"], 2: ["casual"], 3: ["casual", "smart"], 4: ["smart"], 5: ["smart"]}


def stated_level(item: dict) -> int | None:
    """The level the wearer set in the edit sheet, or the photo read found."""
    v = item.get("level")
    return v if isinstance(v, int) and not isinstance(v, bool) and v in LEVELS else None


def level(item: dict) -> int:
    """The garment's dress level, 1-5: stated, else its name, else its kind. A stated
    level is the answer; the old "fits" tags only adjust a guess (user, 2026-10-22:
    the edit sheet's one Dress level replaces them)."""
    if (v := stated_level(item)) is not None:
        return v
    label = _label(item)
    for pat, lvl in _LEVEL_WORDS:
        if pat.search(label):
            return _fits(item, lvl)
    kind = str(item.get("type") or "")
    if kind == "jeans" and _DARK_DENIM.search(label + " " + " ".join(item.get("colors") or [])):
        return _fits(item, 3)
    return _fits(item, TYPE_LEVEL.get(kind, _GROUP_LEVEL.get(str(item.get("group") or ""), 3)))


def _fits(item: dict, lvl: int) -> int:
    """The "fits" tags the wearer can correct in the edit sheet, where they are
    narrower than the kind's: only sportswear is a 1, and smart without casual is at
    least smart casual."""
    tags = set(item.get("formality") or [])
    if tags == {"active"}:
        return 1
    return max(lvl, 3) if "smart" in tags and "casual" not in tags else lvl


def material(item: dict) -> str | None:
    """A shoe's upper: stated, else its name, else its fabric or kind; None unknown."""
    v = item.get("material")
    if v in MATERIALS:
        return v
    label = _label(item)
    for pat, m in _MATERIAL_WORDS:
        if pat.search(label):
            return m
    if (f := _FABRIC_MATERIAL.get(str(item.get("fabric") or ""))) is not None:
        return f
    return "leather" if item.get("type") in _LEATHER_KINDS else None


def gauge(item: dict) -> str | None:
    """A sweater or cardigan's knit: stated, else its name, else busy = chunky, else
    mid. None for anything that is not knitwear."""
    if item.get("type") not in KNITS:
        return None
    v = item.get("gauge")
    if v in GAUGES:
        return v
    label = _label(item)
    if _CHUNKY.search(label):
        return "chunky"
    if _FINE.search(label) or item.get("fabric") in ("cashmere", "silk"):
        return "fine"
    pattern = item.get("pattern")
    return "chunky" if pattern not in (None, "solid") else "mid"


def utility_trousers(item: dict) -> bool:
    """Cargo, joggers, drawstring and the like — unless a stated level says smart
    casual or above: tailored cargos set to 3 go with a shirt (user, 2026-10-22)."""
    if item.get("group") != "bottoms" or ((v := stated_level(item)) is not None and v >= 3):
        return False
    return bool(_UTILITY.search(_label(item)))


def wets_through(item: dict) -> bool:
    """Shoes that soak through on a wet commute. Unknown material never does, and a
    pair marked waterproof never does whatever its upper (a waterproof mesh trainer)."""
    return item.get("group") == "footwear" and not item.get("waterproof") and material(item) in WET_THROUGH
