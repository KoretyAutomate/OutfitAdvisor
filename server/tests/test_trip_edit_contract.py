"""Editing a trip must change it — pinned where the fix is easy to undo.

The Edit button exposed two ways for the trip sheet to lie (2026-08-20):

  1. Delete removed the trip but not the calendar event behind it, so the next
     scan — which skips only events already in `trips` or in `tripsDismissed` —
     judged it afresh and auto-added the same trip straight back.
  2. The sheet opens on the trip's existing lat/lon/place. Retyping the city and
     saving without a fresh Find passed validation on the stale coordinates, so
     the destination silently stayed put while its name changed.

app/tests/trip_edit.test.js proves the behaviour in jsdom — it deletes a scanned
trip and rescans the same event, and it types over the city and tries to save.
That suite is not run by the pre-push gate, so these read the source and check
the two mechanisms are still wired: a regression here is a one-line deletion.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "app" / "www" / "index.html"


def _handler(name: str) -> str:
    """The body of an `$("<id>").onclick=async()=>{...}` handler."""
    src = INDEX.read_text()
    start = src.index(f'$("{name}").onclick=')
    end = src.index("\n};", start)
    return src[start:end]


def _function(sig: str) -> str:
    src = INDEX.read_text()
    start = src.index(sig)
    return src[start:src.index("\n}", start)]


def test_deleting_a_trip_dismisses_the_calendar_event_it_came_from():
    body = _handler("tsDel")
    assert "tripsDismissed" in body, \
        "Delete no longer records the calendar event — the next scan re-adds the trip"
    assert re.search(r"tripsDismissed\.push\(\s*t\.calId\s*\)", body), \
        "the dismissed list must receive the trip's OWN calendar id"


def test_the_scan_still_skips_what_delete_recorded():
    """The other half of the seam: dismissal only works if the scan honours it."""
    body = _function("async function scanCalendar()")
    assert re.search(r"!tripsDismissed\.includes\(c\.calId\)", body), \
        "the scan stopped filtering on tripsDismissed, so Delete cannot hold"


def test_a_trip_with_no_calendar_event_is_not_pushed_as_undefined():
    body = _handler("tsDel")
    assert re.search(r"if\(t\.calId&&", body), \
        "a trip without a calId must not put undefined in the dismissed list"


def test_editing_the_city_text_drops_the_coordinates_it_no_longer_names():
    src = INDEX.read_text()
    assert 'addEventListener("input",syncCityToGeo)' in src, \
        "nothing watches the city box, so an edited city keeps the old geocode"
    body = _function("function syncCityToGeo()")
    assert re.search(r"tsheet\.trip\.lat=null;\s*tsheet\.trip\.lon=null", body), \
        "a city that no longer matches must clear lat/lon — that is what Save gates on"
    assert "tsheet.geo" in body, "the comparison needs the place the coordinates came from"


def test_save_still_refuses_a_trip_with_no_coordinates():
    """Clearing lat/lon only helps because Save is gated on them."""
    body = _handler("tsSave")
    assert re.search(r"if\(t\.lat==null\|\|t\.lon==null\)", body), \
        "Save stopped checking for coordinates, so a cleared geocode saves anyway"


def test_a_freshly_picked_city_records_where_the_coordinates_came_from():
    body = _function("function pickCity(i)")
    assert "tsheet.geo=" in body, \
        "picking a match must record the city text, or the next keystroke drops it"
