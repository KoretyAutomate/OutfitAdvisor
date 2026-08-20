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


def test_a_geocode_that_answers_a_different_place_is_refused():
    """The Kazakhstan gate itself.

    It must be geoPlaceExact — the STRICT test — and neither of the loose ones.
    geoNameMatches tests the city HEAD alone, so "Cambridge, UK" answered with
    Cambridge, Massachusetts passes it: 5,000 km out, approved by the distance test
    precisely because the answer is far away. geoPlaceMatches closes that, but it
    still lets a name grow by whole words, and growing by whole words is not only
    how an alias is spelled — it is how two DIFFERENT cities are told apart.
    Frankfurt (Oder) is 500 km from Frankfurt am Main, York New Salem is not York.
    A human reading a typed-city answer can see which; nobody is reading this one.
    """
    body = _triage_candidate()
    assert "geoPlaceExact(t.city,g)" in body, \
        "the geocoded place is never compared, strictly, with what we asked"
    assert "geoPlaceMatches(t.city" not in body and "geoNameMatches(t.city" not in body, \
        "the automatic path must not fall back on a loose, prefix-tolerant test"
    ask = body.index("geoPlaceExact(t.city,g)")
    assert 'decision:"ask"' in body[ask:ask + 200], \
        "a mismatch must degrade to asking, never to skipping or trusting"


def test_the_automatic_path_demands_the_same_name_not_a_prefix():
    """A trip nobody agreed to may only go to the name that was asked for.

    An extended name is not refused outright, it is ASKED about — one confirmation
    tap, which is what this app pays instead of packing for the wrong Frankfurt.
    """
    src = INDEX.read_text()
    exact = src[src.index("function geoNameExact(asked,got)"):]
    exact = exact[:exact.index("\n}")]
    assert re.search(r"\bq===n\b", exact), "the strict test must compare whole names"
    assert "every(" not in exact and "startsWith" not in exact, \
        "a name that merely extends another must not satisfy the strict test"
    assert "GEO_ALIAS" in exact, \
        "two spellings of one place need an explicit alias, not a prefix rule"
    assert re.search(r"const GEO_ALIAS=\[\[", src), "the alias table must be a real table"


def test_a_region_qualifier_is_compared_and_never_dropped():
    """The whole destination string is judged, not the token before the comma."""
    src = INDEX.read_text()
    place = src[src.index("function geoPlaceBy(nameTest,asked,got)"):]
    place = place[:place.index("\n}")]
    assert "geoRegionMatches" in place, "the qualifier is parsed but never compared"
    assert re.search(r"geoParts\(asked\)\.slice\(1\)\.every\(", place), \
        "EVERY qualifier must be satisfied — one unmatched qualifier is a refusal"
    assert "nameTest(asked,place)" in place, \
        "the head test is chosen by the caller — strict for the automatic path"
    assert re.search(r"geoPlaceExact=\(asked,got\)=>geoPlaceBy\(geoNameExact,", src), \
        "the strict wrapper must pair the qualifier rule with the strict head test"
    region = src[src.index("function geoRegionMatches(q,regions)"):]
    region = region[:region.index("\n}")]
    assert "some(" in region, "a qualifier must be checked against the geocoder's own fields"
    geo = src[src.index("async function geocode(city)"):]
    geo = geo[:geo.index("\n}")]
    assert "regions:[" in geo, \
        "geocode must hand back the region fields the qualifier test needs"


def test_the_geocoder_is_asked_for_more_than_one_candidate():
    """With count=1 there is no way to step over a fuzzy top hit."""
    src = INDEX.read_text()
    geo = src[src.index("async function geocode(city)"):]
    geo = geo[:geo.index("\n}")]
    assert "count=1" not in geo, "one result leaves nothing to choose between"
    assert re.search(r"count=([2-9]|\d\d)", geo), "the search must request several results"
    assert "geoPlaceMatches" in geo, "the returned place is never compared with the query"
    assert geo.index("geoPlaceExact") < geo.index("geoPlaceMatches"), \
        "a result NAMED the city must be preferred to one that merely extends it"
