# SPDX-License-Identifier: Apache-2.0
"""Plugin "email_diag": reads the email plugin's manifest, traces and logs to explain why reading mail fails."""
from __future__ import annotations

import gzip
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("email_diag", version="1.0")

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ROT_RE = re.compile(r"\.(\d{8}-\d{6})\.[a-z]+\.gz$")


def _log_dir() -> Path:
    return Path(cfg.path("AURORA_LOG_DIR"))


def _plugins_dir() -> Path:
    try:
        p = Path(cfg.path("AURORA_PLUGINS_DIR"))
        if p.is_dir():
            return p
    except Exception:
        pass
    return _log_dir().parent / "plugins"


def _files(folder: Path, stem: str, ext: str, since: datetime) -> list[Path]:
    """Live file plus rotated copies whose rotation time falls inside the window."""
    out = []
    if not folder.is_dir():
        return out
    for f in folder.iterdir():
        if f.name == f"{stem}.{ext}":
            out.append(f)
        elif f.name.startswith(stem + ".") and f.name.endswith(f".{ext}.gz"):
            m = ROT_RE.search(f.name)
            try:
                t = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").astimezone() if m else None
            except Exception:
                t = None
            if t is None or t >= since:
                out.append(f)
    return sorted(out, key=lambda p: p.stat().st_mtime)


def _lines(f: Path):
    op = gzip.open if f.name.endswith(".gz") else open
    with op(f, "rt", encoding="utf-8", errors="replace") as h:
        yield from h


def _ts(v) -> datetime | None:
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.astimezone()
    except Exception:
        return None


def _is_email(o: dict) -> bool:
    p = o.get("payload") or {}
    vals = [str(o.get("component", ""))]
    if isinstance(p, dict):
        for k in ("plugin", "server", "tool", "name"):
            vals.append(str(p.get(k, "")))
    return any(v.lower().startswith("email") or v.lower().startswith("mcp__email") for v in vals)


def _err(o: dict) -> str | None:
    ev = str(o.get("event", "")).lower()
    lv = str(o.get("level", "")).lower()
    p = o.get("payload") or {}
    e = p.get("error") if isinstance(p, dict) else None
    if e or lv in ("warn", "warning", "error", "critical") or any(w in ev for w in ("error", "fail", "timeout", "denied")):
        return str(e or ev)[:200]
    return None


@server.tool()
def email_diag_stato() -> str:
    """Dice se il plugin email è installato, quali variabili richiede e se risultano impostate (mai i valori)."""
    try:
        d = _plugins_dir() / "email"
        man = d / "plugin.json"
        if not man.is_file():
            return f"Il plugin email non risulta installato (manca {man})."
        m = json.loads(man.read_text(encoding="utf-8"))
        righe = [f"Plugin email: versione {m.get('version', '?')}, rete nella gabbia: "
                 f"{'sì' if (m.get('sandbox') or {}).get('network') else 'no'}."]
        env = m.get("env") or []
        if env:
            righe.append("Variabili richieste:")
            for e in env:
                nome = e.get("name") if isinstance(e, dict) else str(e)
                stato = "impostata" if os.environ.get(nome) else "non visibile qui"
                righe.append(f"- {nome}: {stato}")
        else:
            righe.append("Nessuna variabile dichiarata.")
        req = m.get("requires") or []
        if req:
            righe.append("Richiede: " + ", ".join(map(str, req)))
        righe.append("Strumenti nel codice: " + (", ".join(sorted(set(
            re.findall(r"def (\w+)\(", (d / "server.py").read_text(encoding="utf-8", errors="replace")))))
            if (d / "server.py").is_file() else "server.py assente"))
        return "\n".join(righe)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def email_diag_chiamate(hours: float = 24) -> str:
    """Riassume le chiamate al plugin email nelle tracce e nei log delle ultime ore, con gli ultimi errori."""
    try:
        since = datetime.now().astimezone() - timedelta(hours=hours)
        trace = _log_dir() / "trace"
        tot, eventi, errori = 0, {}, []
        for stem in ("plugins", "agent", "approvals"):
            for f in _files(trace, stem, "jsonl", since):
                for ln in _lines(f):
                    if "email" not in ln.lower():
                        continue
                    try:
                        o = json.loads(ln)
                    except Exception:
                        continue
                    t = _ts(o.get("ts"))
                    if not t or t < since or not _is_email(o):
                        continue
                    tot += 1
                    ev = str(o.get("event", "?"))
                    eventi[ev] = eventi.get(ev, 0) + 1
                    e = _err(o)
                    if e:
                        errori.append(f"{t.isoformat(timespec='seconds')} {ev}: {e}")
        righe = [f"Tracce del plugin email nelle ultime {hours:g} ore: {tot} eventi."]
        for ev, n in sorted(eventi.items(), key=lambda x: -x[1])[:10]:
            righe.append(f"- {ev}: {n}")

        cont, ultimi = {}, []
        logd = _log_dir() / "email"
        for f in _files(logd, "email", "log", since):
            for ln in _lines(f):
                parti = ln.split(None, 2)
                if len(parti) < 2 or parti[1] not in LEVELS:
                    continue
                t = _ts(parti[0])
                if not t or t < since:
                    continue
                cont[parti[1]] = cont.get(parti[1], 0) + 1
                if parti[1] in ("WARNING", "ERROR", "CRITICAL"):
                    ultimi.append(ln.strip()[:250])
        if cont:
            righe.append("Log email: " + ", ".join(f"{k} {v}" for k, v in cont.items()))
        else:
            righe.append("Log email: nessuna riga nella finestra.")
        errori += ultimi
        if errori:
            righe.append("Ultimi errori/avvisi:")
            righe += ["- " + e for e in errori[-6:]]
        elif tot == 0:
            righe.append("Il plugin email non è mai stato chiamato: forse non è attivo o l'agente non l'ha scelto.")
        else:
            righe.append("Nessun errore registrato.")
        return "\n".join(righe)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
