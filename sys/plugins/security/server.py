# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "security": what the firewall saw, read only, for the owner's questions and routines.

The incidents raised by aurora-sentinel (status/incidents.json) and the firewall's own lines kept by the sentinel
(logs/firewall/, key=value syslog, Sophos and most firewalls), summarised over a window: allowed and denied
traffic, components, intrusion-prevention events, the busiest sources and destination ports. Defensive only: no
lookup about persons, nothing done on the firewall (ethics code, level A).
"""
from __future__ import annotations

import gzip
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from aurora import sys_config
from aurora.sec_sentinel import is_ips, is_private, parse, src_of
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("security", version="1.0")
SEV = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def tool(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return server.tool()(wrapped)


def _ts(text: str) -> float | None:
    try:
        return datetime.fromisoformat(text.replace("+0200", "+02:00").replace("+0100", "+01:00")).timestamp()
    except ValueError:
        return None


def incidents_since(hours: float) -> list[dict]:
    f = cfg.path("AURORA_STATUS_DIR") / "incidents.json"
    try:
        items = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    since = time.time() - hours * 3600
    return [i for i in (items if isinstance(items, list) else []) if (_ts(str(i.get("received", ""))) or 0) >= since]


def lines_since(hours: float):
    """The firewall lines of the window, oldest file first; each line starts with the time the sentinel got it."""
    since = time.time() - hours * 3600
    files = sorted(Path(cfg.path("AURORA_LOG_DIR") / "firewall").glob("firewall*"), key=lambda p: p.stat().st_mtime)
    for f in files:
        if f.stat().st_mtime < since:
            continue
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", errors="replace") as h:
            for line in h:
                t = _ts(line[:29])
                if t is not None and t >= since:
                    yield line


def summary(lines) -> dict:
    """Counts over firewall lines (pure: tested offline)."""
    kinds, comps, denied_src, ports, ips = Counter(), Counter(), Counter(), Counter(), Counter()
    n = 0
    for line in lines:
        f = parse(line[line.find("<"):] if "<" in line else line)
        n += 1
        status = f.get("status") or f.get("log_subtype") or "?"
        kinds[(f.get("log_type", "?"), status)] += 1
        comps[f.get("log_component", "?")] += 1
        if str(status).lower().startswith("den") or str(status).lower() == "drop":
            denied_src[src_of(f) or "?"] += 1
            if f.get("dst_port"):
                ports[f["dst_port"]] += 1
        if is_ips(f):                                     # the sentinel's own rule (IDP, IPS, ATP)
            what = f.get("signature_msg") or f.get("message") or f.get("threatname") or f.get("log_subtype") or "?"
            dest = f.get("url") or f.get("domain") or f.get("dst_domain") or f.get("dst_ip") or ""
            ips[f"{f.get('log_type', '?')} {what}{' → ' + dest if dest else ''} da {src_of(f) or '?'}"] += 1
    return {"lines": n, "kinds": kinds.most_common(8), "components": comps.most_common(6),
            "denied_sources": denied_src.most_common(5), "denied_ports": ports.most_common(5), "ips": ips.most_common(5)}


def _format_incidents(items: list[dict]) -> str:
    if not items:
        return "Nessun incidente."
    rows = []
    for i in sorted(items, key=lambda x: str(x.get("received", ""))):
        where = "interna" if str(i.get("internal")) == "True" else "esterna"
        rows.append(f"{SEV.get(i.get('severity'), '⚪')} {str(i.get('received', ''))[11:16]} {i.get('kind')} da {i.get('source')} "
                    f"({where}, {i.get('count')} eventi) — {i.get('status')}")
    return "\n".join(rows)


def _format_summary(s: dict, hours: float) -> str:
    if not s["lines"]:
        return f"Nessuna riga del firewall nelle ultime {hours:g} ore (la sentinella riceve il syslog?)."
    out = [f"{s['lines']} righe in {hours:g} ore."]
    out.append("Traffico: " + ", ".join(f"{t} {st} {n}" for (t, st), n in s["kinds"]))
    if s["denied_sources"]:
        out.append("Più negati, per sorgente: " + ", ".join(
            f"{ip}{' (interna)' if is_private(ip) else ''} {n}" for ip, n in s["denied_sources"]))
    if s["denied_ports"]:
        out.append("Porte di destinazione negate: " + ", ".join(f"{p} ({n})" for p, n in s["denied_ports"]))
    out.append("IPS/ATP: " + ("; ".join(f"{m} ({n})" for m, n in s["ips"]) if s["ips"] else "nessun evento"))
    return "\n".join(out)


@tool
def security_incidents(hours: float = 12) -> str:
    """The security incidents the sentinel raised in the last hours: time, severity, kind, source, events, status."""
    return _format_incidents(incidents_since(max(1.0, min(hours, 24 * 30))))


@tool
def firewall_summary(hours: float = 12) -> str:
    """What the firewall logged in the last hours: allowed and denied traffic, IPS events, top denied sources and ports."""
    h = max(1.0, min(hours, 72))
    return _format_summary(summary(lines_since(h)), h)


@tool
def security_night_report(hours: float = 10) -> str:
    """The morning report: incidents and firewall traffic of the night (the last `hours`)."""
    h = max(1.0, min(hours, 24))
    inc = incidents_since(h)
    return (f"🛡️ Notte del firewall (ultime {h:g} ore)\nIncidenti: {len(inc)}\n{_format_incidents(inc)}\n\n"
            + _format_summary(summary(lines_since(h)), h))


if __name__ == "__main__":
    server.run("stdio")
