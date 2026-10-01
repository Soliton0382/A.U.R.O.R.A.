# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora reads her own logs: where they are, what went wrong lately, what a run did.

Layout (sys_log): <AURORA_LOG_DIR>/<component>/<component>.log (text, one line per record:
"<iso time> <LEVEL> aurora.<component> <message>"), rotated copies <component>.<time>.log.gz,
and <AURORA_LOG_DIR>/trace/<component>.jsonl (one JSON event per line: ts, seq, pid, component,
event, run_id, payload). Only the live files are read here: enough for the last hours or days.
"""
from __future__ import annotations

import json
import re
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path

from . import sys_config

LINE = re.compile(r"^(\S+) (DEBUG|INFO|WARNING|ERROR|CRITICAL) (\S+) (.*)$")
VARIABLE = re.compile(r"\b[0-9a-f]{12,}\b|\d+(\.\d+)?")


def kind_of(message: str) -> str:
    """A message without its numbers and ids: messages of the same kind share it."""
    return VARIABLE.sub("#", message)[:160]
DESCRIPTION = {
    "api": "answers, runs, settings, imports (aurora-api)", "models": "encoder and re-ranker service",
    "llm": "llama-server output", "llm_client": "calls to the reasoner", "search": "retrieval", "index": "vector index",
    "vault": "vault writes", "ingest": "document import", "attach": "chat attachments", "acquire": "arXiv acquisition",
    "rem": "autonomic cycle", "harvester": "new papers", "migrate": "migration", "https": "Caddy (HTTPS)",
    "senses": "time and weather", "trace": "structured events of every component (JSON lines)",
}


def _dir(cfg) -> Path:
    return cfg.path("AURORA_LOG_DIR")


def _since(hours: float) -> datetime:
    return datetime.now().astimezone() - timedelta(hours=hours)


def inventory(cfg: sys_config.Config | None = None, hours: float = 24) -> dict:
    """Every component: its live file, size, last write, warnings/errors in the last `hours`."""
    cfg = cfg or sys_config.get()
    base, since, out = _dir(cfg), _since(hours), {}
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        files = sorted(folder.glob("*.log")) + sorted(folder.glob("*.jsonl"))
        entry = {"folder": str(folder), "about": DESCRIPTION.get(folder.name, ""), "files": [], "warnings": 0,
                 "errors": 0, "last_problems": [], "kinds": {}, "lifecycle": []}
        for f in files:
            st = f.stat()
            entry["files"].append({"file": f.name, "kb": round(st.st_size / 1024),
                                   "modified": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")})
            if f.suffix != ".log":
                continue
            recent: deque = deque(maxlen=5)
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = LINE.match(line)
                    if m and m.group(2) == "INFO" and re.match(r"(started|stopped cleanly)\b", m.group(4)):
                        entry["lifecycle"].append(f"{m.group(1)[:19]} {m.group(4)[:60]}")
                        del entry["lifecycle"][:-12]
                    if not m or m.group(2) not in ("WARNING", "ERROR", "CRITICAL"):
                        continue
                    try:
                        when = datetime.fromisoformat(m.group(1))
                    except ValueError:
                        continue
                    if when < since:
                        continue
                    entry["errors" if m.group(2) != "WARNING" else "warnings"] += 1
                    recent.append(f"{m.group(1)[11:19]} {m.group(2)} {m.group(4)[:240]}")
                    k = entry["kinds"].setdefault(f"{m.group(2)} {kind_of(m.group(4))}",
                                                  {"count": 0, "first": m.group(1)[:19], "last": ""})
                    k["count"] += 1
                    k["last"] = m.group(1)[:19]
            entry["last_problems"] += list(recent)
        entry["rotated"] = len(list(folder.glob("*.gz")))
        if entry["files"] or entry["rotated"]:
            out[folder.name] = entry
    return {"log_dir": str(base), "hours": hours, "components": out,
            "format": "text: '<iso time> <LEVEL> aurora.<component> <message>'; trace: JSON lines with run_id"}


def tail(component: str, lines: int = 100, level: str | None = None, cfg: sys_config.Config | None = None) -> list[str]:
    """The last lines of a component's live log (optionally only WARNING and above)."""
    cfg = cfg or sys_config.get()
    if not re.fullmatch(r"[a-z_]+", component):
        raise ValueError("bad component name")
    f = _dir(cfg) / component / f"{component}.log"
    if not f.exists():
        return []
    keep: deque = deque(maxlen=max(1, min(lines, 2000)))
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if level:
                m = LINE.match(line)
                if not m or m.group(2) in ("DEBUG", "INFO"):
                    continue
            keep.append(line.rstrip("\n"))
    return list(keep)


def run_events(run_id: str, cfg: sys_config.Config | None = None) -> list[dict]:
    """Every traced event of a run, from the live trace files."""
    cfg = cfg or sys_config.get()
    out = []
    for f in sorted((_dir(cfg) / "trace").glob("*.jsonl")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if run_id in line:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("run_id") == run_id:
                        out.append(e)
    return sorted(out, key=lambda e: e["ts"])


def answer_stats(hours: float = 24, cfg: sys_config.Config | None = None) -> dict:
    """Answers of the last `hours` from the api trace: how many, how long, how many abstained, errors."""
    cfg = cfg or sys_config.get()
    f, since = _dir(cfg) / "trace" / "api.jsonl", _since(hours)
    secs, modes, errors = [], Counter(), 0
    if f.exists():
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"answer.final"' not in line and '"error"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if datetime.fromisoformat(e["ts"]) < since:
                    continue
                if e["event"] == "error":
                    errors += 1
                elif e["event"] == "answer.final":
                    p = e["payload"]
                    secs.append(p.get("seconds", 0))
                    modes["abstained" if p.get("abstained") else p.get("mode") or "knowledge"] += 1
    secs.sort()
    return {"answers": len(secs), "by_outcome": dict(modes), "errors": errors,
            "median_s": secs[len(secs) // 2] if secs else None, "p90_s": secs[int(len(secs) * 0.9)] if secs else None}


# Components that run inside a service process: their problems stop when that service restarts with a fix.
HOST = {"models": "models", "llm": "llm", "rem": "rem", "harvester": "harvester", "https": "https"}


def problem_evidence(cfg: sys_config.Config | None = None, hours: float = 24) -> list[dict]:
    """Every kind of problem with measured facts: how many, first and last time, the last start of the
    service that hosts the component, and whether the problem was seen again after that start. A problem
    not seen since its service restarted is a candidate "resolved" (to be confirmed in the code)."""
    inv = inventory(cfg, hours)
    comps = inv["components"]
    starts = {name: [x[:19] for x in c["lifecycle"] if " started" in x or x[20:].startswith("started")]
              for name, c in comps.items()}
    out = []
    for name, c in comps.items():
        host = HOST.get(name, "api")                     # everything else runs inside aurora-api
        last_start = (starts.get(host) or [None])[-1]
        for kind, k in sorted(c["kinds"].items(), key=lambda kv: -kv[1]["count"]):
            out.append({"component": name, "kind": kind, "count": k["count"], "first": k["first"], "last": k["last"],
                        "host_service": f"aurora-{host}", "host_last_start": last_start,
                        "seen_after_last_start": bool(last_start and k["last"] > last_start)})
    return out
