# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The routines' ticks, every one counted (C600). api.log says only the ticks over 10 s, so a quiet day left no
line and «a day of ticks under aurora-rem's 30 s» could not be read from it. Each tick adds its total and its steps'
times to today's counter, <AURORA_STATUS_DIR>/routine_ticks.json; the first tick of a new day closes the day before
into routine_ticks.jsonl (one line a day) and says it in api.log: ticks, over 30 s, the longest, the slowest step.
aurora-rem's daily soak snapshot carries the last closed day. `python -m aurora.sys_ticks` prints the days.
"""
from __future__ import annotations

import json
import os
import threading
import time

from . import sys_config

SLOW_S = 30                                  # aurora-rem's timeout for a tick: past it, C600 is not closed
FILE, DAYS = "routine_ticks.json", "routine_ticks.jsonl"
_lock = threading.Lock()


def _empty(day: str) -> dict:
    return {"day": day, "ticks": 0, "busy": 0, "deferred": 0, "over_slow": 0, "slow_s": SLOW_S, "max_s": 0.0,
            "max_at": "", "max_steps": {}, "steps": {}}


def _read(f) -> dict | None:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("day") else None
    except (OSError, ValueError):
        return None


def _write(f, d: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def slowest_step(d: dict) -> tuple[str, float]:
    """The step with the longest single time of the day (a step's sub-parts, «automations.due», count too)."""
    steps = d.get("steps") or {}
    if not steps:
        return "", 0.0
    name = max(steps, key=lambda k: steps[k].get("max_s", 0))
    return name, steps[name].get("max_s", 0.0)


def summary(d: dict) -> str:
    step, s = slowest_step(d)
    return (f"{d['day']}: {d['ticks']} ticks, {d['over_slow']} over {d.get('slow_s', SLOW_S)} s, longest "
            f"{d['max_s']:.1f} s, slowest step {step or '-'} ({s:.1f} s); {d.get('busy', 0)} skipped while one ran")


def record(cfg: sys_config.Config, total: float | None, steps: dict | None = None, deferred: bool = False,
           busy: bool = False, now: float | None = None, log=None) -> dict | None:
    """One tick counted (a skipped one, `busy`, without times). Returns the day it closed, if it closed one."""
    now = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    status = cfg.path("AURORA_STATUS_DIR")
    f = status / FILE
    with _lock:
        cur, closed = _read(f), None
        if cur is not None and cur["day"] != day:      # Aurora off at night: the first tick of the morning closes it
            closed = cur
            with open(status / DAYS, "a", encoding="utf-8") as h:
                h.write(json.dumps(closed, ensure_ascii=False) + "\n")
            if log is not None:
                log.info("routines ticks of %s", summary(closed))
            cur = None
        cur = cur or _empty(day)
        if busy:
            cur["busy"] += 1
        else:
            total = float(total or 0.0)
            cur["ticks"] += 1
            cur["deferred"] += bool(deferred)
            cur["over_slow"] += total > SLOW_S
            for k, v in (steps or {}).items():
                st = cur["steps"].setdefault(k, {"max_s": 0.0, "sum_s": 0.0})
                st["max_s"] = round(max(st["max_s"], float(v)), 2)
                st["sum_s"] = round(st["sum_s"] + float(v), 2)
            if total > cur["max_s"]:
                top = sorted((steps or {}).items(), key=lambda x: -x[1])[:6]
                cur.update(max_s=round(total, 2), max_at=time.strftime("%H:%M:%S", time.localtime(now)),
                           max_steps={k: round(float(v), 2) for k, v in top})
        _write(f, cur)
    return closed


def days(cfg: sys_config.Config, n: int = 14, with_today: bool = True) -> list[dict]:
    """The last `n` closed days, oldest first, and today's counter so far (marked «open»)."""
    status = cfg.path("AURORA_STATUS_DIR")
    out = []
    try:
        lines = (status / DAYS).read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        lines = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    if with_today and (cur := _read(status / FILE)) is not None:
        out.append({**cur, "open": True})
    return out


def last_day(cfg: sys_config.Config) -> dict | None:
    """The last closed day in short (aurora-rem's soak snapshot): ticks, over 30 s, the longest, the slowest step."""
    d = (days(cfg, 1, with_today=False) or [None])[-1]
    if d is None:
        return None
    step, s = slowest_step(d)
    return {"day": d["day"], "ticks": d["ticks"], "over_slow": d["over_slow"], "max_s": d["max_s"],
            "slowest_step": step, "slowest_step_s": s, "busy": d.get("busy", 0)}


if __name__ == "__main__":                          # python -m aurora.sys_ticks [days]
    import sys
    for d in days(sys_config.get(), int(sys.argv[1]) if len(sys.argv) > 1 else 14):
        print(summary(d) + ("  (today, open)" if d.get("open") else ""))
