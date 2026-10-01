# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Is Aurora well? Every service, checked two ways, plus disk and GPU memory.

 service      systemd state (is-active) and a real check: its HTTP health, or for the daemons
              without a port a recent line in their own log
 disk         free space where the installation lives
 gpu          memory used on each GPU
Levels: ok (green), warn (yellow: degraded, keeps working), down (red: something does not work).
The overall level is the worst one; each problem has a sentence that says what is wrong.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime

import httpx

from . import sys_config, sys_metrics

LEVEL = {"ok": 0, "warn": 1, "down": 2}


def _unit(name: str) -> str:
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _http(url: str) -> tuple[bool, str]:
    try:
        r = httpx.get(url, timeout=4)
        return r.status_code < 500, f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        return False, type(e).__name__


def _https(domain: str, port: int) -> tuple[bool, str]:
    """A real HTTPS request to the public name, answered by this machine (SNI and certificate checked)."""
    try:
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",
                              "--resolve", f"{domain}:{port}:127.0.0.1", f"https://{domain}:{port}/health"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out.isdigit() and 0 < int(out) < 500, f"HTTP {out or '-'}"
    except (OSError, subprocess.SubprocessError) as e:
        return False, type(e).__name__


def heartbeat(cfg, name: str) -> None:
    """Daemons without a port say they are alive by touching this file (checked by check())."""
    f = cfg.path("AURORA_STATUS_DIR") / "heartbeat" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()


def _beat_age_min(cfg, name: str) -> float | None:
    f = cfg.path("AURORA_STATUS_DIR") / "heartbeat" / name
    return (time.time() - f.stat().st_mtime) / 60 if f.exists() else None


def check(cfg: sys_config.Config | None = None) -> dict:
    cfg = cfg or sys_config.get()
    items = []

    def add(name, level, text, detail=""):
        items.append({"name": name, "level": level, "text": text, "detail": detail})

    web = [("aurora-api", f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/health"),
           ("aurora-models", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
           ("aurora-llm", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")]
    for unit, url in web:
        state = _unit(unit)
        ok, how = _http(url)
        if state == "active" and ok:
            add(unit, "ok", "attivo e risponde", how)
        elif ok:
            add(unit, "warn", f"risponde ma systemd dice {state!r}", how)
        else:
            add(unit, "down", f"non risponde ({how}), systemd: {state}", url)

    state = _unit("aurora-https")
    ok, how = _https(cfg["AURORA_DOMAIN"], cfg["AURORA_HTTPS_PORT"])
    add("aurora-https", "ok" if state == "active" and ok else "down",
        "HTTPS attivo" if state == "active" and ok else f"HTTPS non risponde ({how}), systemd: {state}", how)

    for unit, beat, limit_min in (("aurora-rem", "rem", 3 * cfg["AURORA_REM_TICK_S"] / 60 + 2), ("aurora-harvester", "harvester", 5),
                                  ("aurora-sentinel", "sentinel", 5)):
        state, age = _unit(unit), _beat_age_min(cfg, beat)
        if state != "active":
            add(unit, "down", f"fermo (systemd: {state})")
        elif age is None or age > limit_min:
            add(unit, "warn", f"attivo ma senza battito da {age:.0f} min" if age is not None else "attivo, nessun battito",
                f"atteso ogni {limit_min:.0f} min")
        else:
            add(unit, "ok", "attivo", f"battito {age * 60:.0f} s fa")

    du = shutil.disk_usage(cfg.root)
    free = du.free / du.total
    add("disco", "down" if free < 0.03 else "warn" if free < 0.10 else "ok",
        f"{du.free / 2**30:.0f} GB liberi ({free:.0%})")
    for g in sys_metrics.sample()["gpus"]:
        used = g["used_mib"] / g["total_mib"]
        add(f"GPU{g['index']}", "warn" if used > 0.97 else "ok",
            f"VRAM {g['used_mib'] / 1024:.1f}/{g['total_mib'] / 1024:.1f} GB · carico {g['util_pct']}% · {g['temp_c']} °C")

    from . import sys_ethics                             # the code as the owner signed it (second tier)
    drift = sys_ethics.drift_summary(sys_ethics.code_drift(cfg.root))
    add("firma del codice", "warn" if drift else "ok", drift or "ogni file come firmato dal proprietario")

    worst = max((LEVEL[i["level"]] for i in items), default=0)
    return {"level": [k for k, v in LEVEL.items() if v == worst][0], "items": items,
            "problems": [f"{i['name']}: {i['text']}" for i in items if i["level"] != "ok"],
            "checked": datetime.now().astimezone().isoformat(timespec="seconds")}
