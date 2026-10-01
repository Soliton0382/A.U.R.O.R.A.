# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "weather": the weather at Aurora's home, a daily report and alerts on sudden changes.

Data: Open-Meteo (no key; forecast models of the national services) at AURORA_WEATHER_LAT/LON, and the official
warnings of MeteoAlarm (the European national weather services) for AURORA_WEATHER_REGION. Read only.

Local alerts (thresholds are forecasters' rules of thumb, not measurements of this plugin):
  pressure falling >= 3 hPa in 3 h (rapid), >= 6 hPa (very rapid) | gusts >= 60 km/h | rain >= 10 mm/h |
  temperature change >= 8 degC in 3 h | thunderstorm, snow, freezing rain (WMO weather codes)
looked for from 3 hours ago to AURORA_WEATHER_ALERT_HOURS ahead.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("weather", version="1.0")
logging.getLogger("httpx").setLevel(logging.WARNING)            # its INFO lines carry the URL: the home's coordinates
UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal assistant)"}
WMO = {0: "sereno", 1: "prevalentemente sereno", 2: "parzialmente nuvoloso", 3: "coperto", 45: "nebbia",
       48: "nebbia con brina", 51: "pioviggine debole", 53: "pioviggine", 55: "pioviggine intensa",
       56: "pioviggine gelata", 57: "pioviggine gelata intensa", 61: "pioggia debole", 63: "pioggia",
       65: "pioggia forte", 66: "pioggia gelata", 67: "pioggia gelata forte", 71: "neve debole", 73: "neve",
       75: "neve forte", 77: "granelli di neve", 80: "rovesci deboli", 81: "rovesci", 82: "rovesci violenti",
       85: "rovesci di neve", 86: "rovesci di neve forti", 95: "temporale", 96: "temporale con grandine",
       99: "temporale con grandine forte"}
SEVERE = {95: "temporale", 96: "temporale con grandine", 99: "temporale con grandine forte",
          56: "pioviggine gelata", 57: "pioviggine gelata", 66: "pioggia gelata", 67: "pioggia gelata",
          71: "neve", 73: "neve", 75: "neve forte", 77: "neve", 85: "rovesci di neve", 86: "rovesci di neve forti"}
LEVEL = {"Moderate": "🟡 gialla", "Severe": "🟠 arancione", "Extreme": "🔴 rossa"}


def tool(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError:
            raise
        except Exception as e:                                       # never the query: it holds the coordinates
            raise ToolError(re.sub(r"\?[^'\"\s]*", "?…", f"{type(e).__name__}: {e}")) from e
    return server.tool()(wrapped)


def _place() -> tuple[str, str, str]:
    lat, lon = str(cfg["AURORA_WEATHER_LAT"]).strip(), str(cfg["AURORA_WEATHER_LON"]).strip()
    if not lat or not lon:
        raise ToolError("AURORA_WEATHER_LAT/LON are not set: the weather has no place")
    return lat, lon, cfg["AURORA_WEATHER_PLACE"] or "casa"


def forecast() -> dict:
    lat, lon, _ = _place()
    return httpx.get("https://api.open-meteo.com/v1/forecast", timeout=20, headers=UA, params={
        "latitude": lat, "longitude": lon, "timezone": cfg["AURORA_TIMEZONE"], "past_hours": 3,
        "forecast_hours": max(6, int(cfg["AURORA_WEATHER_ALERT_HOURS"])), "forecast_days": 3, "wind_speed_unit": "kmh",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_gusts_10m,"
                   "precipitation,weather_code,cloud_cover",
        "hourly": "temperature_2m,pressure_msl,wind_gusts_10m,precipitation,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
                 "wind_gusts_10m_max,sunrise,sunset"}).raise_for_status().json()


def local_alerts(j: dict) -> list[str]:
    """Sudden changes in the hourly series (pure: tested offline)."""
    h = j["hourly"]
    t, p, g, r, w, temp = h["time"], h["pressure_msl"], h["wind_gusts_10m"], h["precipitation"], h["weather_code"], h["temperature_2m"]
    out: list[str] = []
    hm = lambda i: t[i][11:16]                                          # noqa: E731
    for i in range(3, len(t)):
        if p[i] is not None and p[i - 3] is not None and p[i - 3] - p[i] >= 3:
            drop = p[i - 3] - p[i]
            out.append(f"📉 pressione in calo {'molto ' if drop >= 6 else ''}rapido: {drop:.1f} hPa in 3 ore "
                       f"({hm(i - 3)}→{hm(i)}), segno di peggioramento")
            break
    for i in range(3, len(t)):
        if temp[i] is not None and temp[i - 3] is not None and abs(temp[i] - temp[i - 3]) >= 8:
            out.append(f"🌡️ temperatura {'in calo' if temp[i] < temp[i - 3] else 'in salita'} di "
                       f"{abs(temp[i] - temp[i - 3]):.0f} °C in 3 ore ({hm(i - 3)}→{hm(i)})")
            break
    gust = max(((x or 0), i) for i, x in enumerate(g))
    if gust[0] >= 60:
        out.append(f"💨 raffiche fino a {gust[0]:.0f} km/h verso le {hm(gust[1])}")
    rain = max(((x or 0), i) for i, x in enumerate(r))
    if rain[0] >= 10:
        out.append(f"🌧️ pioggia intensa: {rain[0]:.0f} mm in un'ora verso le {hm(rain[1])}")
    sev = next(((c, i) for i, c in enumerate(w) if c in SEVERE), None)
    if sev:
        out.append(f"⛈️ {SEVERE[sev[0]]} previsto verso le {hm(sev[1])}")
    return out


def official_alerts() -> list[str]:
    region = str(cfg["AURORA_WEATHER_REGION"]).strip().lower()
    if not region:
        return []
    j = httpx.get(cfg["AURORA_WEATHER_WARNINGS_FEED"], timeout=30, headers=UA, follow_redirects=True).raise_for_status().json()
    now, out = datetime.now().astimezone(), []
    for w in j.get("warnings", []):
        infos = w.get("alert", {}).get("info", [])
        info = next((i for i in infos if str(i.get("language", "")).startswith("it")), infos[0] if infos else None)
        if not info or info.get("severity") not in LEVEL:
            continue
        if not any(region in str(a.get("areaDesc", "")).lower() for a in info.get("area", [])):
            continue
        try:
            if datetime.fromisoformat(info["expires"]) < now:
                continue
        except (KeyError, ValueError):
            pass
        line = f"⚠️ allerta {LEVEL[info['severity']]} ufficiale: {info.get('event', '')}"
        line += f" (dal {info.get('onset', '')[:16].replace('T', ' ')} al {info.get('expires', '')[:16].replace('T', ' ')})"
        if line not in out:
            out.append(line)
    return out


def _day(d: dict, k: int) -> str:
    return (f"{WMO.get(d['weather_code'][k], 'variabile')}, min {d['temperature_2m_min'][k]:.0f}° max "
            f"{d['temperature_2m_max'][k]:.0f}°, pioggia {d['precipitation_sum'][k]:.1f} mm "
            f"(probabilità {d['precipitation_probability_max'][k] or 0}%), raffiche fino a {d['wind_gusts_10m_max'][k]:.0f} km/h")


@tool
def weather_now() -> str:
    """The weather at home now: condition, temperature (felt), humidity, pressure, wind, rain."""
    j = forecast()
    c = j["current"]
    return (f"{_place()[2]}, ore {c['time'][11:16]}: {WMO.get(c['weather_code'], 'variabile')}, {c['temperature_2m']:.1f}° "
            f"(percepiti {c['apparent_temperature']:.1f}°), umidità {c['relative_humidity_2m']}%, pressione "
            f"{c['pressure_msl']:.0f} hPa, vento {c['wind_speed_10m']:.0f} km/h (raffiche {c['wind_gusts_10m']:.0f}), "
            f"pioggia {c['precipitation']:.1f} mm, nuvole {c['cloud_cover']}%")


@tool
def weather_forecast(days: int = 3) -> str:
    """The forecast day by day (1-3 days): condition, min/max, rain and its probability, gusts, sunrise and sunset."""
    d = forecast()["daily"]
    lines = []
    for k in range(min(max(days, 1), len(d["time"]))):
        lines.append(f"{d['time'][k]}: {_day(d, k)}; alba {d['sunrise'][k][11:16]}, tramonto {d['sunset'][k][11:16]}")
    return "\n".join(lines)


@tool
def weather_today() -> str:
    """The daily report: today and tomorrow at home, with any alert (local sudden changes and official warnings)."""
    j = forecast()
    d = j["daily"]
    text = (f"☀️ Meteo di oggi a {_place()[2]}: {_day(d, 0)}. Alba {d['sunrise'][0][11:16]}, tramonto {d['sunset'][0][11:16]}.\n"
            f"Domani: {_day(d, 1)}.")
    alerts = local_alerts(j) + official_alerts()
    return text + ("\n" + "\n".join(alerts) if alerts else "")


@tool
def weather_alerts() -> str:
    """Alerts only: sudden changes expected at home (pressure, gusts, rain, temperature, storms, snow, ice) and official
    warnings for the region. Empty when there is nothing to say."""
    return "\n".join(local_alerts(forecast()) + official_alerts())


if __name__ == "__main__":
    server.run("stdio")
