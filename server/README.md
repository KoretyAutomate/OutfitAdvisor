# Outfit Advisor — DGX server

Stateless FastAPI service that the phone app calls each morning over Tailscale.
Fetches weather (Open-Meteo) + outfit text (local vLLM Qwen3.5-122B) for the
phone's live GPS. Holds no state, no DB, and **never logs coordinates**.

## Endpoints

```
GET  /health                                  -> {"ok": true, "vllm": true}
POST /advice {lat, lon, gender, style, day?}  -> {weather, outfit, outfit_text, source}
```
- `gender`: `man` | `woman` | `neutral`   `style`: `casual` | `smart` | `active`
- `day`: `0` = today (morning-push default), `1` = tomorrow
- `source`: `llm` (122B) or `rule-engine` (fallback when vLLM is unreachable)

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
