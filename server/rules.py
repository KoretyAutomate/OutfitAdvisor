"""rules.py — the wearer's own styling rules, enforced rather than requested.

The user's example (2026-08-24): "I got white V-neck inner + white T
recommendation. this combination shall be banned."

Two ways to honour that. Put the sentence in the prompt and hope, or turn it into
something checkable and check it. This module is the second. It is the same lesson
the PPK/Kazakhstan week taught at length: a model is excellent at READING a
sentence once and unreliable at REMEMBERING it on every future generation, so the
model parses the rule exactly once (llm.parse_rule) and everything after that is a
table lookup. A rule cannot be 85% observed.

The vocabulary is closed on purpose. A rule that names a type or a slot this
project does not have is a rule that silently never fires, which is worse than a
rejected one: the user believes the advisor was told.

Rules are held ON THE PHONE with the closet and arrive with each request. This
server stays stateless.
"""

import vocab

# What a rule can say. Deliberately small — these three cover "never together",
# "never at all" and "not both the same colour", which is the shape every example
# so far has taken. A kind outside this set is dropped at validation.
RULE_KINDS = ("avoid_pair", "avoid_item", "avoid_same_color")

# How many rules one request may carry. A prompt that grows without limit stops
# being a prompt, and a wardrobe with 40 prohibitions has a different problem.
MAX_RULES = 24
MAX_COLOR = 24


def _norm(s: object, limit: int = 40) -> str:
    return str(s or "").strip().lower()[:limit]


def clean_descriptor(d: object) -> dict | None:
    """One side of a rule: which garments it speaks about.

    Every field is optional and every field present must match, so {} would match
    EVERYTHING and turn "avoid_item" into "own nothing". An empty descriptor is
    therefore not a permissive rule, it is a broken one, and it is dropped.
    """
    if not isinstance(d, dict):
        return None
    out: dict = {}
    t = _norm(d.get("type"))
    if t in vocab.TYPE_LABEL:
        out["type"] = t
    g = vocab.canonical_group(_norm(d.get("group")))
    if g:
        out["group"] = g
    r = _norm(d.get("role"))
    if r in vocab.CATEGORIES:
        out["role"] = r
    c = _norm(d.get("color"), MAX_COLOR)
    if c:
        out["color"] = c
    return out or None


def clean_rule(r: object) -> dict | None:
    """Validate one rule from the phone. Returns None for anything unenforceable."""
    if not isinstance(r, dict):
        return None
    kind = _norm(r.get("kind"))
    if kind not in RULE_KINDS:
        return None
    a = clean_descriptor(r.get("a"))
    if not a:
        return None
    b = clean_descriptor(r.get("b"))
    # A pair rule needs both sides; a colour rule needs two slots to compare.
    if kind in ("avoid_pair", "avoid_same_color") and not b:
        return None
    out = {"kind": kind, "a": a}
    if b:
        out["b"] = b
    rid = str(r.get("id") or "")[:64]
    if rid:
        out["id"] = rid
    text = str(r.get("text") or "")[:160]
    if text:
        out["text"] = text
    return out


def clean_rules(rules: object) -> list[dict]:
    if not isinstance(rules, list):
        return []
    return [c for c in (clean_rule(r) for r in rules[:MAX_RULES]) if c]


def _colors(item: dict) -> set[str]:
    return {_norm(c, MAX_COLOR) for c in (item.get("colors") or []) if str(c).strip()}


def _matches(desc: dict, slot: str, item: dict) -> bool:
    """Does the garment in this slot answer this description?

    `role` is the SLOT it was actually picked into, not the set of roles it could
    play. The rule is about the outfit in front of the user: a shirt worn as the
    base today is a base today, whatever else it could have been.
    """
    if "role" in desc and desc["role"] != slot:
        return False
    if "type" in desc and _norm(item.get("type")) != desc["type"]:
        return False
    if "group" in desc and vocab.canonical_group(_norm(item.get("group"))) != desc["group"]:
        return False
    return not ("color" in desc and desc["color"] not in _colors(item))


def _found(desc: dict, worn: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    return [(slot, it) for slot, it in worn if _matches(desc, slot, it)]


def violations(rules: list[dict], picks: dict, by_item: dict) -> list[dict]:
    """Which rules this outfit breaks, and which slot to blame.

    Returns [{rule, slot, why}] — `slot` is what a caller should clear if a retry
    does not fix it. For a pair rule that is the SECOND side: the first is usually
    the item the outfit is built around, and dropping the addition is the smaller
    change. For avoid_item it is the offending slot itself.
    """
    worn = [(slot, by_item[i]) for slot, i in picks.items() if i and i in by_item]
    out: list[dict] = []
    for r in rules:
        kind, a, b = r["kind"], r["a"], r.get("b")
        hits_a = _found(a, worn)
        if not hits_a:
            continue
        if kind == "avoid_item":
            out.append({"rule": r, "slot": hits_a[0][0],
                        "why": f"{_describe(a)} is not to be worn"})
            continue
        side_b: dict = b or {}
        hits_b = [h for h in _found(side_b, worn) if h[0] != hits_a[0][0]]
        if not hits_b:
            continue
        if kind == "avoid_pair":
            out.append({"rule": r, "slot": hits_b[0][0],
                        "why": f"{_describe(a)} and {_describe(side_b)} are not worn together"})
        elif kind == "avoid_same_color":
            shared = _colors(hits_a[0][1]) & _colors(hits_b[0][1])
            if shared:
                out.append({"rule": r, "slot": hits_b[0][0],
                            "why": f"{_describe(a)} and {_describe(side_b)} are both "
                                   f"{sorted(shared)[0]}"})
    return out


def _describe(d: dict) -> str:
    """A rule side in words, for the retry note and for the log."""
    bits = []
    if d.get("color"):
        bits.append(d["color"])
    if d.get("type"):
        bits.append(vocab.TYPE_LABEL.get(d["type"], d["type"]).split(" /")[0].lower())
    elif d.get("group"):
        bits.append(d["group"])
    if d.get("role"):
        bits.append(f"in the {d['role']} slot")
    return " ".join(bits) or "anything"


def prompt_block(rules: list[dict]) -> str:
    """The rules as prose for the generator, so it usually gets them right first go.

    This is a hint, NOT the enforcement — violations() is. Both exist deliberately:
    the prompt saves a corrective retry on the common case, and the check is what
    makes the promise true on the uncommon one.
    """
    if not rules:
        return ""
    lines = []
    for r in rules:
        a, b = _describe(r["a"]), _describe(r.get("b") or {})
        if r["kind"] == "avoid_item":
            lines.append(f"- never use {a}")
        elif r["kind"] == "avoid_pair":
            lines.append(f"- never use {a} together with {b}")
        else:
            lines.append(f"- {a} and {b} must not be the same colour")
    body = "\n".join(lines[:MAX_RULES])
    return (
        "THE WEARER'S OWN RULES — they have told you these; follow every one:\n"
        f"{body}\n"
    )
