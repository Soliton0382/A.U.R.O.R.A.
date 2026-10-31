# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌅 A clean start every morning (owner, 1 Nov: «lasciare il riavvio propedeutico dopo la fase rem o cmq dopo i giri
notturni così il sistema resta sempre pulito e la crescita resta controllata»).

aurora-api's anonymous memory still rises slowly between restarts after the trims (C389, M270: ~+190 MiB a day). Once a
day, after the night's work — from the end of the dream window (AURORA_REM_DREAM_HOURS) for WINDOW_H hours, with no
autonomic task left — aurora-rem asks the API to restart itself, and only when nothing would be lost or broken:

- the ethics code intact (else the API would not start again: C430);
- no GPU job, and the local reasoner's slots idle;
- no run open, and no person's question in the last QUIET_S;
- no backup running.

A check that fails is said in rem's log and tried again at the next tick; a window that passes without a clean moment
is said once and the day skipped. AURORA_NIGHT_RESTART off = never."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx

from . import sys_config

WINDOW_H = 3                     # with the default dream window 2-6: from 6 to 9
QUIET_S = 600                    # a person's question in the last 10 minutes: wait
PEOPLE = ("webui", "openai", "acquire")   # a person's runs (api/routines.PEOPLE); routines, REM, forge… are hers


def _end(cfg: sys_config.Config) -> int:
    return int(str(cfg["AURORA_REM_DREAM_HOURS"]).split("-")[1]) % 24


def in_window(cfg: sys_config.Config, now: datetime) -> bool:
    return (now.hour - _end(cfg)) % 24 < WINDOW_H


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "fresh_start.txt"


def done_today(cfg: sys_config.Config, now: datetime) -> bool:
    try:
        return _file(cfg).read_text(encoding="ascii").strip() == now.date().isoformat()
    except OSError:
        return False


def mark(cfg: sys_config.Config, now: datetime) -> None:
    _file(cfg).write_text(now.date().isoformat(), encoding="ascii")


def _slots_busy(cfg: sys_config.Config) -> bool:
    if str(cfg["AURORA_LLM_BACKEND"]) == "cloud":
        return False
    try:
        slots = httpx.get(f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/slots", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        return False                                   # not answering: nothing of it to wait for
    return any(s.get("is_processing") for s in slots if isinstance(s, dict))


def why_not(cfg: sys_config.Config, runs: list[dict], backup_running: bool, now: float | None = None) -> str | None:
    """What a restart now would lose or break, in words; None when it is clean. `runs`: every user's (api/core._runs)."""
    from . import sys_ethics, sys_health
    now = time.time() if now is None else now
    ok, reason = sys_ethics.integrity()
    if not ok:
        return f"ethics code: {reason}"
    job = sys_health.gpu_job(cfg)
    if job:
        return f"the GPU: {job}"
    if _slots_busy(cfg):
        return "the local reasoner is answering"
    open_ = [r for r in runs if not r.get("done")]
    if open_:
        return f"{len(open_)} run(s) open"
    if any(r.get("origin") in PEOPLE and now - float(r.get("started") or 0) < QUIET_S for r in runs):
        return f"a person asked in the last {QUIET_S // 60} minutes"
    if backup_running:
        return "a backup is running"
    return None


def tick(cfg: sys_config.Config, now: datetime, idle: bool, said: str, ask: Callable[[], str | None],
         restart: Callable[[], None], log) -> str:
    """One look of aurora-rem (`idle`: no autonomic task left for anyone). `ask`: the API's why_not; `restart`: the
    API restarted. → the reason said last («» when none), so that a wait is logged once."""
    if done_today(cfg, now):
        return said
    if not in_window(cfg, now):
        if said:                                      # the window just closed without a clean moment
            log.info("morning restart skipped today: %s", said)
            mark(cfg, now)
        return ""
    why = None if idle else "the night's work still going"
    if why is None:
        try:
            why = ask()
        except Exception as e:  # noqa: BLE001 — the API not answering: wait, never restart blind
            why = f"the check failed: {e}"
    if why:
        if why != said:
            log.info("morning restart waits: %s", why)
        return why
    try:
        restart()
        log.info("morning restart: aurora-api restarted after the night's work")
    except Exception as e:  # noqa: BLE001
        log.warning("morning restart failed: %s", e)
    mark(cfg, now)                                    # once a day, failed or not
    return ""
