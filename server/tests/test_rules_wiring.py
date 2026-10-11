"""The rules are wired into the generator, not just defined (2026-08-24).

Every unit in test_rules.py can be right while the outfit path never calls any of
them — which is exactly how /classify came to ask for `group` and `roles` and throw
both away one line before they reached the phone, twice, independently. So these
read the seams.
"""
import re
from pathlib import Path

import advisor as advisor_mod
import check as check_mod
import fallback as fallback_mod
import rules

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "app" / "www" / "index.html"
# Since the 2026-10-11 refactor: advisor.py asks, check.py judges, fallback.py is
# the last resort.
ADVISOR_PY = Path(advisor_mod.__file__)
CHECK_PY = Path(check_mod.__file__)
FALLBACK_PY = Path(fallback_mod.__file__)


def test_the_generator_is_given_the_rules():
    src = ADVISOR_PY.read_text()
    prompt = src[src.index("def prompt("):]
    prompt = prompt[:prompt.index("\n\n\n")]
    assert "rules.prompt_block" in prompt, "the rules never reach the prompt"


def test_the_picks_are_CHECKED_against_the_rules():
    """The prompt is a hint. The check makes the ban a ban: a broken rule is a HARD
    issue the advisor is told about, and the fallback clears the blamed slot if its
    best answer still breaks it."""
    assert "rules.violations(" in CHECK_PY.read_text(), "nothing verifies the rules were followed"
    fb = FALLBACK_PY.read_text()
    assert 'out[broken[0]["slot"]] = None' in fb, \
        "a last failure must clear the slot rather than serve a banned outfit"


def test_advice_passes_the_phones_rules_through():
    """The rules travel in a Prefs object as of 2026-08-27 — everything the WEARER
    told us, as opposed to what the weather did, in one argument. Each of them has
    to reach both the prompt and the validation, and threading them separately is
    how a flag ends up honoured in one and ignored in the other."""
    app_src = (ROOT / "server" / "app.py").read_text()
    assert re.search(r"Prefs\.of\(rules\.clean_rules\(req\.rules\)", app_src), \
        "the request's rules never reach the generator"
    assert re.search(r"advisor\.dress\([^)]*prefs", app_src, re.S), \
        "the preferences are built but never passed"


def test_the_phone_sends_them():
    src = INDEX.read_text()
    body = src[src.index("async function getAdvice(lat,lon)"):]
    body = body[:body.index("\nasync function ")]
    assert "body.rules" in body, "the phone never sends its rules"


def test_the_phone_and_the_server_agree_on_the_rule_shape():
    """A field the phone sends under another name is a rule that silently never fires."""
    src = INDEX.read_text()
    sent = src[src.index("body.rules=userRules.map"):]
    sent = sent[:sent.index(";")]
    for field in ("kind", "a", "b"):
        assert f"{field}:" in sent, f"the phone does not send `{field}`"
    # And those are the names clean_rule reads.
    assert rules.clean_rule({"kind": "avoid_pair", "a": {"type": "t_shirt"},
                             "b": {"type": "jeans"}}) is not None


def test_a_rule_the_server_cannot_enforce_never_reaches_storage():
    """/rule validates before returning, so the phone cannot hold a dead rule."""
    src = (ROOT / "server" / "ruleparse.py").read_text()
    body = src[src.index("async def parse_rule("):]
    body = body[:body.index("\ndef ")] if "\ndef " in body else body
    assert "rules.clean_rule(" in body, \
        "a parsed rule must be validated before it is handed back"
    assert "return None" in body, "an unenforceable rule must be refused, not stored"
