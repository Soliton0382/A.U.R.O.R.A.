# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Live machine metrics for the WebUI: CPU, RAM, GPUs, the network's traffic and the cloud calls. Sampled at most
every 1.5 s."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

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
        try:                                             # a driver's message instead of a row (no GPU in a cage,
            i, name, util, used, total, temp = [x.strip() for x in line.split(",")]   # a driver being updated): none
            gpus.append({"index": int(i), "name": name, "util_pct": int(util), "used_mib": int(used),
                         "total_mib": int(total), "temp_c": int(temp)})
        except ValueError:
            continue
    return gpus


def _net_bytes() -> tuple[int, int, int]:
    """(received, sent, link Mbit/s) of the physical interfaces (those with a device: not lo, docker, bridges, VMs)."""
    rx = tx = link = 0
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()[2:]
    except OSError:
        return 0, 0, 0
    for line in lines:
        name, data = line.split(":", 1)
        name = name.strip()
        if not (Path("/sys/class/net") / name / "device").exists():
            continue
        v = data.split()
        rx, tx = rx + int(v[0]), tx + int(v[8])
        try:
            link = max(link, int((Path("/sys/class/net") / name / "speed").read_text()))
        except (OSError, ValueError):                 # a Wi-Fi card says no speed: the wired one sets it
            pass
    return rx, tx, link


def _net(now: float) -> dict:
    """Bytes a second in and out since the last sample, and the busier of the two as a share of the link."""
    rx, tx, link = _net_bytes()
    prev = _state.get("net")
    _state["net"] = (now, rx, tx)
    if not prev or now <= prev[0]:
        return {"rx_bps": None, "tx_bps": None, "link_mbps": link or None, "pct": None}
    dt = now - prev[0]
    rxb, txb = max(0, rx - prev[1]) / dt, max(0, tx - prev[2]) / dt
    pct = round(100 * max(rxb, txb) * 8 / (link * 1e6), 1) if link > 0 else None
    return {"rx_bps": round(rxb), "tx_bps": round(txb), "link_mbps": link or None, "pct": pct}


def sample() -> dict:
    with _lock:
        if _state["value"] and time.time() - _state["at"] < 1.5:
            return _state["value"]
        idle, total = _cpu_times()
        prev = _state["cpu"]
        cpu = None if not prev or total == prev[1] else round(100 * (1 - (idle - prev[0]) / (total - prev[1])), 1)
        _state["cpu"] = (idle, total)
        from . import mdl_router
        now = time.time()
        value = {"cpu_pct": cpu, "ram": _ram(), "gpus": _gpus(), "net": _net(now), "cloud": mdl_router.cloud_live(),
                 "at": now}
        _state.update(at=time.time(), value=value)
        return value
