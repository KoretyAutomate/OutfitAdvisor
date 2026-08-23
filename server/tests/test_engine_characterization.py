"""Characterization tests for engine.recommend() and apply_temp_offset().

WHY THIS EXISTS
    `recommend()` is a 136-line threshold ladder with no unit coverage, and it is
    a declared TWIN of recommend() in app/www/index.html — the app's offline
    fallback. A silent behaviour change here desynchronises the two, so the same
    forecast yields a different outfit depending on whether the DGX was
    reachable. That class of bug is invisible in review.

    So: before refactoring the function, its CURRENT output was frozen into
    golden_engine.json. These tests assert the refactor is behaviour-preserving.
    They are not a specification — they pin what the code did on 2026-07-29,
    including anything questionable. If a change here is DELIBERATE, regenerate
    with `python3 server/tests/gen_engine_golden.py` and review the diff:
    a golden diff is the blast radius, and the JS twin must move with it.

    Runs fully offline — no server, unlike check_packing_live.py.
"""

import json
from pathlib import Path

import pytest

import engine

GOLDEN = Path(__file__).parent / "golden_engine.json"

if not GOLDEN.exists():  # pragma: no cover - the generator must run first
    pytest.skip("golden_engine.json missing — run gen_engine_golden.py", allow_module_level=True)

CASES = json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("case", CASES["recommend"], ids=lambda c: c["id"])
def test_recommend_matches_golden(case):
    assert engine.recommend(case["w"], case["gender"], case["style"]) == case["want"]


@pytest.mark.parametrize("case", CASES["offset"], ids=lambda c: c["id"])
def test_apply_temp_offset_matches_golden(case):
    assert engine.apply_temp_offset(case["w"], case["offset"]) == case["want"]


def test_every_output_key_present():
    """recommend() must always return the full 6+1 contract — outfit_to_bullets
    indexes these unconditionally, so a missing key is a KeyError in production."""
    required = {"inner", "base", "mid", "outer", "bottoms", "footwear", "accessories", "tip"}
    for case in CASES["recommend"]:
        got = engine.recommend(case["w"], case["gender"], case["style"])
        assert required <= set(got), f"{case['id']} missing {required - set(got)}"


def test_offset_sign_is_not_inverted():
    """A positive offset must make the engine think it is WARMER (dress lighter).
    engine.py calls getting this backwards 'a silent failure' — so assert it."""
    w = {"lo": 10, "hi": 14, "feelsLo": 10, "feelsHi": 14, "morning": 10, "midday": 12, "evening": 11}
    assert engine.apply_temp_offset(w, 3)["morning"] == 13
    assert engine.apply_temp_offset(w, -3)["morning"] == 7


def test_offset_rounds_half_up_like_js():
    """math.floor(x + 0.5), not round() — Python's round() is banker's rounding
    and would disagree with JS Math.round() on exact .5, which is reachable
    (five 'a bit warm' taps = offset 1.5)."""
    w = {"morning": 10, "lo": 10, "hi": 10, "feelsLo": 10, "feelsHi": 10, "midday": 10, "evening": 10}
    assert engine.apply_temp_offset(w, 1.5)["morning"] == 12  # not 11 (banker's)
    assert engine.apply_temp_offset(w, 0.5)["morning"] == 11  # not 10 (banker's)
