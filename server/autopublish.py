#!/usr/bin/env python3
"""autopublish.py — publish the newest green CI APK without a human at this box.

Run by outfit-autopublish.timer. Release step 3 (`publish_apk.py`) can only run here,
because dist/ is what the tailnet-only server hands the phone. A merge made anywhere
else (a cloud session, the GitHub app) therefore built fine and then went nowhere:
v1.47 sat unpublished on 2026-10-14 while the phone kept saying "up to date".

This polls instead of being pushed to. GitHub cannot reach the tailnet, and a
self-hosted runner was already rejected for the prepush gate.

Every safety gate stays in publish_apk.py (signing key, WEB_BUILD stamp, no
downgrade). This script only decides WHETHER to call it, and says so on Telegram.

State: the id of the last CI run that was dealt with, published or refused. A
refusal is recorded too, so a bad build alerts once rather than every tick. A
failure to reach GitHub is NOT recorded, so the next tick retries it.
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import publish_apk

ROOT = Path(__file__).resolve().parent.parent
REPO = "KoretyAutomate/OutfitAdvisor"
WORKFLOW = "build-apk.yml"
ARTIFACT = "outfit-advisor-debug"
NOTIFY = ROOT / "scripts" / "notify_telegram.sh"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "outfit-autopublish"
STATE = STATE_DIR / "last_run"
FAILS = STATE_DIR / "consecutive_failures"
ALERT_AFTER = 6  # ticks: an hour at the timer's 10 minutes
REMIND_EVERY = 144  # ticks: a day


def gh(*args: str) -> str:
    """Run gh; any failure raises, so the caller exits without recording state."""
    exe = shutil.which("gh")
    if exe is None:
        raise FileNotFoundError("gh is not on PATH")
    return subprocess.run([exe, *args], check=True, capture_output=True, text=True, timeout=300).stdout


def latest_green_run() -> dict | None:
    """The newest successful push build on main, or None if there is none."""
    runs = json.loads(gh("run", "list", "-R", REPO, "-w", WORKFLOW, "-b", "main", "-e", "push",
                         "-s", "success", "-L", "1", "--json", "databaseId,headSha,displayTitle"))
    return runs[0] if runs else None


def strip_version(title: str) -> str:
    """'Closet: mark the laundry (v1.47)' -> 'Closet: mark the laundry'."""
    return re.sub(r"\s*\(v\d+(\.\d+)*\)\s*$", "", title).strip()


def release_notes(sha: str, fallback: str) -> str:
    """The merged PR's title. A run's displayTitle is the merge commit's subject
    ("Merge pull request #31 from …"), which tells the user nothing."""
    try:
        prs = json.loads(gh("pr", "list", "-R", REPO, "--state", "merged", "--search", sha,
                            "--json", "title", "-L", "1"))
    except (subprocess.SubprocessError, ValueError):
        prs = []
    return strip_version(prs[0]["title"] if prs else fallback)


def published_code() -> int:
    try:
        return int(json.loads((publish_apk.DIST / "version.json").read_text()).get("versionCode", 0))
    except (OSError, ValueError):
        return 0


def decide(run_id: int, last_run: int | None, apk_code: int | None, live_code: int) -> str:
    """'skip' = this run was already dealt with; 'stale' = its APK is not newer than
    what the phone is offered; 'publish' = hand it to publish_apk.py.

    apk_code is None until the artifact has been downloaded; the caller downloads
    only when this says 'download'.
    """
    if last_run == run_id:
        return "skip"
    if apk_code is None:
        return "download"
    return "publish" if apk_code > live_code else "stale"


def notify(text: str) -> None:
    # A failed notification must not undo a publish that already happened.
    subprocess.run([str(NOTIFY), text], check=False, timeout=60)


def read_state() -> int | None:
    try:
        return int(STATE.read_text().strip())
    except (OSError, ValueError):
        return None


def write_state(run_id: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(f"{run_id}\n")
    os.replace(tmp, STATE)


def run() -> int:
    run_info = latest_green_run()
    if run_info is None:
        print("no green build on main")
        return 0
    run_id = int(run_info["databaseId"])
    if decide(run_id, read_state(), None, 0) == "skip":
        print(f"run {run_id} already handled")
        return 0

    with tempfile.TemporaryDirectory(prefix="outfit-autopublish-") as tmp:
        gh("run", "download", str(run_id), "-R", REPO, "-n", ARTIFACT, "-D", tmp)
        apk = Path(tmp) / "app-debug.apk"
        if not apk.is_file():
            raise FileNotFoundError(f"artifact {ARTIFACT} of run {run_id} has no app-debug.apk")
        code, name = publish_apk.apk_version(apk)
        live = published_code()
        if decide(run_id, None, code, live) == "stale":
            print(f"run {run_id}: versionCode {code} is not newer than published {live}")
            write_state(run_id)
            return 0

        # The refusals that will give the same answer on every retry are judged here,
        # so only they are recorded. Anything publish_apk.py fails on after these pass
        # (apksigner gone, disk full) is this machine's fault, and recording it would
        # skip the release for good.
        cert = publish_apk.apk_cert(apk)
        if cert is None:
            raise RuntimeError("apksigner could not verify the APK on this machine")
        refusal = refusal_reason(cert, publish_apk.apk_web_build(apk), name)
        if refusal:
            write_state(run_id)
            notify(f"⚠️ OutfitAdvisor {name} (CI run {run_id}, {run_info['headSha'][:7]}) "
                   f"was NOT published:\n{refusal}")
            return 1

        notes = release_notes(run_info["headSha"], run_info["displayTitle"])
        res = subprocess.run([sys.executable, str(Path(__file__).with_name("publish_apk.py")),
                              str(apk), "--notes", notes], capture_output=True, text=True, timeout=600)
    print(res.stdout, res.stderr, sep="")
    if res.returncode != 0:
        tail = (res.stderr.strip() or res.stdout.strip()).splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"publish_apk.py failed: {tail[0]}")
    write_state(run_id)
    notify(f"📲 OutfitAdvisor {name} published — open the app to update.\n{notes}")
    return 0


def refusal_reason(cert: str, web_build: str | None, version_name: str) -> str | None:
    """Why publish_apk.py would refuse this APK no matter how often it is retried."""
    if cert != publish_apk.EXPECTED_CERT:
        return f"signed with {cert[:16]}…, not the persistent key — it would wipe the app's data"
    if web_build != version_name:
        return f"bundled UI is WEB_BUILD {web_build} but the build is {version_name}"
    return None


def read_fails() -> int:
    try:
        return int(FAILS.read_text().strip())
    except (OSError, ValueError):
        return 0


def failure_alert(fails: int) -> bool:
    """One failed tick is noise (a blip in DNS, GitHub having a moment). Alert once
    the failures reach an hour, then once a day while they last."""
    return fails >= ALERT_AFTER and (fails - ALERT_AFTER) % REMIND_EVERY == 0


def guarded_run() -> int:
    """run(), with failures counted. Without this a timer that can no longer reach
    GitHub (token revoked, keyring locked after a reboot) fails silently forever,
    which is the very failure this script exists to end."""
    before = read_fails()
    try:
        rc = run()
    except (Exception, SystemExit) as e:  # publish_apk.apk_version sys.exit()s on a bad APK
        fails = before + 1
        FAILS.write_text(f"{fails}\n")
        print(f"autopublish failed ({fails} in a row): {e}", file=sys.stderr)
        if failure_alert(fails):
            notify(f"⚠️ OutfitAdvisor autopublish has failed {fails} times in a row "
                   f"— new builds are not reaching the phone.\n{e}")
        return 1
    if before >= ALERT_AFTER:
        notify("✅ OutfitAdvisor autopublish is working again.")
    FAILS.unlink(missing_ok=True)
    return rc


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # A manual run during a timer tick would otherwise download and publish twice.
    with open(STATE_DIR / "lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another autopublish is running")
            return 0
        return guarded_run()


if __name__ == "__main__":
    sys.exit(main())
