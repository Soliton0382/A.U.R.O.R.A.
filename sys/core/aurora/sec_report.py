# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The week of the house's security (owner, 2026-10-06): a score, the incidents grouped into "campaigns", what the
defences did, what is still missing — told on Monday morning (the security plugin's routine) and asked any time.

Score: 100, minus what happened (an incident from outside: high 6, medium 3, low 1; from inside not from a known
device: high 8, medium 4) and minus what is not in place (the firewall's API, Aurora's own firewall, the threat lists,
a backup in the last 2 days: 5 each); never below 0. A campaign: the same kind from the same /24 network at least
twice in the week. Measured from the stored incidents and states, never estimated.
"""
from __future__ import annotations

import ipaddress
import time
from collections import Counter, defaultdict

from . import sys_config


def week(cfg: sys_config.Config, days: float = 7) -> dict:
    from datetime import datetime
    from . import sec_fwapi, sec_hostfw, sec_intel, sys_backup
    from .sec_incidents import Incidents
    since = time.time() - days * 86400
    items = []
    for i in Incidents(cfg).list(None, True):
        try:
            t = datetime.strptime(i["received"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
        except (KeyError, ValueError):
            continue
        if t >= since:
            items.append(i)
    score, minus = 100, []
    for i in items:
        inside = i.get("internal")
        if inside and i.get("known") and i["kind"] != "honeypot":
            continue
        w = {"high": 8, "medium": 4, "low": 0}[i["severity"]] if inside else {"high": 6, "medium": 3, "low": 1}[i["severity"]]
        score -= w * (1 + min(int(i.get("repeats") or 0), 4) // 2)
    camp = defaultdict(list)
    for i in items:
        try:
            net = str(ipaddress.ip_network(f"{i['source']}/24", strict=False))
        except ValueError:
            continue
        camp[(i["kind"], net)].append(i)
    campaigns = [{"kind": k, "network": n, "incidents": len(v), "events": sum(int(x.get("count") or 0) for x in v)}
                 for (k, n), v in camp.items() if len(v) >= 2]
    checks = {"firewall_api": sec_fwapi.configured(cfg), "hostfw": sec_hostfw.available(),
              "threat_lists": bool(sec_intel.summary(cfg).get("lists")), "backup": False}
    b = sys_backup.status(cfg).get("last") or {}
    checks["backup"] = bool(b.get("at") and time.time() - float(b["at"]) < 2 * 86400)
    for k, ok in checks.items():
        if not ok:
            score -= 5
            minus.append(k)
    return {"days": days, "score": max(0, score), "incidents": len(items), "by_severity": dict(Counter(i["severity"] for i in items)),
            "by_kind": dict(Counter(i["kind"] for i in items).most_common(8)), "campaigns": sorted(campaigns, key=lambda c: -c["events"])[:10],
            "blocked": {"firewall": sum(1 for i in items if i.get("defence") == "blocked"),
                        "this_machine": sum(1 for i in items if i.get("hostfw") == "blocked")},
            "checks": checks, "missing": minus}


NAMES = {"firewall_api": "l'API del firewall", "hostfw": "il firewall di Aurora (sudo bash sys/deploy/nft/install.sh)",
         "threat_lists": "le liste pubbliche di attaccanti", "backup": "un backup negli ultimi 2 giorni"}


def text(r: dict) -> str:
    lines = [f"🛡️ Sicurezza degli ultimi {r['days']:g} giorni — punteggio {r['score']}/100",
             f"Incidenti: {r['incidents']} ({', '.join(f'{k} {v}' for k, v in r['by_severity'].items()) or 'nessuno'})"]
    if r["by_kind"]:
        lines.append("Per tipo: " + ", ".join(f"{k} {v}" for k, v in r["by_kind"].items()))
    for c in r["campaigns"]:
        lines.append(f"- campagna: {c['kind']} dalla rete {c['network']}, {c['incidents']} incidenti, {c['events']} eventi")
    lines.append(f"Bloccati: {r['blocked']['firewall']} sul firewall, {r['blocked']['this_machine']} sul computer di Aurora")
    if r["missing"]:
        lines.append("Manca: " + "; ".join(NAMES[m] for m in r["missing"]))
    return "\n".join(lines)
