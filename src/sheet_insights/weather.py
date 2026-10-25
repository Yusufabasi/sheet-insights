"""Daily weather from Open-Meteo (no API key). Used only to explain generation swings."""

from __future__ import annotations

from datetime import date

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_PAST_DAYS = 92


def fetch_weather(
    latitude: float,
    longitude: float,
    start: date,
    today: date,
    client: httpx.Client | None = None,
) -> dict[str, dict[str, float]]:
    """Map ISO date -> weather figures for [start, today]. Missing values are omitted."""
    past_days = min((today - start).days + 1, MAX_PAST_DAYS)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "shortwave_radiation_sum,precipitation_sum",
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "auto",
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=15)
    try:
        response = http.get(FORECAST_URL, params=params)
        response.raise_for_status()
        daily = response.json()["daily"]
    finally:
        if owns_client:
            http.close()

    result: dict[str, dict[str, float]] = {}
    for index, day in enumerate(daily["time"]):
        figures: dict[str, float] = {}
        radiation = daily["shortwave_radiation_sum"][index]
        rain = daily["precipitation_sum"][index]
        if radiation is not None:
            figures["solar_radiation_mj_m2"] = round(radiation, 1)
        if rain is not None:
            figures["precipitation_mm"] = round(rain, 1)
        if figures:
            result[day] = figures
    return result
