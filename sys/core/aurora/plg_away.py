# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin's scheduled pause (owner, 2026-10-27: «una sezione dove possiamo impostare una finestra temporale che indica
tipo indisponibilità programmata… disattivata di default», for a service that is off at the same hours every night).

The window is set on the plugin's page (api/agents) and kept with its on/off state in <STATUS>/plugins.json as
{"away": {"on": bool, "from": "HH:MM", "to": "HH:MM"}}, in this machine's local time; a window whose end comes before
its start goes across midnight. Inside it the plugin is not available (plg_host.Plugin.available): the routines that
look at it skip it in silence, and a call says until when it is paused instead of reaching a service that is off."""
from __future__ import annotations

import json
import re
import time

OFF = {"on": False, "from": "", "to": ""}
_HM = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


def _minutes(hm: str) -> int:
    m = _HM.fullmatch(hm or "")
    if not m:
        raise ValueError(f"not a time HH:MM: {hm!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def clean(window: dict | None) -> dict:
    """The window as stored: off by default; switched on only with two valid, different times (ValueError otherwise)."""
    w = {**OFF, **{k: v for k, v in (window or {}).items() if k in OFF}}
    w["on"] = bool(w["on"])
    if w["on"] and _minutes(w["from"]) == _minutes(w["to"]):
        raise ValueError("the pause starts and ends at the same time")
    return w


def of(cfg, name: str) -> dict:
    """A plugin's window read from its state alone, for a loop that looks every few seconds (no manifests read)."""
    try:
        st = json.loads((cfg.path("AURORA_STATUS_DIR") / "plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return st.get(name, {}).get("away", {}) if isinstance(st.get(name), dict) else {}


def paused(window: dict | None, now: float | None = None) -> bool:
    """Inside the window now (a window switched off, or unreadable, never is)."""
    w = window or {}
    if not w.get("on"):
        return False
    try:
        start, end = _minutes(w.get("from", "")), _minutes(w.get("to", ""))
    except ValueError:
        return False
    t = time.localtime(time.time() if now is None else now)
    m = t.tm_hour * 60 + t.tm_min
    return start <= m < end if start < end else (m >= start or m < end)
