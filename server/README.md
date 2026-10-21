# Outfit Advisor — DGX server

Stateless FastAPI service that the phone app calls each morning over Tailscale.
Fetches weather (Open-Meteo) + outfit text (local vLLM model, set in `~/.config/local-llm/models.toml`) for the
phone's live GPS. Holds no state, no DB, and **never logs coordinates**.

## Endpoints

```
GET  /health                                  -> {"ok": true, "vllm": true}
POST /advice {lat, lon, gender, style, day?}  -> {weather, outfit, outfit_text, source}
```
- `gender`: `man` | `woman` | `neutral`   `style`: `casual` | `smart` | `active`
- `day`: `0` = today (morning-push default), `1` = tomorrow
- `source`: who wrote `outfit_text` — `llm` (the local model), `funnel` (a closet outfit
  chosen by code alone, the model unreachable: plain lines), `rule-engine` (fallback when
  vLLM is unreachable and no closet outfit was found) or `none` (closetOnly and the advisor
  could not answer: the slots are emptied rather than filled from a catalogue)

## How a closet outfit is chosen (2026-10-20)

`OUTFIT_ENGINE=funnel` (the default): `funnel.py` narrows the wardrobe in code — the day's
dress level, the weather, layer shapes, rotation priority, then pairings checked slot by
slot (register, texture, colour, belt) with a relax ladder when nothing survives — and every
survivor passes `check.issues`. `chooser.py` asks the model once to pick the best-looking of
the top four and write the lines. `OUTFIT_ENGINE=model` is the earlier loop (the model picks
from everything, `check.py` and `fallback.py` mend it), kept for rollback.

## Run

Dev (foreground):
```
cd server
/home/korety/miniconda3/bin/python3 -m uvicorn app:app --host 100.112.171.54 --port 8787 --no-access-log
```
Production (survives reboot): see `deploy/outfit-advisor.service`.

Health check (the bind is tailnet-only, so use the tailnet IP even locally):
```
curl http://100.112.171.54:8787/health
```

Deps: `fastapi uvicorn[standard] httpx pydantic` (already present in base conda;
`requirements.txt` for a clean venv).

## Design notes
- Binds the **Tailscale IP only** (`100.112.171.54:8787`) — invisible to the LAN;
  vLLM stays localhost-only (`127.0.0.1:8000`). Only this server is on the tailnet.
- **Privacy:** access-log disabled; httpx/httpcore loggers silenced (they would
  otherwise log the Open-Meteo URL with lat/lon). Verified coord-free.
- **vLLM thinking-mode:** `llm.py` passes `chat_template_kwargs.enable_thinking=false`
  — without it Qwen3.5 returns empty content. Do not remove.
- `engine.py` is a faithful Python twin of the JS `recommend()` in
  `../app/www/index.html`, so the app's offline fallback matches the server.
  **Change them together.**

## Future (store/public) — kept portable
Put behind Caddy/Cloudflare Tunnel for HTTPS + add a bearer-token dependency; the
app changes only its base URL + Authorization header. No core-logic change.
