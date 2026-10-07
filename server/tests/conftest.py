"""Puts server/ on sys.path once, before any test module is imported.

pytest imports conftest.py before it collects anything in this directory, so a
path set up here is already in place when the test modules run their imports.
That is why the test files can `import vocab` at the top like normal code.

Doing it per-file instead means every file needs sys.path.insert BEFORE its
imports, which puts imports below a statement — E402 — and the house rule bans
inline lint suppressions for it. Fixing the cause beats suppressing the symptom seven
times, and it is one line to change if the layout ever moves.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The stylist (stylist.py) is a SECOND model call per outfit. Off by default here:
# every test that stubs the model reads the outfit prompt back from the stub and
# counts its calls, and a review prompt arriving after it would replace both. The
# stylist's own tests turn it back on.
os.environ.setdefault("OUTFIT_STYLIST", "0")
