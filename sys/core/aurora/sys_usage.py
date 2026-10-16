# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📊 How Aurora is used, per user and per day (owner, 2026-10-17: «una statistica generale per tenere traccia di tutto
il tipo di utilizzo… niente dati personali… chiamate ai tools, ai modelli»): counts and durations only — questions,
agent runs and steps, model calls by provider/model (cloud, with tokens) and by role (local), fallbacks, tool calls by
plugin and tool with their failures, approvals. Never a question, an answer, an argument or a result.

The counts come from the trace events (sys_log.trace calls count() for the few that matter), added to
<AURORA_STATUS_DIR>/usage/<YYYYMMDD>.json under a lock, shared by every process. Work without a user (routines,
autonomy, the services' own checks) is counted under "" — Aurora on her own. rebuild() makes the days missing from
the trace files still on disk (the history before this module, and after a loss)."""
from __future__ import annotations

import fcntl
import gzip
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import sys_config

# (component, event) -> what it adds to a user's day; anything else is never read
EVENTS = {("api", "run.start"), ("api", "run.end"), ("agent", "agent.start"), ("agent", "agent.finish"),
          ("llm_client", "cloud.call"), ("llm_client", "local.call"), ("llm_client", "cloud.fallback"),
          ("plugins", "plugin.call"), ("plugins", "plugin.refused"), ("approvals", "approval.request")}
MAX_DAYS = 366


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "usage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _num(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def add(day: dict, user: str, component: str, event: str, p: dict) -> None:
    """One event into a day's counts (names and numbers only)."""
    from .mdl_budget import tokens_of
    u = day.setdefault(user, {})

    def bump(group: str, key: str, **fields) -> None:
        row = u.setdefault(group, {}).setdefault(str(key)[:80] or "?", {})
        for k, v in fields.items():
            row[k] = round(row.get(k, 0) + v, 2)

    if event == "run.start":
        u["questions"] = u.get("questions", 0) + 1
    elif event == "run.end":
        u["question_s"] = round(u.get("question_s", 0) + _num(p.get("seconds")), 1)
    elif event == "agent.start":
        u["agent_runs"] = u.get("agent_runs", 0) + 1
    elif event == "agent.finish":
        u["agent_steps"] = u.get("agent_steps", 0) + int(_num(p.get("steps")))
        u["agent_s"] = round(u.get("agent_s", 0) + _num(p.get("seconds")), 1)
    elif event == "cloud.call":
        bump("cloud", f"{p.get('provider', '?')}/{p.get('model', '?')}", calls=1, tokens=tokens_of(p.get("usage") or {}))
    elif event == "local.call":
        bump("local", p.get("role") or "?", calls=1, tokens=int(_num(p.get("tokens_out"))), s=_num(p.get("seconds")))
    elif event == "cloud.fallback":
        bump("fallback", p.get("provider") or "?", calls=1)
    elif event == "plugin.call":
        bump("tools", f"{p.get('plugin', '?')}.{p.get('tool', '?')}", calls=1, failed=0 if p.get("ok") else 1,
             s=_num(p.get("seconds")))
    elif event == "plugin.refused":
        bump("tools", f"{p.get('plugin', '?')}.{p.get('tool', '?')}", calls=1, failed=1)
    elif event == "approval.request":
        u["approvals"] = u.get("approvals", 0) + 1


def _edit(f: Path, change) -> dict:
    """A day file changed by one process at a time (the live counts of every process, a purge)."""
    with open(f, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            data = json.loads(fh.read() or "{}")
        except ValueError:
            data = {}
        change(data)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(data))
    return data


def count(cfg: sys_config.Config, component: str, event: str, payload: dict, user: str | None) -> None:
    """The live count of a trace event (sys_log.trace): quick, and never raises into the traced work."""
    if (component, event) not in EVENTS:
        return
    try:
        _edit(_dir(cfg) / f"{time.strftime('%Y%m%d')}.json", lambda day: add(day, user or "", component, event, payload or {}))
    except Exception:  # noqa: BLE001 — a count lost, never a call broken
        pass


def _lines(f: Path):
    try:
        with (gzip.open(f, "rt", encoding="utf-8", errors="replace") if f.suffix == ".gz"
              else open(f, encoding="utf-8", errors="replace")) as fh:
            yield from fh
    except (OSError, EOFError):
        return


def rebuild(cfg: sys_config.Config, force: bool = False) -> dict[str, int]:
    """The days from the trace files (current and rotated) of the components counted: only the days without a file,
    or every day with force (a day whose oldest trace was already deleted comes out short). {day: events}."""
    trace = cfg.path("AURORA_LOG_DIR") / "trace"
    days: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for comp in sorted({c for c, _ in EVENTS}):
        for f in sorted(set(trace.glob(f"{comp}.*jsonl*")) | set(trace.glob(f"{comp}.jsonl"))):
            for line in _lines(f):
                if '"event"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (r.get("component"), r.get("event")) not in EVENTS:
                    continue
                d = str(r.get("ts", ""))[:10].replace("-", "")
                if len(d) != 8:
                    continue
                add(days.setdefault(d, {}), r.get("user") or "", r["component"], r["event"], r.get("payload") or {})
                seen[d] = seen.get(d, 0) + 1
    out = _dir(cfg)
    written = {}
    for d, day in days.items():
        f = out / f"{d}.json"
        if f.exists() and not force:
            continue
        f.write_text(json.dumps(day), encoding="utf-8")
        written[d] = seen[d]
    return written


def days_of(cfg: sys_config.Config, name: str) -> list[Path]:
    """The day files holding a user's counts (the purge of a user removes them)."""
    out = []
    for f in sorted(_dir(cfg).glob("*.json")):
        try:
            if name in json.loads(f.read_text(encoding="utf-8")):
                out.append(f)
        except (OSError, ValueError):
            continue
    return out


def forget(f: Path, name: str) -> None:
    """A user's counts out of one day file, under the lock the live counts take."""
    _edit(f, lambda day: day.pop(name, None))


def _merge(into: dict, u: dict) -> None:
    for k, v in u.items():
        if isinstance(v, dict):
            g = into.setdefault(k, {})
            for key, row in v.items():
                r = g.setdefault(key, {})
                for f, n in row.items():
                    r[f] = round(r.get(f, 0) + n, 2)
        else:
            into[k] = round(into.get(k, 0) + v, 2)


def totals(u: dict) -> dict:
    """The headline numbers of one user's (or everyone's) counts."""
    s = lambda g, f: sum(r.get(f, 0) for r in (u.get(g) or {}).values())  # noqa: E731
    return {"questions": u.get("questions", 0), "question_s": u.get("question_s", 0),
            "agent_runs": u.get("agent_runs", 0), "agent_steps": u.get("agent_steps", 0),
            "cloud_calls": s("cloud", "calls"), "cloud_tokens": s("cloud", "tokens"),
            "local_calls": s("local", "calls"), "local_tokens": s("local", "tokens"), "local_s": round(s("local", "s"), 1),
            "fallbacks": s("fallback", "calls"), "tool_calls": s("tools", "calls"), "tool_failed": s("tools", "failed"),
            "approvals": u.get("approvals", 0)}


def report(cfg: sys_config.Config, days: int = 7, users: set[str] | None = None) -> dict:
    """The last `days` days: per day and per user the headline numbers, and over the period the models and tools
    in detail. `users` limits it (a user sees only their own: {"<name>"}); None = everyone."""
    days = max(1, min(int(days), MAX_DAYS))
    d0 = datetime.now()
    out_days, per_user, overall = [], {}, {}
    for i in range(days - 1, -1, -1):
        day = (d0 - timedelta(days=i)).strftime("%Y%m%d")
        try:
            data = json.loads((_dir(cfg) / f"{day}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        merged: dict = {}
        for who, u in data.items():
            if users is not None and who not in users:
                continue
            _merge(merged, u)
            _merge(per_user.setdefault(who, {}), u)
            _merge(overall, u)
        out_days.append({"day": day, **totals(merged)})
    rows = lambda g: sorted(({"name": k, **v} for k, v in (overall.get(g) or {}).items()),  # noqa: E731
                            key=lambda r: -r.get("calls", 0))
    return {"days": out_days, "totals": totals(overall),
            "users": [{"user": w, **totals(u)} for w, u in sorted(per_user.items(), key=lambda x: -totals(x[1])["questions"])],
            "cloud": rows("cloud"), "local": rows("local"), "tools": rows("tools"), "fallback": rows("fallback")}


def names(cfg: sys_config.Config, days: int = 7) -> set[str]:
    """Who has counts in the last `days` days ("" = Aurora on her own)."""
    out: set[str] = set()
    for i in range(max(1, min(int(days), MAX_DAYS))):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            out |= set(json.loads((_dir(cfg) / f"{day}.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out
