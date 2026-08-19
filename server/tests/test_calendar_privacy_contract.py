"""A shared calendar must never be read — pinned across the JS/Kotlin seam.

The user's rule (2026-08-19) is absolute: a calendar somebody else shared into
this account is not read, whatever the trip picker's saved selection says.

Honouring it needs the native side, and that is exactly where a test is worth
having. @ebarooni/capacitor-calendar's Android `listCalendars` selects only
_ID, CALENDAR_DISPLAY_NAME and CALENDAR_COLOR — nothing about who owns the
calendar — so the app reads the ownership columns itself in OutfitAlarmPlugin
and the web layer filters on the `shared` flag that comes back.

The jsdom suite (app/tests/trips_math.test.js) proves the FILTERING is right,
but it necessarily fakes the plugin, so it can only prove the web layer agrees
with the web layer's own idea of the plugin. That is the precise shape of the
2026-08-13 bug, where the app sent {from,to} to a plugin whose signature is
{startDate,endDate} and the mock agreed with the app rather than with reality.
So this reads BOTH sources and checks they name the same things.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "app" / "www" / "index.html"
PLUGIN = (
    ROOT / "app" / "android" / "app" / "src" / "main" / "java"
    / "com" / "korety" / "outfitadvisor" / "OutfitAlarmPlugin.kt"
)


def _kotlin_list_calendars() -> str:
    """The body of the native listCalendars method."""
    src = PLUGIN.read_text()
    start = src.index("fun listCalendars(call: PluginCall)")
    # Up to the next method declaration, whatever it turns out to be.
    rest = src[start:]
    end = rest.find("\n    @PluginMethod")
    if end == -1:
        end = rest.find("\n    private fun ")
    assert end > 0, "could not delimit listCalendars"
    return rest[:end]


def _js_load_calendars() -> str:
    src = INDEX.read_text()
    start = src.index("async function loadCalendars()")
    end = src.index("function calLabel(", start)
    return src[start:end]


def test_the_native_side_reads_the_columns_that_reveal_sharing():
    """Ownership cannot be inferred from a calendar's name — these columns are it."""
    body = _kotlin_list_calendars()
    for column in ("OWNER_ACCOUNT", "ACCOUNT_NAME", "CALENDAR_ACCESS_LEVEL"):
        assert f"CalendarContract.Calendars.{column}" in body, column


def test_both_ownership_tests_are_applied_not_just_one():
    """Owner mismatch and guest access level each catch cases the other misses.

    A holiday feed can be owned by another account at owner-level access; a
    calendar you were made an editor on keeps your account name. Dropping
    either test reopens a hole, so the OR is the contract.
    """
    body = _kotlin_list_calendars()
    assert "CAL_ACCESS_OWNER" in body, "access level is never compared"
    assert re.search(r'!owner\.equals\(account,\s*ignoreCase', body), "owner is never compared to the account"
    assert re.search(r'put\(\s*"shared",\s*\w+\s*\|\|\s*\w+\s*\)', body), \
        "the shared flag must be the OR of both tests"


def test_the_native_side_never_reads_event_rows():
    """This method exists to LIST calendars; event text stays where it is."""
    body = _kotlin_list_calendars()
    assert "CalendarContract.Events" not in body
    assert "CalendarContract.Instances" not in body


def test_permission_is_checked_rather_than_assumed():
    body = _kotlin_list_calendars()
    assert "Manifest.permission.READ_CALENDAR" in body
    assert "call.reject" in body, "a denied permission must fail, not return an empty list"


def test_the_web_layer_reads_exactly_the_keys_the_plugin_emits():
    """The seam the jsdom mock cannot police: key names must match on both sides."""
    kotlin = _kotlin_list_calendars()
    emitted = set(re.findall(r'\.put\(\s*"(\w+)"', kotlin))
    assert {"id", "title", "shared", "sharedBy"} <= emitted, emitted
    assert '.put("calendars"' in kotlin, "the payload key the web layer destructures"

    js = _js_load_calendars()
    assert "Plugins.OutfitAlarm" in js
    for key in ("calendars", "shared", "sharedBy", "title", "id"):
        assert key in js, key


def test_the_web_layer_has_no_second_calendar_lister():
    """One source of truth: the plugin's own lister cannot say what is shared.

    Falling back to it would look like it worked and would read shared
    calendars, which is the failure this whole contract exists to prevent.
    """
    src = INDEX.read_text()
    assert "CapacitorCalendar.listCalendars" not in src
    assert re.search(r"Cal\s*&&\s*Cal\.listCalendars", src) is None


def test_the_scan_filters_events_through_a_positive_allow_list():
    """A negative filter degrades to 'read everything' the moment it is empty."""
    src = INDEX.read_text()
    scan = src[src.index("async function scanCalendar()"):]
    scan = scan[:scan.index("\nasync function ") if "\nasync function " in scan else len(scan)]
    assert "calAvail=await loadCalendars()" in scan, "the allow-list must be rebuilt from the device each scan"
    assert re.search(r"filter\(e=>allow\.has\(String\(e\.calendarId\)\)\)", scan), \
        "events must be filtered by an allow-list, not by an exclusion that can be empty"
    assert "!allow||" not in scan, "an 'or no filter' escape hatch reads every calendar"


def test_unselect_all_exists_and_means_read_nothing():
    """Before this, an empty tick list meant 'all' — unticking read everything."""
    src = INDEX.read_text()
    assert 'id="calNone"' in src, "the picker needs an Unselect all control"
    assert '$("calNone").onclick' in src, "and it has to be wired to something"
    save = src[src.index("async function saveCalSel()"):]
    save = save[:save.index("\n}") + 2]
    assert re.search(r'!picked\.length.*calMode="none"', save, re.S), \
        "an empty selection must store the none mode, not fall through to all"
