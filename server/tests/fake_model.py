"""A stand-in for the model behind /advice (2026-10-11 refactor).

`install(monkeypatch, answers, verdicts)` replaces the transport for the advisor and
the stylist. The advisor gets `answers` in order (dicts are JSON-encoded; None means
the model did not answer); the stylist gets `verdicts`. `seen` records the user
message of every advisor call — the outfit prompt first, then each revision note —
and every system message, so a test can read exactly what the model was told.
"""
import json

import advisor
import chooser
import stylist


def outfit(**picks) -> dict:
    """An advisor answer: picks given by id (or handle), a line per worn slot."""
    full = {s: None for s in ("inner", "base", "mid", "outer", "bottoms", "footwear", "accessories")}
    full.update(picks)
    return {"look": "A simple, sensible outfit.", "picks": full,
            "lines": {s: f"{s} chosen" for s, v in full.items() if v},
            "missing": [], "tip": "Have a good day."}


def choice(n: int = 1, reason: str = "", tip: str = "Have a good day.", **lines) -> dict:
    """A chooser answer (funnel path): outfit n of the survivors, 0 for none."""
    return {"choice": n, "reason": reason, "look": "A sensible outfit.", "lines": lines, "tip": tip}


def install(monkeypatch, answers: list, verdicts: list | None = None, choices: list | None = None) -> dict:
    seen: dict = {"prompts": [], "system": [], "stylist": 0, "calls": 0, "chooser": []}
    queue, reviews, picks = list(answers), list(verdicts or []), list(choices or [])

    async def fake_chooser(messages, max_tokens, timeout=45, temperature=0.4, **kw):
        seen["chooser"].append(messages[-1]["content"])
        if not picks:
            return None
        a = picks.pop(0)
        return a if a is None or isinstance(a, str) else json.dumps(a)


    async def fake_advisor(messages, max_tokens, timeout=45, temperature=0.4, **kw):
        seen["calls"] += 1
        seen["temperature"] = temperature
        seen["system"].append(messages[0]["content"])
        seen["prompts"].append(messages[-1]["content"])
        if not queue:
            return None
        a = queue.pop(0)
        return a if a is None or isinstance(a, str) else json.dumps(a)

    async def fake_stylist(messages, max_tokens, timeout=45, **kw):
        seen["stylist"] += 1
        return json.dumps(reviews.pop(0)) if reviews else None

    monkeypatch.setattr(advisor, "_chat", fake_advisor)
    monkeypatch.setattr(stylist, "_chat", fake_stylist)
    monkeypatch.setattr(chooser, "_chat", fake_chooser)
    return seen
