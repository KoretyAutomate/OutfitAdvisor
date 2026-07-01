#!/usr/bin/env python3
"""
outfit_advisor.py — runs on DGX Spark via cron, sends Telegram notification.

Config: ~/.config/outfit_advisor/config.json
{
  "home_lat":             35.6762,
  "home_lon":             139.6503,
  "openweather_api_key":  "...",
  "ollama_host":          "http://localhost:11434",
  "ollama_model":         "qwen3:8b",
  "telegram_bot_token":   "...",
  "telegram_chat_id":     "..."
}
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

CONFIG_PATH = os.path.expanduser("~/.config/outfit_advisor/config.json")


# ── config ────────────────────────────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"Config not found: {CONFIG_PATH}\nRun: python outfit_advisor.py --init")
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    required = ["home_lat", "home_lon", "openweather_api_key",
                "ollama_host", "ollama_model",
                "telegram_bot_token", "telegram_chat_id"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        sys.exit(f"Config missing keys: {', '.join(missing)}")
    return cfg


def write_config_template():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    template = {
        "home_lat":            35.6762,
        "home_lon":            139.6503,
        "openweather_api_key": "PASTE_YOUR_KEY_HERE",
        "ollama_host":         "http://localhost:11434",
        "ollama_model":        "qwen3:8b",
        "telegram_bot_token":  "PASTE_BOT_TOKEN_HERE",
        "telegram_chat_id":    "PASTE_CHAT_ID_HERE",
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(template, f, indent=2)
    print(f"Config template written to {CONFIG_PATH}")
    print("Edit it, then run: python outfit_advisor.py --test")


# ── weather ───────────────────────────────────────────────────────────────────

def fetch_tomorrow(lat, lon, api_key):
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric&cnt=16"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    periods = [p for p in data["list"] if p["dt_txt"].startswith(tomorrow)]
    if not periods:
        periods = data["list"][:8]

    temps      = [p["main"]["temp"] for p in periods]
    feels      = [p["main"]["feels_like"] for p in periods]
    rain_probs = [p.get("pop", 0) for p in periods]
    winds      = [p["wind"]["speed"] for p in periods]
    conditions = list(dict.fromkeys(p["weather"][0]["description"] for p in periods))
    has_rain   = any("rain" in c for c in conditions) or any("rain" in p for p in periods)
    has_snow   = any("snow" in c for c in conditions) or any("snow" in p for p in periods)

    return {
        "temp_min":    round(min(temps), 1),
        "temp_max":    round(max(temps), 1),
        "temp_swing":  round(max(temps) - min(temps), 1),
        "feels_min":   round(min(feels), 1),
        "feels_max":   round(max(feels), 1),
        "rain_prob":   round(max(rain_probs) * 100),
        "wind_max":    round(max(winds), 1),
        "conditions":  conditions,
        "morning":     round(temps[0], 1),
        "midday":      round(temps[min(4, len(temps)-1)], 1),
        "evening":     round(temps[-1], 1),
        "has_rain":    has_rain,
        "has_snow":    has_snow,
    }


# ── prompt ────────────────────────────────────────────────────────────────────

def build_prompt(w):
    flags = []
    if w["temp_swing"] >= 10:
        flags.append(
            f"Big temperature swing ({w['temp_swing']}°C) — "
            "lead with a layering strategy that is easy to adjust mid-day."
        )
    if w["rain_prob"] >= 50 or w["has_rain"]:
        flags.append(f"Rain likely ({w['rain_prob']}%) — include a waterproof layer and footwear choice.")
    if w["has_snow"]:
        flags.append("Snow forecast — insulated waterproof boots are essential.")
    if w["wind_max"] >= 8:
        flags.append(f"Strong wind ({w['wind_max']} m/s) — a windproof shell matters.")

    flag_block = "\n".join(f"⚠ {f}" for f in flags)

    return f"""Tomorrow's weather forecast:
- Temperature: {w['temp_min']}°C → {w['temp_max']}°C  (swing: {w['temp_swing']}°C)
- Feels like: {w['feels_min']}°C → {w['feels_max']}°C
- Timeline: morning {w['morning']}°C / midday {w['midday']}°C / evening {w['evening']}°C
- Sky: {', '.join(w['conditions'])}
- Rain probability: {w['rain_prob']}%
- Max wind: {w['wind_max']} m/s
{flag_block}

Suggest a practical outfit for tomorrow in exactly 5 bullet points.
Each bullet covers one item: base layer, mid layer, outer layer, bottoms, footwear.
Be specific: fabric weight, material, or brand tier (e.g. "light merino tee", "packable down gilet").
If there is a temperature swing, mention when to add/remove each layer."""


# ── ollama ────────────────────────────────────────────────────────────────────

def call_ollama(prompt, host, model):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["response"].strip()


# ── telegram ──────────────────────────────────────────────────────────────────

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram error: {resp}")


def format_message(w, suggestion):
    swing_flag = f"  ⚠ {w['temp_swing']}°C swing" if w["temp_swing"] >= 10 else ""
    rain_flag  = f"  🌧 rain {w['rain_prob']}%" if w["rain_prob"] >= 50 else ""
    snow_flag  = "  🌨 snow" if w["has_snow"] else ""
    wind_flag  = f"  💨 {w['wind_max']} m/s" if w["wind_max"] >= 8 else ""

    header = (
        f"*Tomorrow's outfit* — {w['temp_min']}°C → {w['temp_max']}°C"
        f"{swing_flag}{rain_flag}{snow_flag}{wind_flag}\n"
        f"_{', '.join(w['conditions'][:2])}_\n"
    )
    return f"{header}\n{suggestion}"


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--init" in sys.argv:
        write_config_template()
        return

    cfg = load_config()
    test_mode = "--test" in sys.argv

    print("Fetching weather...", flush=True)
    try:
        weather = fetch_tomorrow(cfg["home_lat"], cfg["home_lon"], cfg["openweather_api_key"])
    except Exception as e:
        sys.exit(f"Weather fetch failed: {e}")

    print(f"  {weather['temp_min']}°C–{weather['temp_max']}°C, swing {weather['temp_swing']}°C, "
          f"rain {weather['rain_prob']}%")

    print(f"Calling Ollama ({cfg['ollama_model']})...", flush=True)
    try:
        suggestion = call_ollama(build_prompt(weather), cfg["ollama_host"], cfg["ollama_model"])
    except Exception as e:
        sys.exit(f"Ollama failed: {e}")

    message = format_message(weather, suggestion)

    if test_mode:
        print("\n--- MESSAGE PREVIEW ---")
        print(message)
        print("--- END ---")
        return

    print("Sending Telegram notification...", flush=True)
    try:
        send_telegram(cfg["telegram_bot_token"], cfg["telegram_chat_id"], message)
        print("Sent.")
    except Exception as e:
        sys.exit(f"Telegram failed: {e}")


if __name__ == "__main__":
    main()
