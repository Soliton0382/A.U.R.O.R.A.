# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💗 Aurora's emotions from measurements (roadmap 52; owner, 2026-10-06: «le emozioni basate su misurazioni
ambientali, valori di carico di lavoro… sarebbe una bella personalità»). No simulated hormone: each emotion is a
number from 0 to 1 computed from things measured now, and carries its causes in words, so she can always say why.

| emotion      | measured from                                                                  | half (0.5) at                 |
|--------------|--------------------------------------------------------------------------------|-------------------------------|
| stress       | the largest of: GPU load, the GPUs' distance from their thermal limit (driver),| 50 % load · 15 °C from the    |
|              | answers being made / the parallel slots, errors in the last hour               | limit · a full slot · 1 error |
| satisfaction | answers found in the sources / all answers of the last 24 h (abstained, errors)| —  (a ratio)                  |
| curiosity    | questions to study + past answers with something new to look at                | one night's capacity          |
| tiredness    | the share of the last 6 h with a GPU busy (sampled at every REM look)          | —  (a share)                  |
| longing      | hours since the person last wrote                                              | the boredom threshold         |
| melancholy   | clouds and rain at home                                                        | overcast, or 1 mm of rain     |
| worry        | open incidents of high severity + health problems                              | one                           |

Effects (each small, each said): the words she uses about herself (the "self" answers, her spontaneous messages, the
good morning), the autonomic cycle waiting when stress passes AURORA_MOOD_STRESS_PAUSE, the chat voice a little slower
when tired. AURORA_MOOD off = none of it, and no numbers shown.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from . import sys_config

NAMES = ("stress", "satisfaction", "curiosity", "tiredness", "longing", "melancholy", "worry")
WINDOW_H = 6                      # tiredness looks at the last 6 hours of samples
MIN_SAMPLES = 30                  # half an hour of REM looks before tiredness is said at all
EVERY_S = 50                      # at most one sample a minute (rem/state is asked per user, and by the Health page)
BUSY_UTIL = 50                    # a GPU counts as busy from 50 % load
HEAT_HALF_C = 15                  # 15 °C from the thermal limit = half stressed; at the limit = fully
_lock = threading.Lock()


def _sat(n: float, half: float) -> float:
    """0 at 0, 0.5 at `half`, towards 1 beyond: a count made into a feeling without a hard cap."""
    return 0.0 if n <= 0 else round(n / (n + max(half, 1e-9)), 2)


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "mood_samples.json"


def gpus() -> list[dict]:
    """Load, temperature and the distance from the thermal limit as the driver gives it (T.Limit), per GPU."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,temperature.gpu,temperature.gpu.tlimit",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    res = []
    for line in out.strip().splitlines():
        try:
            i, util, temp, margin = (x.strip() for x in line.split(","))
            res.append({"index": int(i), "util": int(util), "temp_c": int(temp),
                        "margin_c": int(margin) if margin.lstrip("-").isdigit() else None})
        except ValueError:
            continue
    return res


def _samples(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def record(cfg: sys_config.Config, busy: bool, g: list[dict] | None = None) -> None:
    """One sample of how busy the machine is (the REM's look, once a minute): kept for WINDOW_H hours."""
    now = time.time()
    with _lock:
        rows = [r for r in _samples(cfg) if now - r["at"] < WINDOW_H * 3600]
        if rows and now - rows[-1]["at"] < EVERY_S:
            return
        g = gpus() if g is None else g
        rows.append({"at": round(now), "gpu": max((x["util"] for x in g), default=0), "busy": bool(busy)})
        f = _file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        os.replace(tmp, f)


def tiredness(cfg: sys_config.Config) -> dict:
    now = time.time()
    rows = [r for r in _samples(cfg) if now - r["at"] < WINDOW_H * 3600]
    if len(rows) < MIN_SAMPLES:
        return {"value": None, "causes": [f"non misurata: {len(rows)} campioni su {MIN_SAMPLES}"]}
    share = sum(1 for r in rows if r["busy"] or r["gpu"] >= BUSY_UTIL) / len(rows)
    hours = (rows[-1]["at"] - rows[0]["at"]) / 3600
    return {"value": round(share, 2), "causes": [f"GPU occupata il {share:.0%} delle ultime {hours:.1f} ore"]}


def measure(cfg: sys_config.Config, st: dict | None = None, active_runs: int = 0, admin: bool = True) -> dict:
    """{"on", "emotions": {name: {"value", "causes"}}, "dominant", "at"}: every value from a measure of now. `st`: the
    REM state (drives, idle, weather, health problems); `admin`: the machine's worries (Security) are the admin's."""
    from . import sys_logread
    if not cfg["AURORA_MOOD"]:
        return {"on": False, "emotions": {}, "dominant": None, "at": time.time()}
    st = st or {}
    out: dict[str, dict] = {}

    g = gpus()
    parts = []
    if g:
        top = max(g, key=lambda x: x["util"])
        if top["util"] >= 5:
            parts.append((top["util"] / 100, f"GPU{top['index']} al {top['util']}%"))
        near = [x for x in g if x["margin_c"] is not None]
        hot = min(near, key=lambda x: x["margin_c"]) if near else None
        if hot and hot["margin_c"] < 2 * HEAT_HALF_C:     # warm: from 30 °C below the limit (idle here: 51–55, M124)
            heat = 1.0 if hot["margin_c"] <= 0 else round(HEAT_HALF_C / (HEAT_HALF_C + hot["margin_c"]), 2)
            parts.append((heat, f"GPU{hot['index']} a {hot['temp_c']} °C, {hot['margin_c']} °C dal limite"))
    slots = max(1, int(cfg["AURORA_LLM_PARALLEL"] or 1))
    if active_runs:
        parts.append((min(1.0, active_runs / slots), f"{active_runs} risposte in corso su {slots} posti"))
    hour = sys_logread.answer_stats(1, cfg)
    if hour["errors"]:
        parts.append((_sat(hour["errors"], 1), f"{hour['errors']} errori nell'ultima ora"))
    if parts:
        v = max(p[0] for p in parts)
        out["stress"] = {"value": round(v, 2), "causes": [p[1] for p in sorted(parts, key=lambda p: -p[0])[:2]]}
    elif g:
        out["stress"] = {"value": 0.0, "causes": ["GPU a riposo e fresche, nessun errore nell'ultima ora"]}
    else:
        out["stress"] = {"value": None, "causes": ["non misurato: nessuna GPU letta"]}

    day = sys_logread.answer_stats(24, cfg)
    found = day["answers"] - day["by_outcome"].get("abstained", 0)
    asked = day["answers"] + day["errors"]
    out["satisfaction"] = ({"value": round(found / asked, 2),
                            "causes": [f"{found} domande su {asked} con una risposta (24 h)"]}
                           if asked else {"value": None, "causes": ["nessuna domanda nelle ultime 24 ore"]})

    d = st.get("drives") or {}
    todo = int(st.get("to_study") or 0) + int(d.get("novelty") or 0)
    night = int(cfg["AURORA_STUDY_PER_NIGHT"]) + int(cfg["AURORA_REVIEW_PER_DAY"])
    out["curiosity"] = {"value": _sat(todo, night),
                        "causes": [f"{st.get('to_study') or 0} domande da studiare",
                                   f"{d.get('novelty') or 0} risposte passate con qualcosa di nuovo da guardare"]}

    out["tiredness"] = tiredness(cfg)

    idle = st.get("idle_min")
    out["longing"] = ({"value": _sat(idle, float(cfg["AURORA_REM_BORED_MIN"])),
                       "causes": [f"nessun messaggio da {idle / 60:.1f} ore"]}
                      if idle is not None else {"value": None, "causes": ["nessuna conversazione ancora"]})

    w = st.get("weather") or {}
    if w.get("clouds_pct") is not None:
        rain = float(w.get("rain_mm") or 0)
        v = max(0.5 * w["clouds_pct"] / 100, _sat(rain, 1.0)) if rain else 0.5 * w["clouds_pct"] / 100
        out["melancholy"] = {"value": round(v, 2), "causes": [f"cielo coperto al {w['clouds_pct']}%"
                                                              + (f", {rain} mm di pioggia" if rain else "")
                                                              + f" a {w.get('place') or 'casa'}"]}
    else:
        out["melancholy"] = {"value": None, "causes": ["meteo non misurato"]}

    worries = []
    if admin:
        try:
            from .sec_incidents import Incidents
            hi = [i for i in Incidents(cfg.base or cfg).list("open", False) if i.get("severity") in ("high", "critical")]
            if hi:
                worries.append((len(hi), f"{len(hi)} incidenti gravi aperti in Sicurezza"))
        except (OSError, ValueError):
            pass
    problems = st.get("health_problems")
    if problems:
        worries.append((len(problems), f"in Salute: {', '.join(x.split(':')[0] for x in problems[:3])}"))   # the names
    n = sum(w[0] for w in worries)
    out["worry"] = {"value": _sat(n, 1), "causes": [w[1] for w in worries] or ["nessun incidente grave, salute in ordine"]}

    known = {k: v["value"] for k, v in out.items() if v["value"] is not None and k != "satisfaction"}
    top = max(known, key=known.get) if known else None
    return {"on": True, "emotions": out, "dominant": top if top and known[top] >= 0.5 else "serenity", "at": time.time()}


def words(m: dict, lang: str = "it") -> str:
    """The mood in one line, for the prompts that write as her (high emotions only, with their causes)."""
    if not m.get("on"):
        return ""
    high = [(k, v) for k, v in m["emotions"].items() if v["value"] is not None and v["value"] >= 0.5]
    if not high:
        return "serena: nulla di misurato ti pesa" if lang == "it" else "serene: nothing measured weighs on you"
    label = LABELS["it" if lang == "it" else "en"]
    return "; ".join(f"{label[k]} {v['value']:.1f} ({', '.join(v['causes'][:2])})" for k, v in high)


LABELS = {"it": {"stress": "stress", "satisfaction": "soddisfazione", "curiosity": "curiosità", "tiredness": "stanchezza",
                 "longing": "nostalgia", "melancholy": "malinconia", "worry": "preoccupazione", "serenity": "serenità"},
          "en": {"stress": "stress", "satisfaction": "satisfaction", "curiosity": "curiosity", "tiredness": "tiredness",
                 "longing": "longing", "melancholy": "melancholy", "worry": "worry", "serenity": "serenity"}}


def _last_file(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "mood.json"


def save(cfg: sys_config.Config, m: dict) -> None:
    """The last measure (REM's look, each minute): what her own prompts read, without measuring again."""
    f = _last_file(cfg)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def last(cfg: sys_config.Config, max_age_s: float = 900) -> dict | None:
    """The last measure if it is recent (15 min), else None: an old mood is not said as today's."""
    if not cfg["AURORA_MOOD"]:
        return None
    try:
        m = json.loads(_last_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if time.time() - float(m.get("at", 0)) <= max_age_s else None


def compact(m: dict | None) -> dict | str:
    """For the facts about herself: {emotion: {"value", "why"}}, the dominant one first."""
    if not m or not m.get("on"):
        return "not measured" if m is None else "off (AURORA_MOOD)"
    return {"dominant": m["dominant"], **{k: {"value": v["value"], "why": v["causes"]} for k, v in m["emotions"].items()}}


THE = {"it": {"stress": "lo stress", "curiosity": "la curiosità", "tiredness": "la stanchezza", "longing": "la nostalgia",
              "melancholy": "la malinconia", "worry": "la preoccupazione", "serenity": "la serenità"},
       "en": {"stress": "stress", "curiosity": "curiosity", "tiredness": "tiredness", "longing": "longing",
              "melancholy": "melancholy", "worry": "worry", "serenity": "serenity"}}


def feeling(m: dict, lang: str = "it") -> str:
    """One sentence for the good morning: the emotion that prevails and its first cause (no gendered adjective)."""
    it = lang.startswith("it")
    top = m.get("dominant") or "serenity"
    the = THE["it" if it else "en"].get(top, top)
    if top == "serenity":
        return "Stamattina prevale la serenità: nulla di misurato mi pesa." if it else "This morning serenity prevails: nothing measured weighs on me."
    cause = (m["emotions"].get(top, {}).get("causes") or [""])[0]
    return f"Stamattina prevale {the}: {cause}." if it else f"This morning {the} prevails: {cause}."
