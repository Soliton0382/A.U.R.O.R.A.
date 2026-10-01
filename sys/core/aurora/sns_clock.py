# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's sense of time: the exact local time, always, in every prompt that needs it."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import sys_config

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def now(cfg: sys_config.Config | None = None) -> datetime:
    cfg = cfg or sys_config.get()
    return datetime.now(ZoneInfo(cfg["AURORA_TIMEZONE"]))


def now_text(cfg: sys_config.Config | None = None) -> str:
    """e.g. 'mercoledì 2026-09-30 10:31:05 CEST (Europe/Rome)': weekday in Italian, ISO date, zone."""
    t = now(cfg)
    return f"{DAYS_IT[t.weekday()]} {t:%Y-%m-%d %H:%M:%S} {t.tzname()} ({t.tzinfo.key})"


def local(iso: str, cfg: sys_config.Config | None = None) -> str:
    """A stored ISO timestamp in local time, to the minute: '2026-09-30 10:31'."""
    cfg = cfg or sys_config.get()
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(cfg["AURORA_TIMEZONE"])).strftime("%Y-%m-%d %H:%M")


def when(iso: str, cfg: sys_config.Config | None = None) -> str:
    """A stored timestamp as Aurora should read it: 'mercoledì 2026-09-30 11:22 (ieri)'.
    The relative day is computed here, never left to the model (it once called the 29th "ieri" on the 1st)."""
    cfg = cfg or sys_config.get()
    t = datetime.fromisoformat(iso).astimezone(ZoneInfo(cfg["AURORA_TIMEZONE"]))
    days = (now(cfg).date() - t.date()).days
    rel = {0: "oggi", 1: "ieri", 2: "l'altro ieri"}.get(days, f"{days} giorni fa" if days > 0 else "nel futuro?")
    return f"{DAYS_IT[t.weekday()]} {t:%Y-%m-%d %H:%M} ({rel})"
