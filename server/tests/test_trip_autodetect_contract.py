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
    # What is forbidden is the loose test being the GATE on the geocoder's answer.
    # `geoPlaceMatches(t.city, g)` would approve Cambridge, Massachusetts for
    # "Cambridge, UK" — 5,000 km out, and the distance test passes precisely because
    # it is far. Comparing the model's city with a place the USER TAUGHT is a
    # different question with no geocoder in it: a miss there sends the city down
    # this same strict road, it does not approve anything (2026-08-24).
    assert "geoPlaceMatches(t.city,g)" not in body.replace(" ", ""), \
        "the geocoder's answer must not be approved by the loose test"
    assert "geoNameMatches(t.city" not in body, \
        "the automatic path must not fall back on a head-only test"
    ask = body.index("geoPlaceExact(t.city,g)")
    # Generous window: the branch carries an explanatory comment between the test
    # and the return, and a tight window fails on prose rather than on behaviour.
    assert 'decision:"ask"' in body[ask:ask + 600], \
        "a mismatch must degrade to asking, never to skipping or trusting"
    # The reason must NOT name the place that came back. The geocoder resolves codes
    # out of an airport table, so quoting it prints "Petropavl, North Kazakhstan" —
    # which reads as the app proposing Kazakhstan. That message, not the trip logic,
    # is what the user reported twice while the logic was already correct.
    reason = body[ask:ask + 600]
    assert "g.place" not in reason, \
        "the refusal must not repeat the wrongly-geocoded place back to the user"


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
    """With count=1 there is no way to step over a fuzzy top hit.

    The width is also load-bearing beyond that. Measured against the live API on
    2026-08-23 from the user's own home area: "Princeton" ranks New Jersey 6th and
    "Lawrenceville" ranks New Jersey 8th, behind bigger namesakes in other states.
    At count=5 the user's own town was not in the list AT ALL, so no amount of
    choosing among the answers could have found it.
    """
    src = INDEX.read_text()
    geo = src[src.index("async function geocode(city)"):]
    geo = geo[:geo.index("\n}")]
    assert "count=1" not in geo, "one result leaves nothing to choose between"
    # The count is a named constant now, so resolve it rather than matching digits.
    m = re.search(r"count=\$\{(\w+)\}", geo)
    assert m, "the search must request several results"
    decl = re.search(rf"const {m.group(1)}\s*=\s*(\d+)", src)
    assert decl, f"{m.group(1)} is used but never declared"
    assert int(decl.group(1)) >= 10, (
        "a short list cannot reach the user's own town: New Jersey ranks 6th for "
        f"'Princeton' and 8th for 'Lawrenceville', but count={decl.group(1)}"
    )
    assert "geoPlaceMatches" in geo, "the returned place is never compared with the query"
    assert geo.index("geoPlaceExact") < geo.index("geoPlaceMatches"), \
        "a result NAMED the city must be preferred to one that merely extends it"


def test_a_building_code_never_reaches_the_geocoder():
    """PPK is an office on Princeton Pike, NJ. Open-Meteo says Kazakhstan.

    Verified against the live API on 2026-08-23: the geocoder resolves IATA codes,
    so `PPK` returns Petropavl, Kazakhstan and `LVL` returns Lawrenceville,
    VIRGINIA — the user's Lawrenceville is in New Jersey, 9 km from home. Both
    answer with total confidence and no score, and the distance test then CONFIRMS
    the trip precisely because the answer is far away.

    A work calendar puts exactly these strings in the location field, so this is
    the common case, not an exotic one.
    """
    src = INDEX.read_text()
    # The gate is the strict NAME test: PPK comes back named Petropavl, and a place
    # that is not the place we asked about has not been placed.
    body = _triage_candidate()
    assert "geoPlaceExact(t.city,g)" in body, \
        "nothing checks that the geocoder answered the name it was asked"

    # No SHAPE rule, in either direction. `[A-Z0-9]{2,4}` refuses a pasted "ROME";
    # making it case-insensitive additionally refuses Rome, Oslo, Nice, Lyon, Bath,
    # York, Kobe, Pisa, Graz, Cork, Riga, Bonn, Linz and Gent. Every one is a real
    # city of four letters or fewer, so a shape rule is wrong more often than right.
    # Both were tried and both were reverted; this keeps them out.
    assert "geoLooksLikeCode" not in src, \
        "a code must be recognised by the ANSWER, never by the shape of the query"

    # The user-facing picker refuses a short query that nothing came back named
    # after, which is what catches lowercase codes without touching short cities.
    assert re.search(r"const geoUnplaceableShort=", src), \
        "nothing catches a code the user types into the picker"
    short = src[src.index("const geoUnplaceableShort="):]
    short = short[:short.index(";\n")]
    assert "geoPlaceMatches" in short, "the test must compare the answer with the query"
    assert "GEO_SHORT" in short, "the test must be bounded to short queries"
    bound = re.search(r"const GEO_SHORT=(\d+)", src)
    assert bound and int(bound.group(1)) <= 5, \
        "a long unmatched string is a typo, not a code — saying 'code' there misleads"
