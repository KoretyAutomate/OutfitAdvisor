"""An automatic trip may not be invented — pinned across the DGX/web seam.

The user saw trips they had never planned, to cities that appear nowhere in
their calendar: "Petropavl, North Kazakhstan, KZ" (2026-08-20). Three
independent defects lined up, and all three live on the seam between
`llm.triage_event` and the web layer's `triageCandidate`:

  1. the server returns a `confidence` and the phone ignored it, so a guess
     added a trip as readily as a certainty;
  2. the LLM's `city` string went to a public geocoder unexamined;
  3. Open-Meteo's search is fuzzy and scoreless — it answers SOMETHING for
     almost any string — and `results[0]` was trusted. The distance test then
     passed *because* the answer was far away: the wronger the hit, the more
     certainly it became a trip.

The jsdom suite (app/tests/trip_autodetect.test.js) proves the decision table,
but it stubs both network calls, so it can only prove the web layer agrees with
itself. These read BOTH sources and check they still name the same things.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "app" / "www" / "index.html"
LLM = ROOT / "server" / "llm.py"


def _triage_candidate() -> str:
    src = INDEX.read_text()
    start = src.index("async function triageCandidate(c)")
    return src[start:src.index("\n/* ───────── trips", start)]


def test_the_server_still_returns_the_confidence_the_phone_gates_on():
    """A field the caller depends on cannot quietly stop being emitted."""
    src = LLM.read_text()
    body = src[src.index("async def triage_event("):]
    assert '"confidence":' in body, "triage_event no longer returns a confidence"


def test_an_unsure_answer_cannot_add_a_trip_by_itself():
    body = _triage_candidate()
    assert "TRIAGE_MIN_CONF" in body, "the confidence is read but never compared"
    assert re.search(r'confidence>=TRIAGE_MIN_CONF\)+\s*return\s*\{decision:"ask"', body), \
        "falling under the floor must ask, not add"
    floor = re.search(r"const TRIAGE_MIN_CONF=([\d.]+);", INDEX.read_text())
    assert floor and 0 < float(floor.group(1)) <= 1, "the floor must be a real probability"


def test_the_llm_city_is_examined_before_a_public_geocoder_sees_it():
    body = _triage_candidate()
    assert re.search(r"match\(/\\p\{L\}/gu\)", body), \
        "a city string with no letters must not reach Open-Meteo"


def test_a_geocode_that_answers_a_different_city_is_refused():
    """The Kazakhstan gate itself."""
    body = _triage_candidate()
    assert "geoNameMatches(t.city,g.place)" in body, \
        "the geocoded place is never compared with the city we asked about"
    ask = body.index("geoNameMatches(t.city,g.place)")
    assert 'decision:"ask"' in body[ask:ask + 200], \
        "a mismatch must degrade to asking, never to skipping or trusting"


def test_the_geocoder_is_asked_for_more_than_one_candidate():
    """With count=1 there is no way to step over a fuzzy top hit."""
    src = INDEX.read_text()
    geo = src[src.index("async function geocode(city)"):]
    geo = geo[:geo.index("\n}")]
    assert "count=1" not in geo, "one result leaves nothing to choose between"
    assert re.search(r"count=([2-9]|\d\d)", geo), "the search must request several results"
    assert "geoNameMatches" in geo, "the returned name is never compared with the query"
