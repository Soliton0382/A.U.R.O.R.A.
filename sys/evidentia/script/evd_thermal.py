#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The machine's temperatures while the long jobs run (owner, 10 Nov: «tieni monitorato temperature e consumi prima
che fonde la macchina»). Every 20 s: each GPU's temperature and power (nvidia-smi), the CPU's Tctl (k10temp), the load.
A GPU at GPU_HOT °C pauses the embedding (SIGSTOP), the CPU at CPU_HOT °C three readings in a row pauses the OCR; each
goes on (SIGCONT) once 10 °C cooler. Paused, never killed: nothing is lost. A line on stdout for every pause, resume
and, every 10 minutes, the readings; all of them in sys/logs/thermal.log.

    .venv/bin/python sys/evidentia/script/evd_thermal.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "sys" / "logs" / "thermal.log"
GPU_HOT, CPU_HOT, COOL = 85, 95, 10        # 7700X: Tjmax 95 °C; RTX 5060 Ti slows itself near 90 °C
EVERY, SUMMARY = 20, 600
JOBS = {"gpu": ("evd_embed.py",), "cpu": ("evd_inventory.py",)}


def gpus() -> list[tuple[int, int, float]]:
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=30).stdout
    return [(int(i), int(t), float(p)) for i, t, p in (line.split(", ") for line in out.strip().splitlines())]


def tctl() -> int:
    for d in Path("/sys/class/hwmon").iterdir():
        if (d / "name").read_text().strip() == "k10temp":
            return int((d / "temp1_input").read_text()) // 1000
    return -1


PY_OPTS_WITH_ARG = ("-W", "-X", "--check-hash-based-pycs")     # interpreter options whose value is the next argument


def runs(cmdline: bytes, scripts: tuple[str, ...]) -> bool:
    """True when this /proc cmdline is a Python interpreter running one of the scripts: argv[0] is python*, and the
    first argument that is not an interpreter option is the script, matched by its basename. A substring of the
    whole line matched an editor open on evd_embed.py and stopped it (B33). «-c» and «-m» run code or a module, never
    one of the scripts; whatever follows them is theirs."""
    argv = [a.decode("utf-8", "replace") for a in cmdline.split(b"\0") if a]
    if not argv or not os.path.basename(argv[0]).startswith("python"):
        return False
    skip = False
    for a in argv[1:]:
        if skip:
            skip = False
            continue
        if a in ("-c", "-m"):
            return False
        if a.startswith("-") and a != "-":
            skip = a in PY_OPTS_WITH_ARG
            continue
        return os.path.basename(a) in scripts
    return False


def pids(kind: str) -> list[int]:
    """The job's processes and every child of theirs (tesseract, the pool's workers)."""
    procs = {}
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                cmd = (p / "cmdline").read_bytes()
                ppid = int((p / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
            procs[int(p.name)] = (cmd, ppid)
    roots = {pid for pid, (cmd, _) in procs.items() if runs(cmd, JOBS[kind]) and pid != os.getpid()}
    found, grew = set(roots), True
    while grew:
        grew = False
        for pid, (_, ppid) in procs.items():
            if ppid in found and pid not in found:
                found.add(pid)
                grew = True
    return sorted(found)


def signal_all(kind: str, sig: int) -> int:
    n = 0
    for pid in pids(kind):
        try:
            os.kill(pid, sig)
            n += 1
        except OSError:
            pass
    return n


def say(text: str, out: bool = True) -> None:
    line = f"{time.strftime('%d/%m %H:%M:%S')} {text}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if out:
        print(line, flush=True)


def main() -> int:
    paused = {"gpu": False, "cpu": False}
    hot_cpu, last = 0, 0.0
    say("guard on: GPU pause at %d °C, CPU pause at %d °C (3 readings), resume %d °C cooler" % (GPU_HOT, CPU_HOT, COOL))
    while True:
        try:
            g, c = gpus(), tctl()
        except Exception as e:                       # noqa: BLE001 — a failed reading is said, the guard goes on
            say(f"reading failed: {e}")
            time.sleep(EVERY)
            continue
        load = os.getloadavg()[0]
        reading = " · ".join(f"GPU{i} {t}°C {p:.0f}W" for i, t, p in g) + f" · CPU {c}°C · load {load:.1f}"
        say(reading, out=False)
        top = max(t for _, t, _ in g)
        if not paused["gpu"] and top >= GPU_HOT:
            paused["gpu"] = True
            say(f"⏸️ GPU hot ({top}°C): embedding paused ({signal_all('gpu', signal.SIGSTOP)} processes)")
        elif paused["gpu"] and top <= GPU_HOT - COOL:
            paused["gpu"] = False
            say(f"▶️ GPU {top}°C: embedding resumed ({signal_all('gpu', signal.SIGCONT)} processes)")
        hot_cpu = hot_cpu + 1 if c >= CPU_HOT else 0
        if not paused["cpu"] and hot_cpu >= 3:
            paused["cpu"] = True
            say(f"⏸️ CPU hot ({c}°C): OCR paused ({signal_all('cpu', signal.SIGSTOP)} processes)")
        elif paused["cpu"] and c <= CPU_HOT - COOL:
            paused["cpu"] = False
            say(f"▶️ CPU {c}°C: OCR resumed ({signal_all('cpu', signal.SIGCONT)} processes)")
        if time.time() - last >= SUMMARY:
            last = time.time()
            say("🌡️ " + reading)
        time.sleep(EVERY)


def _stop(*_):
    for kind in JOBS:                                    # stopped: nothing left paused behind it
        signal_all(kind, signal.SIGCONT)
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:                            # stopped: nothing left paused behind it
        for kind in JOBS:
            signal_all(kind, signal.SIGCONT)
