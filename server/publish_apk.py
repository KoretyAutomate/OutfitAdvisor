#!/usr/bin/env python3
"""publish_apk.py — make a CI-built APK the one the app offers as an update.

    python3 server/publish_apk.py /path/to/app-debug.apk [--notes "what changed"]

Copies the APK into dist/ and writes dist/version.json, which GET /version serves.

The version numbers are read from INSIDE the APK's binary AndroidManifest.xml, not
from build.gradle. The first draft read build.gradle and was wrong: the working
tree moves on after a build, so publishing a previously-built APK cheerfully
claimed whatever version the tree happened to say. That produces an update the
phone installs and then still sees as old — the banner returns forever. The APK is
the only honest source for what the APK actually is.

SIGNING GATE: an APK signed with a different key cannot update the installed app;
Android refuses it and the only way forward is uninstall-first, which wipes
settings and closet photos. That is the exact failure this project already fixed
once (persistent keystore + CI cert-drift gate, 2026-07-11). This script refuses
to publish an APK whose signing cert is not the expected one, so a mis-signed
build can never reach the phone as an "update".
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# The persistent debug key every build since 2026-07-11 is signed with. Same value
# the CI cert-drift gate asserts (.github/workflows/build-apk.yml).
EXPECTED_CERT = "067bcb5f27b863b77d75e8dff39b9dc78b7d5998735ece815eb7cf6decd84113"


def _axml_strings(blob: bytes, off: int) -> list[str]:
    """Decode an AXML string-pool chunk into a list of strings."""
    count = struct.unpack_from("<I", blob, off + 8)[0]
    flags = struct.unpack_from("<I", blob, off + 16)[0]
    strings_start = struct.unpack_from("<I", blob, off + 20)[0]
    utf8 = bool(flags & (1 << 8))
    out = []
    for i in range(count):
        so = struct.unpack_from("<I", blob, off + 28 + i * 4)[0]
        p = off + strings_start + so
        if utf8:
            # two varint-ish lengths (char count, then byte count), then bytes
            n = blob[p]
            p += 2 if n & 0x80 else 1
            n = blob[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | blob[p + 1]
                p += 2
            else:
                p += 1
            out.append(blob[p : p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", blob, p)[0]
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", blob, p + 2)[0]
                p += 4
            else:
                p += 2
            out.append(blob[p : p + n * 2].decode("utf-16-le", "replace"))
    return out


def apk_version(apk: Path) -> tuple[int, str]:
    """versionCode / versionName straight out of the APK's binary manifest.

    Minimal AXML walk: find the string pool, then the <manifest> START_ELEMENT,
    then its android:versionCode / android:versionName attributes. We only need
    two attributes off one element, so this stays far short of a full parser.
    """
    with zipfile.ZipFile(apk) as z:
        blob = z.read("AndroidManifest.xml")

    CHUNK_STRINGS, CHUNK_RESMAP, CHUNK_START_ELEM = 0x0001, 0x0180, 0x0102
    # AAPT2 does not store the NAME of a framework attribute as a string — the
    # string-pool slot is empty and the real identity is a resource id in the
    # resource-map chunk, parallel-indexed to the pool. Matching on the string
    # alone finds nothing, which is exactly how the first attempt failed.
    ATTR_VERSION_CODE, ATTR_VERSION_NAME = 0x0101021B, 0x0101021C

    strings: list[str] = []
    resmap: list[int] = []
    off, end = 8, len(blob)  # skip the 8-byte file header
    while off + 8 <= end:
        ctype, hsize, csize = (
            struct.unpack_from("<H", blob, off)[0],
            struct.unpack_from("<H", blob, off + 2)[0],
            struct.unpack_from("<I", blob, off + 4)[0],
        )
        if csize <= 0 or off + csize > end:
            break
        if ctype == CHUNK_STRINGS:
            strings = _axml_strings(blob, off)
        elif ctype == CHUNK_RESMAP:
            n = (csize - hsize) // 4
            resmap = list(struct.unpack_from("<%dI" % n, blob, off + hsize))
        elif ctype == CHUNK_START_ELEM and strings:
            name_i = struct.unpack_from("<I", blob, off + 20)[0]
            if name_i < len(strings) and strings[name_i] == "manifest":
                attr_start = struct.unpack_from("<H", blob, off + 24)[0]
                attr_size = struct.unpack_from("<H", blob, off + 26)[0]
                attr_count = struct.unpack_from("<H", blob, off + 28)[0]
                code, vname = None, None
                for i in range(attr_count):
                    # attributeStart counts from the START of the attrExt struct,
                    # which begins after the 16-byte node header — not from the
                    # chunk start. Using the chunk start reads garbage.
                    a = off + 16 + attr_start + i * attr_size
                    a_name = struct.unpack_from("<I", blob, a + 4)[0]
                    raw = struct.unpack_from("<i", blob, a + 8)[0]
                    data = struct.unpack_from("<I", blob, a + 16)[0]
                    res_id = resmap[a_name] if a_name < len(resmap) else 0
                    key = strings[a_name] if a_name < len(strings) else ""
                    if res_id == ATTR_VERSION_CODE or key == "versionCode":
                        code = data
                    elif res_id == ATTR_VERSION_NAME or key == "versionName":
                        vname = strings[raw] if 0 <= raw < len(strings) else str(data)
                if code is None:
                    sys.exit("versionCode not found in the APK manifest")
                return code, vname or "?"
        off += csize
    sys.exit("could not locate <manifest> in the APK's AndroidManifest.xml")


def apk_cert(apk: Path) -> str | None:
    """SHA-256 of the APK's signing certificate, or None if apksigner is absent."""
    candidates = sorted((ROOT.home() / "android-sdk" / "build-tools").glob("*/apksigner"))
    if not candidates:
        return None
    try:
        out = subprocess.run(
            [str(candidates[-1]), "verify", "--print-certs", str(apk)], capture_output=True, text=True, timeout=120
        ).stdout
    except Exception:
        return None
    m = re.search(r"certificate SHA-256 digest:\s*([0-9a-f]+)", out)
    return m.group(1) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk", type=Path)
    ap.add_argument("--notes", default="")
    ap.add_argument(
        "--allow-unsigned-check",
        action="store_true",
        help="publish even if the signing cert cannot be verified locally",
    )
    args = ap.parse_args()

    if not args.apk.is_file():
        sys.exit(f"no such file: {args.apk}")

    cert = apk_cert(args.apk)
    if cert is None:
        if not args.allow_unsigned_check:
            sys.exit(
                "apksigner not found — cannot verify the signing key. "
                "Re-run with --allow-unsigned-check only if you are certain "
                "this APK came from the CI pipeline."
            )
        print("WARNING: signing cert NOT verified (apksigner unavailable)")
    elif cert != EXPECTED_CERT:
        sys.exit(
            f"REFUSING TO PUBLISH: signed with {cert}, expected {EXPECTED_CERT}.\n"
            "An APK with a different key cannot update the installed app — it "
            "would force an uninstall and wipe settings and closet photos."
        )
    else:
        print(f"signing cert OK ({cert[:16]}…)")

    code, name = apk_version(args.apk)
    print(f"apk reports versionCode={code} versionName={name}")

    # Refuse to go backwards: the updater compares versionCode, so republishing an
    # older APK would offer every phone a "update" that downgrades them, and Android
    # rejects downgrades — leaving a banner that can never be satisfied.
    meta_path = DIST / "version.json"
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text()).get("versionCode", 0)
        except Exception:
            prev = 0
        if code < prev:
            sys.exit(f"REFUSING: {code} is older than the published {prev}.")

    DIST.mkdir(exist_ok=True)
    target = DIST / "outfit-advisor.apk"
    shutil.copy2(args.apk, target)

    data = target.read_bytes()
    meta = {
        "versionCode": code,
        "versionName": name,
        "file": target.name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "publishedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "notes": args.notes,
    }
    (DIST / "version.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    print(f"\npublished -> {target}  ({len(data) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
