#!/usr/bin/env python3
"""Does asking again actually give you something else? (user, 2026-09-03)

The unit tests next door prove the seam: `shown` survives validation, reaches the
prompt, exempts a slot with no alternative, and spends a retry on a repeat that
could have been avoided. None of that answers the question the user asked, which is
about a 122B model's behaviour and cannot be stubbed — the whole reason this bug
reached the field is that every unit involved was already correct.

So this asks the REAL server, four times, exactly as the phone does: once cold, then
three times carrying what the previous answer put on screen.

Not named test_* on purpose: it needs vLLM resident and a working Tailscale bind,
and it sys.exit()s, which would kill pytest collection for the whole tree.
Run: python3 server/tests/check_reroll_live.py [n]
"""
import json
import sys
import urllib.request

BASE = "http://100.112.171.54:8787"
SLOTS = ("inner", "base", "mid", "outer", "bottoms", "footwear", "accessories")


def item(i, label, cat, warmth, colors, formality=("casual",)):
    return {"id": f"itm-000000{i:02d}", "label": label, "category": cat,
            "colors": list(colors), "warmth": warmth, "formality": list(formality),
            "waterproof": False, "availableCount": 3}


# Five bases, four bottoms, three pairs of shoes — a wardrobe with room to vary. If
# this one repeats itself there is nothing wrong with the closet.
CLOSET = [
    item(1, "white cotton tee", "base", 2, ["white"]),
    item(2, "navy cotton tee", "base", 2, ["navy"]),
    item(3, "grey henley", "base", 3, ["grey"]),
    item(4, "blue oxford shirt", "base", 3, ["blue"], ("casual", "smart")),
    item(5, "black polo", "base", 2, ["black"], ("casual", "smart")),
    item(6, "charcoal chinos", "bottoms", 3, ["charcoal"], ("casual", "smart")),
    item(7, "blue jeans", "bottoms", 3, ["blue"]),
    item(8, "khaki shorts", "bottoms", 1, ["khaki"]),
    item(9, "olive linen trousers", "bottoms", 2, ["olive"]),
    item(10, "white sneakers", "footwear", 2, ["white"]),
    item(11, "brown leather loafers", "footwear", 2, ["brown"], ("casual", "smart")),
    item(12, "running shoes", "footwear", 2, ["grey"], ("active",)),
    item(13, "light grey hoodie", "mid", 3, ["grey"]),
    item(14, "navy cardigan", "mid", 3, ["navy"], ("casual", "smart")),
    item(15, "black baseball cap", "accessories", 1, ["black"]),
    item(16, "cotton undershirt", "inner", 2, ["white"]),
]
LABEL = {i["id"]: i["label"] for i in CLOSET}
BODY = {"lat": 40.7, "lon": -74.0, "gender": "man", "style": "casual", "day": 0,
        "tempOffset": 1.05, "closet": CLOSET}
# The slots a wearer actually looks at. The cap and the undershirt moving is not
# what "show me something else" means, and treating them as a pass is how the
# original measurement looked like 3 distinct outfits out of 4.
CORE = ("base", "bottoms", "footwear")


def ask(shown):
    body = dict(BODY)
    if shown:
        body["shown"] = shown
    req = urllib.request.Request(
        BASE + "/advice", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-OA-Client": "probe/reroll"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    shown, rows, repeats = None, [], 0
    for k in range(n):
        d = ask(shown)
        if not d.get("closetUsed"):
            print(f"[FAIL] request {k + 1} did not use the closet — is vLLM up?")
            return 1
        picks = {s: v for s, v in (d.get("picks") or {}).items() if v}
        core = {s: picks.get(s) for s in CORE}
        tag = "first ask" if shown is None else f"re-roll {k}"
        print(f"--- {tag} " + "-" * 40)
        for s in SLOTS:
            mark = ""
            if shown and shown.get(s) == picks.get(s) and picks.get(s):
                mark = "   << same"
            print(f"   {s:12} {LABEL.get(picks.get(s), '-')}{mark}")
        if shown is not None:
            same = [s for s in CORE if shown.get(s) and core.get(s) == shown.get(s)]
            if same:
                repeats += 1
                print(f"   REPEATED in {', '.join(same)}")
            first = (d.get("outfit_text") or "").splitlines()[:1]
            if first and "Same outfit again" in first[0]:
                print(f"   said so: {first[0]}")
        rows.append(core)
        shown = picks

    print("\n" + "=" * 60)
    uniq = len({json.dumps(r, sort_keys=True) for r in rows})
    print(f"distinct core outfits (base/bottoms/footwear) over {n} asks: {uniq}/{n}")
    print(f"re-rolls that repeated a core slot: {repeats}/{n - 1}")
    # The pass is `repeats`, NOT `uniq`. A four-bottom wardrobe legitimately comes
    # back round — the promise is that each answer differs from the one ON SCREEN,
    # not that it differs from every outfit ever shown. Demanding the latter is the
    # accumulating-avoid-list this design rejected, and it narrows a small wardrobe
    # to nothing by the third tap.
    ok = repeats == 0
    print("[PASS] every re-roll differed from what was on screen" if ok else
          "[FAIL] a re-roll came back with a core slot unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
