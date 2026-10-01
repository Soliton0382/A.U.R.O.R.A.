# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Live machine metrics for the WebUI: CPU, RAM, GPUs. Sampled at most every 1.5 s."""
from __future__ import annotations

import subprocess
import threading
import time

_lock = threading.Lock()
_state: dict = {"at": 0.0, "value": None, "cpu": None}


def _cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return idle, sum(v)


def _ram() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) // 1024                     # MiB
    return {"used_mib": info["MemTotal"] - info["MemAvailable"], "total_mib": info["MemTotal"],
            "swap_used_mib": info["SwapTotal"] - info["SwapFree"]}


def _gpus() -> list[dict]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        i, name, util, used, total, temp = [x.strip() for x in line.split(",")]
        gpus.append({"index": int(i), "name": name, "util_pct": int(util), "used_mib": int(used),
                     "total_mib": int(total), "temp_c": int(temp)})
    return gpus


def sample() -> dict:
    with _lock:
        if _state["value"] and time.time() - _state["at"] < 1.5:
            return _state["value"]
        idle, total = _cpu_times()
        prev = _state["cpu"]
        cpu = None if not prev or total == prev[1] else round(100 * (1 - (idle - prev[0]) / (total - prev[1])), 1)
        _state["cpu"] = (idle, total)
        value = {"cpu_pct": cpu, "ram": _ram(), "gpus": _gpus(), "at": time.time()}
        _state.update(at=time.time(), value=value)
        return value
