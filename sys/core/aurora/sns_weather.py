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


# WMO weather codes (Open-Meteo) → an icon and words; a code not listed falls to its decade's
WMO = {0: ("☀️", "sereno"), 1: ("🌤️", "poco nuvoloso"), 2: ("⛅", "parzialmente nuvoloso"), 3: ("☁️", "coperto"),
       45: ("🌫️", "nebbia"), 48: ("🌫️", "nebbia con brina"), 51: ("🌦️", "pioviggine"), 53: ("🌦️", "pioviggine"),
       55: ("🌧️", "pioviggine fitta"), 61: ("🌦️", "pioggia debole"), 63: ("🌧️", "pioggia"), 65: ("🌧️", "pioggia forte"),
       66: ("🌧️", "pioggia gelata"), 67: ("🌧️", "pioggia gelata"), 71: ("🌨️", "neve debole"), 73: ("🌨️", "neve"),
       75: ("❄️", "neve forte"), 77: ("🌨️", "granelli di neve"), 80: ("🌦️", "rovesci"), 81: ("🌧️", "rovesci"),
       82: ("⛈️", "rovesci violenti"), 85: ("🌨️", "rovesci di neve"), 86: ("🌨️", "rovesci di neve"),
       95: ("⛈️", "temporale"), 96: ("⛈️", "temporale con grandine"), 99: ("⛈️", "temporale con grandine")}
_next: dict = {"at": 0.0, "value": None}


def next_hours(cfg: sys_config.Config | None = None, hours: int = 3) -> dict | None:
    """The next hours at home for the top bar (owner, 2026-10-20: «una piccola icona nella barra in alto che indica il
    tempo previsto nelle prossime 3 ore»): the worst sky of those hours (a storm over a cloud), its icon and words, the
    temperatures, the rain's highest chance and amount. Open-Meteo, cached 15 minutes; never the place's coordinates."""
    cfg = cfg or sys_config.get()
    lat, lon = str(cfg["AURORA_WEATHER_LAT"]).strip(), str(cfg["AURORA_WEATHER_LON"]).strip()
    if not lat or not lon:
        return None
    with _lock:
        if _next["value"] and time.time() - _next["at"] < 900:
            return _next["value"]
        try:
            h = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
                "latitude": lat, "longitude": lon, "timezone": cfg["AURORA_TIMEZONE"], "forecast_hours": hours,
                "hourly": "weather_code,temperature_2m,precipitation_probability,precipitation,is_day"}
            ).raise_for_status().json()["hourly"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            sys_log.get_logger("senses").warning("weather (next hours) failed: %s", _no_query(e))
            return _next["value"]
        code = max(h["weather_code"])
        icon, words = WMO.get(code) or WMO.get(code // 10 * 10, ("🌡️", ""))
        if code <= 1 and not h["is_day"][0]:
            icon = "🌙"
        out = {"icon": icon, "words": words, "code": code, "hours": hours,
               "t_min": round(min(h["temperature_2m"])), "t_max": round(max(h["temperature_2m"])),
               "rain_pct": max((p or 0) for p in h["precipitation_probability"]),
               "rain_mm": round(sum((p or 0) for p in h["precipitation"]), 1),
               "times": [x[-5:] for x in h["time"]]}
        _next.update(at=time.time(), value=out)
        return out


# Oggi's greeting (api/today.hello; owner, 26 Oct: «una emoji basata… sul meteo, le misurazioni»)
SKY = {"rain": "🌧️", "low_pressure_overcast": "☁️", "hot_humid": "🥵", "cold": "🥶"}


def sign_of_day(w: dict | None, hour: int) -> tuple[str, str]:
    """(emoji, its reason) from the weather reading (sns_weather) and the hour; night wins over a clear sky."""
    night = hour >= 20 or hour < 6
    if w and w.get("condition") in SKY:
        return SKY[w["condition"]], w["condition"]
    if w and (w.get("clouds_pct") or 0) >= 70:
        return "☁️", "clouds"
    if night:
        return "🌙", "night"
    if w and (w.get("clouds_pct") or 0) >= 30:
        return "⛅", "some clouds"
    return ("☀️", "clear") if w else ("👋", "no weather")
