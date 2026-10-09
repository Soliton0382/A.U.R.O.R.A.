# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The security autopilot's scorecard (owner, 2026-10-10: «mi serve capire se lo fa davvero bene… solo così posso
fidarmi a lasciarle il pilota automatico»; roadmap 81).

The owner judges each incident — right, false alarm, not sure — and every week is measured:
  incidents     how many, of which kind, from inside or outside
  reviewed      the share the owner judged
  precision     right / (right + false alarms)
  blind         minutes with no line from the firewall longer than BLIND_GAP_MIN (C242: 8 hours unnoticed)
The autopilot is «ready» only when READY_WEEKS weeks in a row reach the bar — numbers, not a feeling.
"""
from __future__ import annotations

import gzip
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import sys_config

VERDICTS = ("right", "false_alarm", "unsure")
BLIND_GAP_MIN = 30
READY_WEEKS = 2
BAR = {"reviewed": 0.8, "precision": 0.9, "min_reviewed": 5, "blind_min": 30}
WEEK = 7 * 86400


def gaps(folder: Path, since: float, until: float) -> list[tuple[float, float]]:
    """The silences longer than BLIND_GAP_MIN in the firewall's log between since and until: (start, end)."""
    stamps: list[float] = []
    for f in sorted(folder.glob("firewall*")):
        if f.stat().st_mtime < since:
            continue
        op = gzip.open if f.suffix == ".gz" else open
        with op(f, "rt", errors="replace") as fh:
            for line in fh:
                try:
                    t = datetime.fromisoformat(line[:29]).timestamp()
                except ValueError:
                    continue
                if since <= t <= until:
                    stamps.append(t)
    stamps.sort()
    edges = [since, *stamps, min(until, time.time())] if stamps else [since, min(until, time.time())]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b - a > BLIND_GAP_MIN * 60]


def week(items: list[dict], start: float, end: float, silences: list[tuple[float, float]]) -> dict:
    inside = [i for i in items if start <= float(i.get("received_ts") or 0) < end]
    v = Counter(i.get("verdict") for i in inside if i.get("verdict") in VERDICTS)
    judged = v["right"] + v["false_alarm"]
    blind = sum(min(b, end) - max(a, start) for a, b in silences if b > start and a < end) / 60
    return {"from": start, "to": end, "incidents": len(inside),
            "kinds": dict(Counter(i.get("kind") for i in inside).most_common(6)),
            "internal": sum(1 for i in inside if i.get("internal")),
            "reviewed": sum(v.values()), "right": v["right"], "false_alarm": v["false_alarm"], "unsure": v["unsure"],
            "reviewed_share": round(sum(v.values()) / len(inside), 2) if inside else None,
            "precision": round(v["right"] / judged, 2) if judged else None, "blind_min": round(blind)}


def passes(w: dict) -> list[str]:
    """What keeps a week under the bar (empty: it passes)."""
    why = []
    if w["reviewed"] < BAR["min_reviewed"]:
        why.append(f"giudicati {w['reviewed']} incidenti (ne servono almeno {BAR['min_reviewed']})")
    if w["reviewed_share"] is not None and w["reviewed_share"] < BAR["reviewed"]:
        why.append(f"giudicato il {w['reviewed_share']:.0%} (serve l'{BAR['reviewed']:.0%})")
    if w["precision"] is not None and w["precision"] < BAR["precision"]:
        why.append(f"precisione {w['precision']:.0%} (serve il {BAR['precision']:.0%})")
    if w["blind_min"] > BAR["blind_min"]:
        why.append(f"cieca per {w['blind_min']} min (il firewall non ha mandato niente)")
    return why


def scorecard(cfg: sys_config.Config, weeks: int = READY_WEEKS, now: float | None = None, items: list | None = None,
              silences: list | None = None) -> dict:
    from .sec_incidents import Incidents
    now = now or time.time()
    items = items if items is not None else Incidents(cfg).list(None, True)
    since = now - weeks * WEEK
    if silences is None:
        silences = gaps(cfg.path("AURORA_LOG_DIR") / "firewall", since, now)
    out = [week(items, now - (k + 1) * WEEK, now - k * WEEK, silences) for k in range(weeks)]
    for w in out:
        w["short"] = passes(w)
    ready = all(not w["short"] for w in out)
    return {"weeks": out, "ready": ready, "bar": BAR, "blind_gaps": [(round(a), round(b)) for a, b in silences][-10:]}
