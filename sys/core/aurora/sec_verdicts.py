# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's verdicts kept apart from the incidents (C406). incidents.json keeps its last 1,000 incidents only
(sec_incidents.Incidents._save); with 30–270 incidents a day the file held 11 days and the verdicts went with the
incidents they were given on: the autopilot's judgement, 10 verdicts per kind, closed 62 alerts on 9–13 Nov and none
after, because «31 of 31» had fallen to fewer than 10 — and the owner judged again what he had judged before.

Each verdict is copied here with what sec_quiet needs to count it (its pattern, what it is, which device), kept KEEP_DAYS
(more than sec_quiet.WINDOW_DAYS, which still decides what counts) and at most KEEP_MAX. merged() gives the incidents
plus the verdicts whose incidents have left the file; the newest verdict on an incident wins.
State: <STATUS>/incident_verdicts.json, a list of records."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import sec_quiet, sys_config

KEEP_DAYS = 90
KEEP_MAX = 5000            # a judged week was 197 verdicts (M274): 5,000 is half a year of that
FIELDS = ("id", "kind", "source", "internal", "known", "severity", "received_ts", "verdict", "verdict_at")
_lock = threading.Lock()


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "incident_verdicts.json"


def load(cfg: sys_config.Config) -> list[dict]:
    try:
        out = json.loads(_file(cfg).read_text(encoding="utf-8"))
        return out if isinstance(out, list) else []
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(tmp, f)


def record(item: dict) -> dict:
    """What is kept of a judged incident: enough for sec_quiet's patterns and sec_autopilot's kinds."""
    return {**{k: item.get(k) for k in FIELDS}, "_what": sec_quiet.what(item), "_pattern": sec_quiet.pattern(item)}


def keep(cfg: sys_config.Config, items: list[dict], now: float | None = None) -> list[dict]:
    """The verdicts of `items` added or brought up to date, the old ones dropped; returns the ledger."""
    now = time.time() if now is None else now
    with _lock:
        rows = load(cfg)
        by_id = {r.get("id"): r for r in rows}
        changed = False
        for i in items:
            if not i.get("verdict") or not i.get("id"):
                continue
            old = by_id.get(i["id"])
            if old is None or old.get("verdict") != i["verdict"] or old.get("verdict_at") != i.get("verdict_at"):
                by_id[i["id"]] = record(i)
                changed = True
        since = now - KEEP_DAYS * 86400
        kept = [r for r in by_id.values() if float(r.get("verdict_at") or r.get("received_ts") or 0) >= since]
        kept.sort(key=lambda r: float(r.get("verdict_at") or 0))
        kept = kept[-KEEP_MAX:]
        if changed or len(kept) != len(rows):
            _save(cfg, kept)
    return kept


def merged(cfg: sys_config.Config, items: list[dict]) -> list[dict]:
    """The incidents, then the verdicts whose incidents are no longer among them (older first, as list() orders)."""
    here = {i.get("id") for i in items}
    gone = [r for r in keep(cfg, items) if r.get("id") not in here]
    return list(items) + sorted(gone, key=lambda r: -float(r.get("verdict_at") or 0))
