import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

EMOJI = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
}

async def fetch_week_forecast(api_key: str, lat=55.6761, lon=12.5683, tz=ZoneInfo("Europe/Copenhagen")):
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric", "lang": "da"}
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
    by_day = {}
    for item in data["list"]:
        dt = datetime.fromtimestamp(item["dt"], tz)
        day = dt.strftime("%a")
        main = item["weather"][0]["main"]
        temp = item["main"]["temp_max"]
        d = by_day.setdefault(day, {"max": -273, "counts": {}})
        d["max"] = max(d["max"], temp)
        d["counts"][main] = d["counts"].get(main, 0) + 1
    days = []
    for day, d in list(by_day.items())[:4]:
        dominant = max(d["counts"], key=d["counts"].get)
        icon = EMOJI.get(dominant, "🌤️")
        days.append({"label": day, "icon": icon, "tmax": round(d["max"])})
    return days
