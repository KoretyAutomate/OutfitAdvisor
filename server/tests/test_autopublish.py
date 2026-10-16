"""autopublish.py (2026-10-14): when a green CI build reaches the phone, and when it must not."""
import subprocess
import time
from pathlib import Path

import pytest

import autopublish


def test_a_run_already_handled_is_skipped_before_any_download():
    assert autopublish.decide(38591816842, 38591816842, None, 48) == "skip"


def test_a_new_run_is_downloaded_first():
    assert autopublish.decide(2, 1, None, 48) == "download"
    assert autopublish.decide(2, None, None, 48) == "download"


def test_a_newer_version_is_published():
    assert autopublish.decide(2, 1, 49, 48) == "publish"


def test_a_build_that_did_not_bump_the_version_is_not_republished():
    """Also the case where someone already published that release by hand."""
    assert autopublish.decide(2, 1, 48, 48) == "stale"


def test_an_older_build_is_never_offered():
    assert autopublish.decide(2, 1, 47, 48) == "stale"


def test_release_notes_drop_the_version_suffix():
    assert autopublish.strip_version(
        "Closet: mark by hand what is still in the laundry (v1.47)"
    ) == "Closet: mark by hand what is still in the laundry"
    assert autopublish.strip_version("Office days (v1.45) and more") == "Office days (v1.45) and more"


def test_release_notes_fall_back_to_the_commit_when_no_pr_is_found(monkeypatch):
    monkeypatch.setattr(autopublish, "gh", lambda *a: "[]")
    assert autopublish.release_notes("abc", "Fix the thing (v1.48)") == "Fix the thing"


def test_state_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(autopublish, "STATE_DIR", tmp_path)
    monkeypatch.setattr(autopublish, "STATE", tmp_path / "last_run")
    assert autopublish.read_state() is None
    autopublish.write_state(123)
    assert autopublish.read_state() == 123


def test_only_a_wrong_key_or_stale_page_counts_as_a_permanent_refusal():
    good = autopublish.publish_apk.EXPECTED_CERT
    assert autopublish.refusal_reason(good, "1.47", "1.47") is None
    assert "persistent key" in autopublish.refusal_reason("0" * 64, "1.47", "1.47")
    assert "WEB_BUILD 1.46" in autopublish.refusal_reason(good, "1.46", "1.47")
    assert "WEB_BUILD None" in autopublish.refusal_reason(good, None, "1.47")


def test_failures_alert_after_an_hour_then_daily_not_every_tick():
    alerts = [n for n in range(1, 400) if autopublish.failure_alert(n)]
    assert alerts == [6, 150, 294]


def _isolate(monkeypatch, tmp_path, sent):
    monkeypatch.setattr(autopublish, "STATE_DIR", tmp_path)
    monkeypatch.setattr(autopublish, "FAILS", tmp_path / "consecutive_failures")
    monkeypatch.setattr(autopublish, "notify", sent.append)


def test_github_unreachable_is_counted_and_alerted_once_then_recovery_is_announced(monkeypatch, tmp_path):
    sent: list[str] = []
    _isolate(monkeypatch, tmp_path, sent)

    def down():
        raise RuntimeError("gh: HTTP 401")
    monkeypatch.setattr(autopublish, "run", down)
    for _ in range(7):
        assert autopublish.guarded_run() == 1
    assert len(sent) == 1 and "6 times" in sent[0]

    monkeypatch.setattr(autopublish, "run", lambda: 0)
    assert autopublish.guarded_run() == 0
    assert "working again" in sent[-1]
    assert not (tmp_path / "consecutive_failures").exists()


def test_a_bad_apk_that_exits_is_a_counted_failure_not_a_crash(monkeypatch, tmp_path):
    sent: list[str] = []
    _isolate(monkeypatch, tmp_path, sent)

    def bad():
        raise SystemExit("versionCode not found in the APK manifest")
    monkeypatch.setattr(autopublish, "run", bad)
    assert autopublish.guarded_run() == 1
    assert autopublish.read_fails() == 1


def test_a_spent_budget_stops_the_next_step_but_never_the_alert(monkeypatch):
    """systemd's TimeoutStartSec kills the whole unit; the budget must run out first
    so guarded_run() can still count the failure and send the alert (Codex, 2026-10-16)."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: calls.append((argv[0], kw["timeout"])))
    monkeypatch.setattr(autopublish, "_deadline", time.monotonic() - 1)
    with pytest.raises(TimeoutError):
        autopublish._run(["gh", "run", "list"], timeout=300)
    autopublish.notify("budget spent")
    assert calls == [(str(autopublish.NOTIFY), 60)]


def test_a_step_never_outlives_the_budget(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: seen.append(kw["timeout"]))
    monkeypatch.setattr(autopublish, "_deadline", time.monotonic() + 30)
    autopublish._run(["gh"], timeout=300)
    assert 0 < seen[0] <= 30


def test_the_budget_leaves_room_inside_the_unit_timeout():
    unit = (Path(autopublish.__file__).parent / "deploy" / "outfit-autopublish.service").read_text()
    stop = int(next(ln.split("=")[1] for ln in unit.splitlines() if ln.startswith("TimeoutStartSec=")))
    # + apksigner's own 120s, + one Telegram call
    assert stop > autopublish.BUDGET_S + 120 + 60
