# Outfit Advisor

A "what should I wear today?" Android app that wakes up at your chosen morning
time, reads your **live GPS location**, checks the weather, and pushes a
notification with a concrete outfit — written by a **local LLM running on your
own machine**. No cloud AI, no account, no location ever stored.

```
06:45 ─ exact alarm fires (works through Doze, phone locked)
      ─ brief wake screen reads ONE fresh GPS fix
      ─ POST {lat, lon, gender, style} ──Tailscale──▶ home server
                                                      ├─ Open-Meteo forecast
                                                      └─ local LLM writes the outfit
      ◀─ notification: "🌦 16–22°  Today's outfit — light merino base, …"
      ─ coordinates discarded (RAM-only, never persisted, never logged)
```

## How it works

Two halves, split so the phone stays dumb and the intelligence stays home:

| | Phone (Capacitor + Kotlin) | Home server (FastAPI) |
|---|---|---|
| Owns | schedule, GPS, notification | weather fetch, LLM prompt |
| Talks | POST `/advice` over Tailscale | Open-Meteo + local vLLM |
| Stores | prefs only — **never coordinates** | nothing (stateless, no DB) |

- **Exact morning alarm** via `setExactAndAllowWhileIdle` + a full-screen-intent
  wake activity — this makes the GPS read count as legitimate *foreground*
  location, so the app needs no background-location permission and no paid
  geolocation SDK.
- **Offline fallback**: if the server is unreachable, an on-device rule engine
  (a JS twin of the server's `engine.py`) still produces an outfit from
  Open-Meteo directly. You always get *something*.
- **Tailscale-only**: the server binds its tailnet IP, not `0.0.0.0` — it is
  invisible to the LAN and the public internet. The app whitelists cleartext
  HTTP to that single IP only.

## The three sheets

The app is one screen with three pages, switched by a strip of tabs along the
bottom the way a spreadsheet switches sheets:

| 📍 Location & advice | 🧥 Closet | 📅 Calendar |
|---|---|---|
| where you are, who you dress as, today's weather and outfit | your clothes, and what is in the wash | home area, which calendars may be read, upcoming trips and packing |

## Repo layout

```
server/          FastAPI service (see server/README.md for endpoints & run)
  app.py           POST /advice, GET /health — validated inputs, leak-safe errors
  weather.py       Open-Meteo (tz=auto)
  engine.py        rule-engine fallback (JS twin lives in app/www/index.html)
  llm.py           local vLLM call (enable_thinking:false — do not remove)
  deploy/          systemd user unit
app/             Capacitor 6 Android app
  www/index.html   the whole web layer (UI, offline engine, prefs)
  android/         native layer: exact alarm, wake activity, boot re-arm
.github/workflows/build-apk.yml   CI APK build (debug)
```

## Build & install

The APK is built by GitHub Actions (`build-apk.yml`) — grab the
`outfit-advisor-debug` artifact from the latest run and sideload it, or:

```bash
gh run download <run-id> --name outfit-advisor-debug
adb pair <phone-ip>:<pair-port>        # once, from Developer options → Wireless debugging
adb connect <phone-ip>:<connect-port>  # port rotates; check the phone each time
adb install -r app-debug.apk
```

Building locally instead needs JDK 17 + Android SDK 34 and an **x86-64 host**
(Google ships no aarch64 `aapt2`; ARM hosts must use CI or qemu).

Server setup: `server/README.md`. Point the app at your server via
*Advanced — advisor server* in the app's Morning push card.

## Privacy posture

- Coordinates live only in RAM on both sides: the phone never persists them,
  the server never logs them (access log off; httpx loggers silenced because
  they would otherwise print the weather URL with lat/lon).
- A saved city name re-geocodes on demand rather than caching its coordinates.
- Weather-fetch errors return coordinate-free messages (upstream error strings
  embed the request URL — they are never propagated).
- Calendars (used only to spot upcoming trips) are read **on the phone** and never
  sent anywhere. A calendar somebody else **shared with you is never read at all** —
  the app asks Android who owns each calendar and scans only the user's own, and if
  it cannot tell the two apart it scans nothing rather than everything. The picker
  lists them grouped under the account each belongs to, so you can see which
  sign-in a calendar came from before ticking it.
- A trip is only added **by itself** when the advisor is sure, the destination
  looks like a place name, and the geocoder answers with *that* place. Open-Meteo's
  search is fuzzy and scoreless — trusting its first hit is what once produced
  automatic trips to cities nobody had named. Anything short of all three is
  offered as a candidate to confirm, never invented.

## Status

MVP under active development. Server, web layer, and native layer are
build-verified; on-device verification of the morning-alarm path (Doze wake →
fresh GPS → push) is in progress. Single-device, Tailscale-only for now — a
public-HTTPS + auth variant is sketched in `server/README.md` but out of scope
for the MVP.

## License

No license yet — all rights reserved. Open an issue if you want to use it.
