"""
local_llm.py — which local model to call, and where.

Read from ~/.config/local-llm/models.toml, the one file every project on this box
shares (LOCAL_LLM_CONFIG overrides the path; tests point it at a fixture). The model
is not a secret, so it does not belong in .env, and a model swap is one edit there
instead of a hardcoded name in every repo — the 2026-10-15 swap from the 122B to
Qwen3.6 left this file's old constant asking vLLM for a model it no longer served.

Read on every call, not at import: the file is a few lines, and an edit takes effect
without a restart. A missing or malformed file raises LocalLLMConfigError, which the
caller turns into "no reply" like any other failure.
"""

import logging
import os
import tomllib
from pathlib import Path

log = logging.getLogger("outfit.llm")

DEFAULT_PATH = Path.home() / ".config" / "local-llm" / "models.toml"


class LocalLLMConfigError(RuntimeError):
    pass


_last: tuple[str, str] | None = None


def config_path() -> Path:
    return Path(os.environ.get("LOCAL_LLM_CONFIG") or DEFAULT_PATH)


def endpoint(tier: str = "smart") -> tuple[str, str]:
    """(chat-completions URL, model id) for a tier of models.toml."""
    global _last
    path = config_path()
    try:
        with path.open("rb") as f:
            entry = tomllib.load(f)[tier]
        base, model = str(entry["base_url"]).rstrip("/"), str(entry["model"])
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as e:
        raise LocalLLMConfigError(f"{path}: no usable [{tier}] base_url/model ({type(e).__name__})") from e
    if not entry.get("vision"):
        # classify_image sends photos; a text-only model would reject every one.
        raise LocalLLMConfigError(f"{path}: [{tier}] model {model} is not marked vision = true")
    found = (f"{base}/chat/completions", model)
    if found != _last:
        log.info("llm: %s @ %s (from %s)", model, base, path)
        _last = found
    return found
