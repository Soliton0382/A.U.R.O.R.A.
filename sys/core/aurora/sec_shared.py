# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Traffic from a shared network that the firewall already refused: counted, not an incident (ROADMAP 103; owner,
2026-10-14: «gli scanning ip che provengono dalla rete cloudflare… arrivano da quei tentativi»).

Measured (M213): 56 incidents «scanning» from 46 Cloudflare addresses, 6–14 Oct, every line on port 80 and
already denied (Appliance Access) — Cloudflare reaching the origin over HTTP for whoever opens the domains with
http://. Blocking those addresses would change nothing (dropped already) and on a served port would shut out real
visitors behind the same node. So: an owner's check (rule:…) tripped by a source of a shared network (sec_intel.shared:
Cloudflare, Google…) whose lines were all refused becomes a count in <STATUS>/security/shared_denied.json, told at
most once a day per provider with what to change at the provider; anything from those networks that was NOT refused
stays an incident."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import sec_intel, sys_config

DENIED = re.compile(r'log_subtype="?Denied|action="?(?:Drop|Deny|Reject)', re.I)
PORT = re.compile(r'dst_port="?(\d+)')


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "security" / "shared_denied.json"


def classify(cfg: sys_config.Config, incident: dict) -> dict | None:
    """{"provider", "source", "ports", "lines"} when the incident is a shared network's refused traffic, else None."""
    if not str(incident.get("kind", "")).startswith("rule:") or incident.get("internal"):
        return None
    provider = sec_intel.shared(cfg, str(incident.get("source", "")))
    samples = incident.get("samples") or []
    if not provider or not samples or not all(DENIED.search(s) for s in samples):
        return None
    ports = sorted({int(m.group(1)) for s in samples for m in [PORT.search(s)] if m})
    return {"provider": provider, "source": incident["source"], "ports": ports, "lines": int(incident.get("count", 0))}


def hint(provider: str, ports: list[int]) -> str:
    if provider == "Cloudflare" and set(ports) <= {80, 8080, 8880, 2052, 2082, 2086, 2095}:
        return ("Cloudflare raggiunge il tuo server in HTTP, già rifiutato dal firewall: nel pannello di Cloudflare "
                "imposta SSL/TLS «Full (strict)» e «Always Use HTTPS», così passa solo dalla 443 e questo rumore sparisce. Chi c'è dietro: chiedimi «chi c'è dietro Cloudflare?».")
    return (f"{provider} ha cercato porte che il firewall rifiuta già ({', '.join(map(str, ports)) or '?'}): nessun "
            "blocco serve; se una di queste porte la servi tu, controlla la configurazione del proxy di " + provider + ".")


def group(cfg: sys_config.Config, g: dict, now: float | None = None) -> str:
    """Counted in today's line; returns the text to tell the owner, once a day per provider («» otherwise)."""
    now = now or time.time()
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    f = _file(cfg)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    d = data.setdefault(day, {}).setdefault(g["provider"], {"trips": 0, "lines": 0, "sources": [], "ports": [],
                                                             "told": False})
    d["trips"] += 1
    d["lines"] += g["lines"]
    d["sources"] = sorted(set(d["sources"]) | {g["source"]})[:500]
    d["ports"] = sorted(set(d["ports"]) | set(g["ports"]))
    told = "" if d["told"] else (f"{g['provider']}: {d['lines']} tentativi già rifiutati da {len(d['sources'])} "
                                 f"indirizzi oggi (porte {', '.join(map(str, d['ports']))}). Non è un incidente. "
                                 + hint(g["provider"], d["ports"]))
    d["told"] = True
    for old in sorted(data)[:-30]:                       # a month of days kept
        data.pop(old)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return told
