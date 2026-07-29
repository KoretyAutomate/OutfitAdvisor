"""
weather.py — Open-Meteo fetch. JS twin: fetchWeatherLocal() in app/www/index.html.

No API key. Returns a structured weather dict for a given day (0=today, 1=tomorrow),
with morning/midday/evening hourly temps in the location's LOCAL time (timezone=auto).

Trips (2026-07-13): fetch_range() covers a multi-day trip window and fetch_normals()
covers a trip beyond the forecast horizon. Both return the SAME {mode, days[],
summary{}} shape so callers and prompts never branch on which one ran.

Verified against the live API 2026-07-12 — three traps encoded below:
  1. The forecast window is today-92d … today+15d and it HARD-ERRORS (HTTP 400)
     outside it. It does not clamp and does not return empty.
  2. The ARCHIVE api silently returns nulls for precipitation_probability_max
     (HTTP 200, units "undefined"). Never request it there — derive rain from
     precipitation_sum instead.
  3. Open-Meteo bills by variables x time-span: one 10-year span ~= 261 calls,
     ten 4-day spans = 10 calls. Always fan out per-year.
"""
import asyncio
import datetime as dt
import statistics
import httpx

# WMO weather-code → (emoji, description). Ported verbatim from index.html.
WMO = {
    0: ("☀️", "Clear sky"), 1: ("🌤️", "Mainly clear"), 2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Heavy drizzle"),
    61: ("🌦️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Freezing rain"), 67: ("🌧️", "Freezing rain"),
    71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"),
    77: ("🌨️", "Snow grains"), 80: ("🌦️", "Rain showers"), 81: ("🌧️", "Rain showers"),
    82: ("⛈️", "Violent showers"), 85: ("🌨️", "Snow showers"), 86: ("❄️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Storm w/ hail"), 99: ("⛈️", "Storm w/ hail"),
}
SNOW_CODES = {71, 73, 75, 77, 85, 86}
RAIN_CODES = {51, 53, 55, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo serves today + 15 more days. Past that the API 400s (verified).
FORECAST_HORIZON_DAYS = 15
# Years of history averaged for the "typical for this window" path.
NORMALS_YEARS = 10
# Open-Meteo 429s a 10-wide burst — throttle, and refuse to call it a "normal"
# if too few years survive (verified 2026-07-13; see _archive_year).
NORMALS_CONCURRENCY = 3
NORMALS_MIN_YEARS = 8
# A day counts as wet above this much precipitation. 0.1mm is drizzle noise.
WET_DAY_MM = 1.0

# Daily vars available in BOTH endpoints. Note the deliberate absence of
# precipitation_probability_max — see trap 2 in the module docstring.
_COMMON_DAILY = [
    "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "wind_speed_10m_max", "weather_code",
]


def _summarize(days: list[dict], mode: str, timezone: str | None) -> dict:
    """Trip-level summary. Packing is driven by the RANGE and the wet-day count,
    not by any single day's mean — a 7-19C week needs layers a 13C mean hides."""
    los = [d["lo"] for d in days]
    his = [d["hi"] for d in days]
    wet = [d for d in days if d["isRain"] or d["rain"] >= 50]
    return {
        "mode": mode,
        "timezone": timezone,
        "nDays": len(days),
        "loMin": min(los),
        "hiMax": max(his),
        "swing": max(his) - min(los),          # across the WHOLE trip, not one day
        "rainDays": len(wet),
        "windMax": max(d["wind"] for d in days),
        "isSnow": any(d["isSnow"] for d in days),
        "isRain": bool(wet),
    }


def _day(date: str, code: int, lo: float, hi: float, rain: int, wind: float) -> dict:
    emoji, desc = WMO.get(code, ("🌡️", "—"))
    return {
        "date": date, "code": code, "emoji": emoji, "desc": desc,
        "lo": round(lo), "hi": round(hi), "rain": rain, "wind": round(wind),
        "isSnow": code in SNOW_CODES, "isRain": code in RAIN_CODES,
    }


def horizon_days_from(today: dt.date, start: dt.date) -> int:
    return (start - today).days


async def fetch_range(lat: float, lon: float, start: str, end: str) -> dict:
    """Real forecast for a trip window. Caller must have checked the window is
    inside FORECAST_HORIZON_DAYS — outside it Open-Meteo 400s rather than clamp."""
    params = {
        "latitude": lat, "longitude": lon,
        "daily": ",".join(_COMMON_DAILY + ["precipitation_probability_max"]),
        "timezone": "auto", "wind_speed_unit": "ms",
        "start_date": start, "end_date": end,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(BASE_URL, params=params)
        r.raise_for_status()
        d = r.json()

    daily = d["daily"]
    days = [
        _day(
            date=daily["time"][i],
            code=daily["weather_code"][i],
            lo=daily["temperature_2m_min"][i],
            hi=daily["temperature_2m_max"][i],
            rain=daily["precipitation_probability_max"][i] or 0,
            wind=daily["wind_speed_10m_max"][i] or 0,
        )
        for i in range(len(daily["time"]))
    ]
    if not days:
        raise ValueError("forecast returned no days")
    return {"mode": "forecast", "days": days,
            "summary": _summarize(days, "forecast", d.get("timezone"))}


async def _archive_year(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                        lat: float, lon: float,
                        start: dt.date, end: dt.date, year: int) -> list[dict] | None:
    """One year's slice of the same calendar window. None if that year is
    genuinely unusable (e.g. a Feb-29 window in a common year).

    Open-Meteo 429s ("Too many concurrent requests") if all NORMALS_YEARS requests
    are fired at once — verified 2026-07-13, 5 of 10 years were rejected. The
    semaphore throttles the fan-out and we retry the 429s; fetch_normals() then
    REFUSES to build a normal out of too few years rather than silently averaging
    two years and calling it climate.
    """
    try:
        s = start.replace(year=year)
        e = end.replace(year=year)
    except ValueError:
        return None  # Feb 29 in a common year — legitimately skippable
    params = {
        "latitude": lat, "longitude": lon,
        "daily": ",".join(_COMMON_DAILY),   # NEVER precipitation_probability_max here
        "timezone": "auto", "wind_speed_unit": "ms",
        "start_date": s.isoformat(), "end_date": e.isoformat(),
    }
    async with sem:
        for attempt in range(4):
            try:
                r = await client.get(ARCHIVE_URL, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json().get("daily")
            except httpx.HTTPError:
                await asyncio.sleep(0.4 * (attempt + 1))
    return None


async def fetch_normals(lat: float, lon: float, start: str, end: str) -> dict:
    """"Typical for this window" — the same calendar days averaged over the last
    NORMALS_YEARS. For trips beyond the forecast horizon.

    Fans out one small request per year (10 billed calls) rather than one long
    span (~261 billed calls) — see trap 3.
    """
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    this_year = dt.date.today().year
    years = range(this_year - NORMALS_YEARS, this_year)

    sem = asyncio.Semaphore(NORMALS_CONCURRENCY)
    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(*[
            _archive_year(client, sem, lat, lon, s, e, y) for y in years
        ])
    usable = [d for d in results if d and d.get("time")]
    # An average of two years is not a climate normal. Fail loudly rather than
    # dress the user for noise while the badge claims "typical for March".
    if len(usable) < NORMALS_MIN_YEARS:
        raise ValueError(
            f"only {len(usable)}/{NORMALS_YEARS} archive years available "
            f"(need {NORMALS_MIN_YEARS})")

    n = (e - s).days + 1
    days: list[dict] = []
    for i in range(n):
        los = [d["temperature_2m_min"][i] for d in usable
               if i < len(d["time"]) and d["temperature_2m_min"][i] is not None]
        his = [d["temperature_2m_max"][i] for d in usable
               if i < len(d["time"]) and d["temperature_2m_max"][i] is not None]
        prc = [d["precipitation_sum"][i] for d in usable
               if i < len(d["time"]) and d["precipitation_sum"][i] is not None]
        wnd = [d["wind_speed_10m_max"][i] for d in usable
               if i < len(d["time"]) and d["wind_speed_10m_max"][i] is not None]
        cds = [d["weather_code"][i] for d in usable
               if i < len(d["time"]) and d["weather_code"][i] is not None]
        if not los or not his:
            continue
        # Rain "probability" for a normals day = the share of past years in which
        # this calendar day was actually wet. Honest, and it is what you pack for.
        wet_frac = round(100 * sum(1 for p in prc if p >= WET_DAY_MM) / len(prc)) if prc else 0
        days.append(_day(
            date=(s + dt.timedelta(days=i)).isoformat(),
            code=statistics.mode(cds) if cds else 0,   # the modal sky, not the mean
            lo=statistics.mean(los), hi=statistics.mean(his),
            rain=wet_frac, wind=statistics.mean(wnd) if wnd else 0,
        ))
    if not days:
        raise ValueError("archive returned no usable days")

    out = {"mode": "normals", "days": days,
           "summary": _summarize(days, "normals", None)}
    # The means understate what you must pack for: a 3.8C mean low with a -2.4C
    # coldest year is a winter-coat trip. Carry the extremes so the prompt can.
    out["summary"]["yearsUsed"] = len(usable)
    out["summary"]["loMinEver"] = round(min(
        v for d in usable for v in d["temperature_2m_min"] if v is not None))
    out["summary"]["hiMaxEver"] = round(max(
        v for d in usable for v in d["temperature_2m_max"] if v is not None))
    return out


async def fetch_weather(lat: float, lon: float, day: int = 0) -> dict:
    """day: 0 = today (morning-push default), 1 = tomorrow."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min",
            "apparent_temperature_max", "apparent_temperature_min",
            "precipitation_probability_max", "wind_speed_10m_max", "weather_code",
        ]),
        "hourly": "temperature_2m",
        "timezone": "auto",
        "forecast_days": 2,
        "wind_speed_unit": "ms",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(BASE_URL, params=params)
        r.raise_for_status()
        d = r.json()

    i = day
    daily = d["daily"]
    date = daily["time"][i]
    code = daily["weather_code"][i]

    # hourly temps for morning(8)/midday(13)/evening(19) at this date, local tz
    htime = d["hourly"]["time"]
    htemp = d["hourly"]["temperature_2m"]

    def hour_temp(h: int):
        key = f"{date}T{h:02d}:00"
        try:
            idx = htime.index(key)
        except ValueError:
            return None
        v = htemp[idx]
        return round(v) if v is not None else None

    lo = round(daily["temperature_2m_min"][i])
    hi = round(daily["temperature_2m_max"][i])
    emoji, desc = WMO.get(code, ("🌡️", "—"))

    return {
        "date": date,
        "timezone": d.get("timezone"),
        "code": code,
        "emoji": emoji,
        "desc": desc,
        "lo": lo,
        "hi": hi,
        "swing": hi - lo,
        "feelsLo": round(daily["apparent_temperature_min"][i]),
        "feelsHi": round(daily["apparent_temperature_max"][i]),
        "rain": daily["precipitation_probability_max"][i] or 0,
        "wind": round(daily["wind_speed_10m_max"][i]),
        "morning": hour_temp(8),
        "midday": hour_temp(13),
        "evening": hour_temp(19),
        "isSnow": code in SNOW_CODES,
        "isRain": code in RAIN_CODES,
    }
