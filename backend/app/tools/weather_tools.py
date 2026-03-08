"""
Weather tools — current conditions and forecast via the free Open-Meteo API.

No API key required. Geocoding + weather data are fetched from open-meteo.com.
"""

import json
import logging
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# ── JSON-Schema definitions ─────────────────────────────────────

WEATHER_TOOL_DEFINITIONS = [
    {
        "name": "get_current_weather",
        "description": (
            "Get current weather conditions for a location. Returns temperature, "
            "humidity, wind speed, and weather description. Use this when the "
            "user asks about the weather, temperature, or conditions in a city."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "City name, optionally with country (e.g. 'Zurich', "
                        "'London, UK', 'New York, US')."
                    ),
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "get_weather_forecast",
        "description": (
            "Get a multi-day weather forecast for a location. Returns daily "
            "high/low temperatures, precipitation, and conditions for up to "
            "7 days ahead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, optionally with country.",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of forecast days (1-7, default 3).",
                },
            },
            "required": ["location"],
        },
    },
]

WEATHER_TOOL_NAMES = {t["name"] for t in WEATHER_TOOL_DEFINITIONS}

# ── WMO weather code descriptions ───────────────────────────────

WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _wmo_description(code: int) -> str:
    return WMO_CODES.get(code, f"Unknown ({code})")


# ── Geocoding helper ─────────────────────────────────────────────

def _geocode(location: str) -> dict:
    """Look up coordinates for a location name. Returns {name, lat, lon, country}."""
    from urllib.parse import quote
    url = f"{GEOCODE_URL}?name={quote(location)}&count=1&language=en&format=json"
    req = Request(url, headers={"User-Agent": "Cronosaurus/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        raise ValueError(f"Geocoding failed for '{location}': {e}")

    results = data.get("results", [])
    if not results:
        raise ValueError(f"Location '{location}' not found. Try a different city name.")

    r = results[0]
    return {
        "name": r.get("name", location),
        "country": r.get("country", ""),
        "lat": r["latitude"],
        "lon": r["longitude"],
    }


# ── Weather API helpers ──────────────────────────────────────────

def _fetch_weather(lat: float, lon: float, forecast_days: int = 1) -> dict:
    """Fetch weather data from Open-Meteo."""
    current_params = "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m"
    daily_params = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"

    url = (
        f"{WEATHER_URL}?latitude={lat}&longitude={lon}"
        f"&current={current_params}"
        f"&daily={daily_params}"
        f"&forecast_days={forecast_days}"
        f"&timezone=auto"
    )
    req = Request(url, headers={"User-Agent": "Cronosaurus/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        raise ValueError(f"Weather API request failed: {e}")


# ── Tool implementations ─────────────────────────────────────────

def _get_current_weather(location: str) -> dict:
    try:
        geo = _geocode(location)
        data = _fetch_weather(geo["lat"], geo["lon"], forecast_days=1)
        current = data.get("current", {})

        return {
            "success": True,
            "location": f"{geo['name']}, {geo['country']}",
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction": current.get("wind_direction_10m"),
            "conditions": _wmo_description(current.get("weather_code", 0)),
            "unit": "°C",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_current_weather error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch weather: {e}"}


def _get_weather_forecast(location: str, days: int = 3) -> dict:
    try:
        days = max(1, min(days, 7))
        geo = _geocode(location)
        data = _fetch_weather(geo["lat"], geo["lon"], forecast_days=days)
        daily = data.get("daily", {})

        dates = daily.get("time", [])
        forecast = []
        for i, date in enumerate(dates):
            forecast.append({
                "date": date,
                "high": daily.get("temperature_2m_max", [None])[i],
                "low": daily.get("temperature_2m_min", [None])[i],
                "precipitation_mm": daily.get("precipitation_sum", [0])[i],
                "max_wind_kmh": daily.get("wind_speed_10m_max", [None])[i],
                "conditions": _wmo_description(
                    daily.get("weather_code", [0])[i] if i < len(daily.get("weather_code", [])) else 0
                ),
            })

        return {
            "success": True,
            "location": f"{geo['name']}, {geo['country']}",
            "unit": "°C",
            "days": len(forecast),
            "forecast": forecast,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_weather_forecast error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch forecast: {e}"}


# ── Tool execution dispatcher ───────────────────────────────────

def execute_weather_tool(tool_name: str, arguments: str | dict) -> dict:
    """Execute a weather tool call and return the result."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {"success": False, "error": f"Invalid arguments: {arguments}"}

    if tool_name == "get_current_weather":
        return _get_current_weather(location=arguments.get("location", ""))
    elif tool_name == "get_weather_forecast":
        return _get_weather_forecast(
            location=arguments.get("location", ""),
            days=arguments.get("days", 3),
        )

    return {"success": False, "error": f"Unknown weather tool: {tool_name}"}
