# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every way out of Aurora's services, learnt and watched (ROADMAP N50; owner, 2026-10-27: «il traffico legittimo va
bene… è il traffico anomalo che non va bene (come un invio di file o richieste di connessione esterne così dal
nulla)… facciamo la parte dinamica che permette un controllo e decisione per poi avere anche lì il pilota automatico…
la suite di controllo la voglio completa»).

The sentinel samples the sockets of Aurora's own services every SAMPLE_S (their cgroups: aurora-*.service; the
owner's desktop on the same machine is not looked at) and keeps, per service, the networks it reaches (by autonomous
system, from RIPEstat, else by address) with when, how often and the most it sent on one connection
(<STATUS>/egress_baseline.json, the sentinel's alone). For LEARN_DAYS it only learns. Then:
  egress_new     a service reaches a network it never reached — high when nothing was running (the API's runs: a
                 connection «dal nulla»), medium while a run was;
  egress_upload  a connection sends more than UPLOAD_BYTES and UPLOAD_FACTOR times the most that service ever sent
                 to that network: a file going out — high.
The owner decides on each incident (legitimate: learnt; or the network on the deny list, sec_egress), and the Autonomy
page decides who decides (api/incidents): at 🚀 a new network met while a run was working is learnt by herself, one
met with nothing running or carrying a file is denied by herself unless it is a shared network (a cloud's or a CDN's:
denying it would cut off half the web) — always told. The owner's answers: <STATUS>/egress_decisions.json (the API's
alone), read here every minute."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import sec_egress, sys_config

LEARN_DAYS = 7
SAMPLE_S = 10
UPLOAD_BYTES = 10 * 2**20        # M264: the most one connection of a service sent while working was 31 KB
UPLOAD_FACTOR = 4
ONCE_S = 3600                    # one incident per service and network an hour
LOOKUPS_PER_MIN = 30             # RIPEstat asked at most this often (a harvest opens many addresses at once)


def _status(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR")


def _read(f: Path, empty: dict) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty


def _write(f: Path, data: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def baseline(cfg: sys_config.Config) -> dict:
    return _read(_status(cfg) / "egress_baseline.json", {"since": 0, "services": {}})


def decisions(cfg: sys_config.Config) -> dict:
    """{service: {network key: "legit" | "denied"}} — the owner's answers, or Aurora's at 🚀."""
    return _read(_status(cfg) / "egress_decisions.json", {})


def decide(cfg: sys_config.Config, service: str, key: str, state: str) -> dict:
    if state not in ("legit", "denied"):
        raise ValueError("state: legit or denied")
    d = decisions(cfg)
    d.setdefault(service, {})[key] = state
    _write(_status(cfg) / "egress_decisions.json", d)
    return d


def sockets() -> list[dict]:
    """Every TCP connection of this user's processes with a public peer: pid, process, peer, port, bytes sent."""
    try:
        out = subprocess.run(["ss", "-tinpH"], capture_output=True, text=True, timeout=10).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []
    rows, i = [], 0
    while i < len(out):
        line = out[i]
        info = out[i + 1] if i + 1 < len(out) and out[i + 1][:1] in ("\t", " ") else ""
        i += 2 if info else 1
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        f = line.split()
        if not m or len(f) < 5:
            continue
        peer, _, port = f[4].rpartition(":")
        peer = peer.strip("[]").removeprefix("::ffff:")
        try:
            a = ipaddress.ip_address(peer.split("%")[0])
        except ValueError:
            continue
        if not a.is_global:                               # the house, loopback, documentation ranges
            continue
        sent = re.search(r"bytes_sent:(\d+)", info)
        rows.append({"pid": int(m.group(2)), "process": m.group(1), "peer": peer, "port": port,
                     "state": f[0], "sent": int(sent.group(1)) if sent else 0})
    return rows


def service_of(pid: int) -> str:
    """aurora-api.service and the like, or '' for a process not Aurora's (the owner's desktop)."""
    try:
        cg = Path(f"/proc/{pid}/cgroup").read_text().strip().rsplit("/", 1)[-1]
    except OSError:
        return ""
    return cg if cg.startswith("aurora-") and cg.endswith(".service") else ""


class Networks:
    """An address's network, kept across restarts (<STATUS>/egress_networks.json), RIPEstat asked sparingly."""

    def __init__(self, cfg: sys_config.Config, lookup=sec_egress.network_of):
        self.file = _status(cfg) / "egress_networks.json"
        self.known = _read(self.file, {})
        self.lookup, self.asked = lookup, []

    def of(self, ip: str, now: float) -> dict:
        if ip in self.known:
            return self.known[ip]
        self.asked = [t for t in self.asked if now - t < 60]
        if len(self.asked) >= LOOKUPS_PER_MIN:
            return {}                                     # asked again at the next sample
        self.asked.append(now)
        net = self.lookup(ip) or {}
        self.known[ip] = net
        if net:
            _write(self.file, self.known)
        return net


def key_of(net: dict, ip: str) -> str:
    return f"AS{net['asn']}" if net.get("asn") else f"ip:{ip}"


class EgressWatch:
    """The sentinel's look at Aurora's own ways out, every SAMPLE_S."""

    def __init__(self, cfg: sys_config.Config, busy=lambda: False, sample=sockets, owner=service_of, networks=None):
        self.cfg, self.busy, self.sample, self.owner = cfg, busy, sample, owner
        self.nets = networks or Networks(cfg)
        self.base = baseline(cfg)
        self.answers = decisions(cfg)
        self.read_at = time.time()
        self.told: dict[tuple[str, str], float] = {}

    def learning(self, now: float) -> bool:
        return now - self.base.get("since", now) < LEARN_DAYS * 86400

    def look(self, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        if not self.base.get("since"):
            self.base["since"] = now
        if now - self.read_at > 60:
            self.answers, self.read_at = decisions(self.cfg), now
        found, changed, busy = [], False, None
        for s in self.sample():
            svc = self.owner(s["pid"])
            if not svc:
                continue
            net = self.nets.of(s["peer"], now)
            if not net and s["peer"] not in self.nets.known:
                continue                                  # its network asked at the next sample
            key = key_of(net, s["peer"])
            seen = self.base["services"].setdefault(svc, {})
            entry = seen.get(key)
            answer = self.answers.get(svc, {}).get(key)
            if entry is None:
                if not self.learning(now) and answer is None:
                    busy = self.busy() if busy is None else busy
                    found += self._tell("egress_new", svc, key, net, s, now, busy)
                seen[key] = {"holder": net.get("holder", ""), "first": now, "last": now, "seen": 1,
                             "max_sent": s["sent"], "learning": self.learning(now)}
                changed = True
                continue
            entry["last"], entry["seen"] = now, entry.get("seen", 0) + 1
            limit = max(UPLOAD_BYTES, UPLOAD_FACTOR * entry.get("max_sent", 0))
            if s["sent"] > limit and not self.learning(now) and answer != "legit":
                busy = self.busy() if busy is None else busy
                found += self._tell("egress_upload", svc, key, net, s, now, busy, limit)
            if self.learning(now) or answer == "legit":
                entry["max_sent"] = max(entry.get("max_sent", 0), s["sent"])
            changed = True
        if changed:
            _write(_status(self.cfg) / "egress_baseline.json", self.base)
        return found

    def _tell(self, kind: str, svc: str, key: str, net: dict, s: dict, now: float, busy: bool,
              limit: int = 0) -> list[dict]:
        if now - self.told.get((svc, key), 0) < ONCE_S:
            return []
        self.told[(svc, key)] = now
        from . import sec_intel
        shared = sec_intel.shared(self.cfg, s["peer"]) or ""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
        who = f"{key} {net.get('holder', '')}".strip()
        name = svc.removesuffix(".service")
        if kind == "egress_new":
            title = f"{name}: una rete mai vista, {who}"
            why = (f"{name} ({s['process']}) ha aperto una connessione verso {s['peer']}:{s['port']} ({who}), una rete "
                   "che non aveva mai raggiunto" + (" mentre nessun lavoro era in corso" if not busy
                                                    else " durante un lavoro in corso") + f"; inviati {s['sent']} byte.")
        else:
            title = f"{name}: {s['sent'] // 2**20} MB inviati a {who}"
            why = (f"{name} ({s['process']}) ha inviato {s['sent']} byte su una connessione verso {s['peer']}:{s['port']} "
                   f"({who}), oltre il limite di {limit} byte di quello che aveva mai mandato lì.")
        return [{"kind": kind, "source": "127.0.0.1", "count": 1, "internal": True, "first": stamp, "last": stamp,
                 "samples": [json.dumps(s)],
                 "detail": {"title": title, "why": why, "service": svc, "key": key, "destination": s["peer"],
                            "process": s["process"], "sent": s["sent"], "busy": busy, "shared": shared,
                            "asn": net.get("asn"), "holder": net.get("holder", ""),
                            "action": "È legittimo? Segnalo come tale e lo impara; altrimenti metti la rete in "
                                      "blacklist." + (f" Attenzione: è una rete condivisa ({shared})." if shared else "")}}]


KINDS = ("model_egress", "egress_deny", "egress_new", "egress_upload")


def report(cfg: sys_config.Config, now: float | None = None, incidents: list[dict] | None = None) -> dict:
    """The ways-out page's view (and the Today tile's): learning or watching, every service's networks with the answers,
    today's numbers, the deny list, the model watch, and the ways-out incidents of the last 30 days."""
    now = time.time() if now is None else now
    base, answers = baseline(cfg), decisions(cfg)
    since = base.get("since") or now
    t = time.localtime(now)
    midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    nets_all = [(svc, v) for svc, nets in base.get("services", {}).items() for v in nets.values()]
    deny = sec_egress.load(cfg)
    recent = [i for i in (incidents or []) if i.get("kind") in KINDS
              and float(i.get("received_ts") or 0) >= now - 30 * 86400]
    from collections import Counter
    out = {"today": {"networks": sum(1 for _, v in nets_all if v.get("last", 0) >= midnight),
                     "new": sum(1 for _, v in nets_all if v.get("first", 0) >= midnight and not v.get("learning")),
                     "services": sorted({s for s, v in nets_all if v.get("last", 0) >= midnight}),
                     "incidents": sum(1 for i in recent if float(i.get("received_ts") or 0) >= midnight)},
           "deny": {"asns": sec_egress.asns(cfg), "prefixes": len(deny.get("prefixes", [])), "at": deny.get("at", 0)},
           "model": {"processes": len(sec_egress._model_pids())},
           "incidents": {"by_kind": dict(Counter(i["kind"] for i in recent)),
                         "open": sum(1 for i in recent if i.get("status") == "open"),
                         "latest": [{"id": i["id"], "kind": i["kind"], "severity": i.get("severity"), "status": i.get("status"),
                                     "title": (i.get("detail") or {}).get("title", ""), "received": i.get("received"),
                                     "decided": i.get("decided") or i.get("deny") or i.get("verdict") or ""}
                                    for i in recent[:12]]}}
    services = {svc: sorted(({"key": k, **v, "answer": answers.get(svc, {}).get(k, "")} for k, v in nets.items()),
                            key=lambda x: -x.get("seen", 0))
                for svc, nets in base.get("services", {}).items()}
    return {"since": since, "learn_until": since + LEARN_DAYS * 86400, "learning": now - since < LEARN_DAYS * 86400,
            "services": services, "rule": {"upload_bytes": UPLOAD_BYTES, "factor": UPLOAD_FACTOR, "learn_days": LEARN_DAYS,
                                           "sample_s": SAMPLE_S}, **out}
