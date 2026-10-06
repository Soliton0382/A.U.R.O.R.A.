# SPDX-License-Identifier: Apache-2.0
"""Plugin "logs": reads Aurora's component logs (live and rotated .gz) and counts lines per level."""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("logs", version="1.0")

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
RANK = {name: i for i, name in enumerate(LEVELS)}
JSON_LEVELS = {"debug": "DEBUG", "info": "INFO", "warn": "WARNING", "warning": "WARNING",
               "error": "ERROR", "err": "ERROR", "critical": "CRITICAL", "fatal": "CRITICAL",
               "panic": "CRITICAL", "dpanic": "CRITICAL"}
SUFFIXES = (".log", ".log.gz", ".jsonl", ".jsonl.gz", ".out")


def _log_dir() -> Path:
    try:
        return Path(cfg.path("AURORA_LOG_DIR"))
    except Exception:
        return Path("sys/logs")


def _local(dt: datetime) -> datetime:
    return dt.astimezone() if dt.tzinfo else dt.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _parse(line: str):
    """Return (timestamp, level) or (None, None) for lines with no recognisable header."""
    s = line.strip()
    if not s:
        return None, None
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except Exception:
            return None, None
        if not isinstance(obj, dict):
            return None, None
        lvl = JSON_LEVELS.get(str(obj.get("level", "")).lower())
        ts = obj.get("ts", obj.get("time"))
        when = None
        try:
            if isinstance(ts, (int, float)):
                when = datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone()
            elif isinstance(ts, str):
                when = _local(datetime.fromisoformat(ts))
        except Exception:
            when = None
        return when, lvl
    parts = s.split(None, 2)
    if len(parts) < 2:
        return None, None
    try:
        when = _local(datetime.fromisoformat(parts[0]))
    except Exception:
        return None, None
    lvl = parts[1] if parts[1] in RANK else None
    return when, lvl


def _files(folder: Path, since: datetime | None):
    out = []
    for f in folder.iterdir():
        if not f.is_file() or not f.name.endswith(SUFFIXES):
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).astimezone()
        except OSError:
            continue
        if since is not None and mtime < since:
            continue                      # every line of this file is older than the window
        out.append((mtime, f))
    return [f for _, f in sorted(out)]


def _lines(path: Path):
    opener = gzip.open if path.name.endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line.rstrip("\n")
    except (OSError, EOFError):
        return


def _components(component: str = ""):
    base = _log_dir()
    if not base.is_dir():
        return base, []
    dirs = sorted(d for d in base.iterdir() if d.is_dir())
    if component:
        dirs = [d for d in dirs if d.name.lower() == component.strip().lower()]
    return base, dirs


@server.tool()
def logs_summary(hours: float = 24) -> str:
    """Per ogni componente di Aurora, quante righe di log per livello nelle ultime N ore (copie ruotate incluse)."""
    try:
        since = datetime.now().astimezone() - timedelta(hours=float(hours))
        base, dirs = _components()
        if not dirs:
            return f"Nessuna cartella di log trovata in {base}."
        rows, total_bad = [], 0
        for d in dirs:
            counts = {k: 0 for k in LEVELS}
            for f in _files(d, since):
                for line in _lines(f):
                    when, lvl = _parse(line)
                    if lvl and when and when >= since:
                        counts[lvl] += 1
            bad = counts["WARNING"] + counts["ERROR"] + counts["CRITICAL"]
            if sum(counts.values()) == 0:
                continue
            total_bad += bad
            detail = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
            rows.append((counts["CRITICAL"], counts["ERROR"], bad, f"- {d.name}: {detail}"))
        if not rows:
            return f"Nessuna riga di log nelle ultime {hours:g} ore."
        rows.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
        head = f"Log delle ultime {hours:g} ore ({len(rows)} componenti attivi, WARNING+ERROR+CRITICAL = {total_bad}):"
        return head + "\n" + "\n".join(r[3] for r in rows)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def logs_errors(component: str = "", hours: float = 24, min_level: str = "ERROR", limit: int = 20) -> str:
    """Le ultime righe di log con livello almeno min_level (WARNING, ERROR, CRITICAL) nelle ultime N ore, di un componente o di tutti."""
    try:
        floor = RANK.get(str(min_level).strip().upper(), RANK["ERROR"])
        limit = max(1, min(int(limit), 200))
        since = datetime.now().astimezone() - timedelta(hours=float(hours))
        base, dirs = _components(component)
        if not dirs:
            what = f"il componente «{component}»" if component else "alcun componente"
            return f"Non trovo {what} in {base}."
        found = []
        for d in dirs:
            for f in _files(d, since):
                for line in _lines(f):
                    when, lvl = _parse(line)
                    if lvl and when and when >= since and RANK[lvl] >= floor:
                        found.append((when, d.name, lvl, line.strip()))
        if not found:
            dove = f" in {component}" if component else ""
            return f"Nessuna riga {LEVELS[floor]} o superiore{dove} nelle ultime {hours:g} ore."
        found.sort(key=lambda r: r[0])
        shown = found[-limit:]
        out = [f"{len(found)} righe {LEVELS[floor]}+ nelle ultime {hours:g} ore; le ultime {len(shown)}:"]
        for when, comp, lvl, text in reversed(shown):
            if len(text) > 300:
                text = text[:300] + "…"
            out.append(f"- {when.strftime('%Y-%m-%d %H:%M:%S')} [{comp}] {lvl}: {text}")
        return "\n".join(out)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
