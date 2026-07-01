"""
weather.py — Open-Meteo fetch, ported from webapp/index.html fetchWeather().

No API key. Returns a structured weather dict for a given day (0=today, 1=tomorrow),
with morning/midday/evening hourly temps in the location's LOCAL time (timezone=auto).
"""
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
