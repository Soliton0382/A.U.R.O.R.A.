# SPDX-License-Identifier: Apache-2.0
"""Plugin "routine_status": reads routines.json of each user and counts active and suspended routines."""
from __future__ import annotations

import json
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("routine_status", version="1.0")

_OFF_WORDS = {"off", "disabled", "disabilitata", "disabilitato", "paused", "pausa",
              "suspended", "sospesa", "sospeso", "inactive", "inattiva", "stopped", "false", "no", "0"}


def _users_dir() -> Path:
    cfg = sys_config.get()
    return Path(cfg.path("AURORA_STATUS_DIR")) / "users"


def _current_user() -> str:
    try:
        return str(getattr(sys_config.get(), "user", "") or "")
    except Exception:
        return ""


def _items(data) -> list[dict]:
    """Accepts a list, {"routines": [...]}, or a dict keyed by name."""
    if isinstance(data, dict):
        for k in ("routines", "items", "list", "routine"):
            if isinstance(data.get(k), (list, dict)):
                return _items(data[k])
        out = []
        for name, val in data.items():
            if isinstance(val, dict):
                d = dict(val)
                d.setdefault("name", name)
                out.append(d)
        return out
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _active(r: dict) -> bool:
    for k in ("suspended", "paused", "disabled"):
        if k in r and isinstance(r[k], bool):
            return not r[k]
    for k in ("enabled", "active", "on"):
        if k in r:
            v = r[k]
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() not in _OFF_WORDS
    for k in ("status", "state"):
        if k in r:
            return str(r[k]).strip().lower() not in _OFF_WORDS
    return True


def _first(r: dict, keys) -> str:
    for k in keys:
        v = r.get(k)
        if v not in (None, "", [], {}):
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False)[:60]
            return str(v)[:60]
    return "—"


def _load(user_filter: str) -> tuple[list[tuple[str, list[dict]]], list[str]]:
    base = _users_dir()
    found, problems = [], []
    if not base.is_dir():
        return found, problems
    for udir in sorted(p for p in base.iterdir() if p.is_dir()):
        if user_filter and udir.name != user_filter:
            continue
        f = udir / "routines.json"
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8") or "[]")
        except Exception as e:
            problems.append(f"{udir.name}: routines.json illeggibile ({type(e).__name__})")
            continue
        found.append((udir.name, _items(data)))
    return found, problems


@server.tool()
def routine_status_summary(user: str = "") -> str:
    """How many routines there are in all, how many active and how many suspended, per user (empty user = everyone)."""
    try:
        found, problems = _load(user.strip())
        if not found:
            msg = "Nessuna routine configurata" + (f" per l'utente {user}." if user else ".")
            return msg + ("\n" + "\n".join(problems) if problems else "")
        lines, tot, act = [], 0, 0
        for uname, items in found:
            a = sum(1 for r in items if _active(r))
            tot += len(items)
            act += a
            lines.append(f"- {uname}: {len(items)} in tutto, {a} attive, {len(items) - a} sospese")
        me = _current_user()
        head = f"Routine: {tot} in tutto, {act} attive, {tot - act} sospese."
        if me and not user:
            for uname, items in found:
                if uname == me:
                    a = sum(1 for r in items if _active(r))
                    head += f"\nTue ({me}): {len(items)} in tutto, {a} attive."
        out = head + "\n" + "\n".join(lines)
        if problems:
            out += "\n" + "\n".join(problems)
        return out
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def routine_status_list(user: str = "", only_active: bool = False) -> str:
    """The list of routines (name, state, schedule, last run); empty user = everyone, only_active for the active ones only."""
    try:
        found, problems = _load(user.strip())
        if not found:
            return "Nessuna routine configurata." + ("\n" + "\n".join(problems) if problems else "")
        rows = []
        for uname, items in found:
            for r in items:
                on = _active(r)
                if only_active and not on:
                    continue
                name = _first(r, ("name", "title", "id", "topic"))
                sched = _first(r, ("schedule", "cron", "when", "at", "time", "every", "interval"))
                last = _first(r, ("last_run", "last_run_at", "last", "lastRun", "ran_at"))
                rows.append(f"- [{uname}] {name} — {'attiva' if on else 'sospesa'}; "
                            f"quando: {sched}; ultima: {last}")
        if not rows:
            return "Nessuna routine attiva." if only_active else "Nessuna routine configurata."
        out = f"{len(rows)} routine:\n" + "\n".join(rows[:80])
        if len(rows) > 80:
            out += f"\n… e altre {len(rows) - 80}."
        if problems:
            out += "\n" + "\n".join(problems)
        return out
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
