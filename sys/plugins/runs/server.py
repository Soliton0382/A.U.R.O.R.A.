# SPDX-License-Identifier: Apache-2.0
"""Plugin "runs": reads the previous routine reports (push/history.jsonl) to compare with new data."""
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import datetime
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("runs", version="1.0")

URL_RE = re.compile(r"https?://[^\s<>\")\]]+")


def _history_files() -> list[Path]:
    # the notifications of the user this plugin works for (sys_push keeps them there; the sandbox hides the others')
    from aurora import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "push"
    if not d.is_dir():
        return []
    files = sorted(d.glob("history*.jsonl.gz")) + sorted(d.glob("history*.jsonl"))
    return [f for f in files if f.is_file()]


def _events() -> list[dict]:
    out = []
    for f in _history_files():
        opener = gzip.open if f.suffix == ".gz" else open
        try:
            with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(ev, dict):
                        out.append(ev)
        except Exception:
            continue
    out.sort(key=lambda e: _ts(e))
    return out


def _ts(ev: dict) -> float:
    v = ev.get("at", 0)
    try:
        return float(v)
    except Exception:
        try:
            return datetime.fromisoformat(str(v)).timestamp()
        except Exception:
            return 0.0


def _when(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def _match(ev: dict, query: str, event: str) -> bool:
    if event and not str(ev.get("event", "")).startswith(event):
        return False
    if not query.strip():
        return True
    text = (str(ev.get("title", "")) + " " + str(ev.get("body", ""))).lower()
    return all(w in text for w in query.lower().split())


@server.tool()
def runs_previous(query: str = "", n: int = 1, skip: int = 0, event: str = "routine",
                  max_chars: int = 4000) -> str:
    """Il testo completo degli ultimi n resoconti di routine (i più recenti prima) che contengono tutte le parole di query (es. 'ricerca', 'scienza'); skip salta i più recenti."""
    try:
        evs = [e for e in _events() if _match(e, query, event)]
        if not evs:
            return f"Nessun resoconto precedente trovato (query: '{query}')."
        evs = list(reversed(evs))[max(0, int(skip)):max(0, int(skip)) + max(1, int(n))]
        if not evs:
            return "Nessun resoconto oltre quelli saltati."
        parts = []
        budget = max(500, int(max_chars))
        for e in evs:
            body = str(e.get("body", ""))
            per = budget // len(evs)
            if len(body) > per:
                body = body[:per] + " …[troncato]"
            parts.append(f"== {_when(_ts(e))} · {e.get('event', '')} · {e.get('title', '')}\n{body}")
        return "\n\n".join(parts)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def runs_list(hours: float = 168, query: str = "", event: str = "routine") -> str:
    """Elenco delle esecuzioni di routine nelle ultime ore: data, titolo e prima riga del resoconto."""
    try:
        since = time.time() - float(hours) * 3600
        evs = [e for e in _events() if _ts(e) >= since and _match(e, query, event)]
        if not evs:
            return f"Nessuna esecuzione nelle ultime {hours:g} ore."
        lines = [f"{len(evs)} esecuzioni nelle ultime {hours:g} ore (più recenti prima):"]
        for e in reversed(evs[-50:]):
            first = str(e.get("body", "")).strip().splitlines()
            first = first[0][:140] if first else ""
            lines.append(f"- {_when(_ts(e))} [{e.get('event', '')}] {e.get('title', '')}: {first}")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def runs_links(query: str = "", hours: float = 72, event: str = "routine") -> str:
    """I link (URL) già citati nei resoconti precedenti delle ultime ore, per riportare solo notizie nuove."""
    try:
        since = time.time() - float(hours) * 3600
        evs = [e for e in _events() if _ts(e) >= since and _match(e, query, event)]
        if not evs:
            return f"Nessun resoconto nelle ultime {hours:g} ore: nessun link già dato."
        seen: dict[str, str] = {}
        for e in evs:
            for u in URL_RE.findall(str(e.get("body", ""))):
                u = u.rstrip(".,;:")
                seen.setdefault(u, _when(_ts(e)))
        if not seen:
            return f"{len(evs)} resoconti nelle ultime {hours:g} ore, ma senza link."
        lines = [f"{len(seen)} link già citati in {len(evs)} resoconti (ultime {hours:g} ore):"]
        for u, w in list(seen.items())[-150:]:
            lines.append(f"- {w} {u}")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
