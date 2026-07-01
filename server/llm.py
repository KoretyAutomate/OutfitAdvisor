"""
llm.py — outfit text from the local vLLM Qwen3.5-122B (OpenAI-compatible API).

CRITICAL (verified empirically 2026-06-29): Qwen3.5 defaults to "thinking mode",
which burns the whole token budget on a hidden reasoning trace and returns EMPTY
content. We MUST pass chat_template_kwargs.enable_thinking=false. With that +
max_tokens~130 + a concise prompt → ~7.7s clean 5-bullet output.

Returns the outfit text, or None on any failure (caller falls back to the rule engine).
"""
import httpx

VLLM_URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "Intel/Qwen3.5-122B-A10B-int4-AutoRound"


def build_prompt(w: dict, gender: str, style: str) -> str:
    flags = []
    if w["swing"] >= 10:
        flags.append(f"Big {w['swing']}C swing — say when to shed/add a layer.")
    if w["rain"] >= 50 or w["isRain"]:
        flags.append(f"Rain likely ({w['rain']}%) — waterproof outer + footwear.")
    if w["isSnow"]:
        flags.append("Snow — insulated waterproof boots.")
    if w["wind"] >= 8:
        flags.append(f"Strong wind ({w['wind']} m/s) — windproof shell.")
    flag_line = (" " + " ".join(flags)) if flags else ""

    return (
        f"Today: {w['lo']}C-{w['hi']}C (feels {w['feelsLo']}-{w['feelsHi']}C), "
        f"{w['desc'].lower()}, rain {w['rain']}%, wind {w['wind']} m/s. "
        f"Morning {w['morning']}C, midday {w['midday']}C, evening {w['evening']}C.{flag_line} "
        f"Outfit for a {gender}, {style} style. Exactly 5 short bullets: "
        f"base, mid, outer, bottoms, footwear. One concise line each, name fabric/material. "
        f"ONLY the 5 bullets, no preamble."
    )


async def outfit_text(w: dict, gender: str, style: str) -> str | None:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": build_prompt(w, gender, style)}],
        "max_tokens": 130,
        "temperature": 0.4,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(VLLM_URL, json=payload)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"].get("content")
        if content and content.strip():
            return content.strip()
        return None
    except Exception:
        return None
