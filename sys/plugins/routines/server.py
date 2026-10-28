# SPDX-License-Identifier: Apache-2.0
"""Plugin "routines": reads the configured routines (routines.json) and their active/disabled status."""
from __future__ import annotations

import json
from pathlib import Path

from aurora import sys_config, sys_seal
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("routines", version="1.0")

_NAME_KEYS = ("name", "title", "label", "id", "slug")
_SCHED_KEYS = ("schedule", "cron", "when", "every", "at", "time", "interval", "trigger")
_LAST_KEYS = ("last_run", "last_run_at", "lastRun", "last", "last_ok")


def _users_root() -> Path:
    return Path(cfg.path("AURORA_STATUS_DIR")) / "users"


def _user_files(user: str) -> list[tuple[str, Path]]:
    """(user, path of routines.json) for the requested user, the current one, or all."""
    root = _users_root()
    if user:
        return [(user, root / user / "routines.json")]
    current = getattr(cfg, "user", None) or ""
    if current and (root / current / "routines.json").is_file():
        return [(current, root / current / "routines.json")]
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            f = d / "routines.json"
            if d.is_dir() and f.is_file():
                out.append((d.name, f))
    return out


def _as_list(data) -> list[dict]:
    """Accepts a list, {"routines": [...]}, or {id: {...}}."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for k in ("routines", "items", "jobs", "tasks"):
            if isinstance(data.get(k), (list, dict)):
                return _as_list(data[k])
        out = []
        for k, v in data.items():
            if isinstance(v, dict):
                r = dict(v)
                r.setdefault("id", k)
                out.append(r)
        return out
    return []


def _is_active(r: dict) -> bool:
    for k in ("enabled", "active", "on"):
        if k in r:
            v = r[k]
            return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "si", "sì", "on")
    for k in ("disabled", "paused"):
        if k in r:
            v = r[k]
            return not (v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on"))
    st = str(r.get("status", "") or r.get("state", "")).strip().lower()
    if st:
        return st in ("active", "enabled", "on", "attiva", "attivo", "running", "scheduled")
    return True  # no flag: a configured routine is active by default


def _first(r: dict, keys) -> str:
    for k in keys:
        v = r.get(k)
        if v not in (None, "", [], {}):
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False)[:60]
            return str(v)[:60]
    return ""


def _load(user: str):
    """Returns (list of (user, routines)), notes."""
    files = _user_files(user)
    if not files:
        return [], ["Nessun file routines.json trovato in " + str(_users_root())]
    got, notes = [], []
    for u, f in files:
        if not f.is_file():
            notes.append(f"{u}: nessuna routine configurata (manca routines.json)")
            continue
        try:
            # sealed with its user's «routines» key (N64), which the host gives this cage: another user's file does
            # not open here and is said sealed, never guessed; a file of before is read as it is
            data = json.loads(sys_seal.read_any(cfg, f, u, "routines") or b"[]")
        except json.JSONDecodeError as e:
            notes.append(f"{u}: routines.json non leggibile ({e.msg}, riga {e.lineno})")
            continue
        except (ValueError, RuntimeError):                # does not open here (sys_keyring.Locked is a RuntimeError)
            notes.append(f"{u}: routines.json è sigillato con la chiave dell'utente: le routine sono nella pagina Routine")
            continue
        got.append((u, _as_list(data)))
    return got, notes


@server.tool()
def routines_summary(user: str = "") -> str:
    """How many routines are configured and how many are active or disabled (for the current user, or for each user if none is set)."""
    try:
        got, notes = _load(user)
        lines = []
        for u, rs in got:
            act = sum(1 for r in rs if _is_active(r))
            lines.append(f"{u}: {len(rs)} routine in tutto, {act} attive, {len(rs) - act} disattivate")
        lines += notes
        return "\n".join(lines) if lines else "Nessuna routine configurata."
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def routines_list(only_active: bool = False, user: str = "") -> str:
    """List of the configured routines with name, status (attiva/disattivata), schedule and last run."""
    try:
        got, notes = _load(user)
        lines = []
        for u, rs in got:
            sel = [r for r in rs if _is_active(r)] if only_active else rs
            act = sum(1 for r in rs if _is_active(r))
            lines.append(f"{u} — {len(rs)} routine, {act} attive:")
            if not sel:
                lines.append("  (nessuna)")
            for i, r in enumerate(sel[:60], 1):
                name = _first(r, _NAME_KEYS) or f"routine {i}"
                stato = "attiva" if _is_active(r) else "disattivata"
                row = f"  {i}. {name} [{stato}]"
                sched = _first(r, _SCHED_KEYS)
                if sched:
                    row += f" — quando: {sched}"
                last = _first(r, _LAST_KEYS)
                if last:
                    row += f" — ultima: {last}"
                lines.append(row)
            if len(sel) > 60:
                lines.append(f"  … e altre {len(sel) - 60}")
        lines += notes
        return "\n".join(lines) if lines else "Nessuna routine configurata."
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
