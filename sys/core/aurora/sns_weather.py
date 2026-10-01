# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's sense of the weather around her home.

Providers: open-meteo (no key) or openweathermap (AURORA_WEATHER_API_KEY). The place is
AURORA_WEATHER_LAT / AURORA_WEATHER_LON, kept only in the private .env. A reading is
cached for AURORA_WEATHER_INTERVAL_MIN minutes; without coordinates the sense is off.

The reading is plain data (temperature, humidity, pressure, clouds, rain, wind) plus a
`condition` word; how it colours Aurora's moods is decided by the autonomic cycle.
"""
from __future__ import annotations

import re
import threading
import time

import httpx

from . import sys_config, sys_log

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "reading": None}


def _no_query(e: Exception) -> str:
    """An error without the query of its URL."""
    return re.sub(r"\?[^'\"\s]*", "?…", f"{type(e).__name__}: {e}")


def _condition(r: dict) -> str:
    if r["rain_mm"] > 0.5:
        return "rain"
    if r["pressure_hpa"] < 1005 and r["clouds_pct"] > 80:
        return "low_pressure_overcast"
    if r["temperature_c"] > 28 and r["humidity_pct"] > 70:
        return "hot_humid"
    if r["temperature_c"] < 5:
        return "cold"
    if r["clouds_pct"] < 20 and 15 < r["temperature_c"] < 26:
        return "clear_mild"
    return "neutral"


def _open_meteo(cfg, lat: float, lon: float) -> dict:
    j = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": lat, "longitude": lon, "timezone": cfg["AURORA_TIMEZONE"],
        "current": "temperature_2m,relative_humidity_2m,surface_pressure,cloud_cover,rain,wind_speed_10m,is_day"}
    ).raise_for_status().json()["current"]
    return {"temperature_c": j["temperature_2m"], "humidity_pct": j["relative_humidity_2m"],
            "pressure_hpa": j["surface_pressure"], "clouds_pct": j["cloud_cover"], "rain_mm": j["rain"],
            "wind_kmh": j["wind_speed_10m"], "is_day": bool(j["is_day"]), "observed": j["time"]}


def _openweathermap(cfg, lat: float, lon: float) -> dict:
    j = httpx.get("https://api.openweathermap.org/data/2.5/weather", timeout=10, params={
        "lat": lat, "lon": lon, "appid": cfg["AURORA_WEATHER_API_KEY"], "units": "metric", "lang": "it"}
    ).raise_for_status().json()
    now = j.get("dt", 0)
    return {"temperature_c": j["main"]["temp"], "humidity_pct": j["main"]["humidity"],
            "pressure_hpa": j["main"]["pressure"], "clouds_pct": j.get("clouds", {}).get("all", 0),
            "rain_mm": j.get("rain", {}).get("1h", 0.0), "wind_kmh": round(j["wind"]["speed"] * 3.6, 1),
            "is_day": j["sys"]["sunrise"] <= now <= j["sys"]["sunset"], "observed": now,
            "description": j["weather"][0]["description"] if j.get("weather") else ""}


def read(cfg: sys_config.Config | None = None) -> dict | None:
    """The current reading (cached), or None when the sense is off or the provider fails."""
    cfg = cfg or sys_config.get()
    lat, lon = str(cfg["AURORA_WEATHER_LAT"]).strip(), str(cfg["AURORA_WEATHER_LON"]).strip()
    if not lat or not lon:
        return None
    with _lock:
        if _cache["reading"] and time.time() - _cache["at"] < cfg["AURORA_WEATHER_INTERVAL_MIN"] * 60:
            return _cache["reading"]
        provider = cfg["AURORA_WEATHER_PROVIDER"]
        try:
            fetch = _openweathermap if provider == "openweathermap" else _open_meteo
            r = fetch(cfg, float(lat), float(lon))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # never the URL: its query holds the home's coordinates (and the key of a keyed provider)
            sys_log.get_logger("senses").warning("weather (%s) failed: %s", provider, _no_query(e))
            return _cache["reading"]                      # the last good reading, if any
        r["condition"], r["provider"] = _condition(r), provider
        r["place"] = cfg["AURORA_WEATHER_PLACE"]
        _cache.update(at=time.time(), reading=r)
        return r
