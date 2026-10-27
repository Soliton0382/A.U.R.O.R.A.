# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Networks Aurora never reaches (owner, 2026-10-27, after a Qwen model was caught writing a curl to a bucket in
Beijing: «basterebbe mettere come destinazioni in black list le destinazioni verso Alibaba… lascerei comunque una
sentinella per capire se da aurora escono file verso destinazioni in black list»).

AURORA_EGRESS_DENY_ASNS names the networks by their autonomous systems (by default Alibaba Cloud and Taobao); their
announced IPv4 prefixes come from RIPEstat (public, no key), collapsed and kept in <STATUS>/egress_deny.json, fetched
again after REFRESH_DAYS — a failed fetch keeps the last list. Two uses:
  - sys_install_services writes them into the units of Aurora's services (IPAddressDeny): the services — the tools,
    the plugins, the harvest — cannot reach them; the owner's desktop on the same machine is not touched;
  - the sentinel (feed) reads the firewall's lines: one from this machine to a listed network is a high incident,
    never quieted, with the local process that holds the connection when it is still open (ss).
The local reasoner reaches nothing but 127.0.0.1 in any case (its unit: IPAddressDeny=any; M263)."""
from __future__ import annotations

import bisect
import ipaddress
import json
import re
import subprocess
import time
from pathlib import Path

from . import sys_config

RIPESTAT = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}"
REFRESH_DAYS = 7
ONCE_S = 3600                    # one incident per destination an hour


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "egress_deny.json"


def asns(cfg: sys_config.Config) -> list[int]:
    return [int(a) for a in (cfg["AURORA_EGRESS_DENY_ASNS"] or []) if str(a).strip().isdigit()]


def collapse(prefixes: list[str]) -> list[str]:
    """IPv4 prefixes merged where they touch: fewer rules, the same addresses."""
    nets = [ipaddress.ip_network(p, strict=False) for p in prefixes if ":" not in p]
    return [str(n) for n in ipaddress.collapse_addresses(nets)]


def load(cfg: sys_config.Config) -> dict:
    """{"at", "asns", "prefixes"} as kept (an empty list when nothing was fetched yet)."""
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"at": 0, "asns": [], "prefixes": []}


def refresh(cfg: sys_config.Config, fetch=None, force: bool = False) -> dict:
    """The prefixes of the listed networks, fetched again when old or when the list of networks changed."""
    kept, want = load(cfg), asns(cfg)
    if not want:
        return {"at": time.time(), "asns": [], "prefixes": []}
    if not force and kept.get("asns") == want and time.time() - kept.get("at", 0) < REFRESH_DAYS * 86400:
        return kept
    if fetch is None:
        import httpx

        def fetch(asn: int) -> list[str]:
            r = httpx.get(RIPESTAT.format(asn=asn), timeout=30)
            r.raise_for_status()
            return [p["prefix"] for p in r.json()["data"]["prefixes"]]
    try:
        raw = [p for a in want for p in fetch(a)]
    except Exception:                                    # noqa: BLE001 — RIPEstat away: the last list stays
        return kept
    out = {"at": time.time(), "asns": want, "prefixes": collapse(raw)}
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out), encoding="utf-8")
    return out


class Deny:
    """The listed networks, for a quick look-up of an address."""

    def __init__(self, prefixes: list[str]):
        nets = sorted((int(n.network_address), int(n.broadcast_address))
                      for n in (ipaddress.ip_network(p) for p in prefixes))
        self.starts = [a for a, _ in nets]
        self.nets = nets

    def __contains__(self, ip: str) -> bool:
        try:
            v = int(ipaddress.IPv4Address(ip))
        except ValueError:
            return False
        i = bisect.bisect_right(self.starts, v) - 1
        return i >= 0 and self.nets[i][0] <= v <= self.nets[i][1]


def own_addresses() -> set[str]:
    """This machine's IPv4 addresses (the firewall sees it by them)."""
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {m.group(1) for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)/", out)} - {"127.0.0.1"}


def holder(ip: str) -> str:
    """The local process with a connection to `ip` now (this user's processes: ss shows them), or ''."""
    try:
        out = subprocess.run(["ss", "-tunapH", "dst", ip], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return ", ".join(sorted(set(re.findall(r'users:\(\("([^"]+)"', out))))


class Watch:
    """The sentinel's look at each firewall line: this machine towards a listed network."""

    def __init__(self, cfg: sys_config.Config, mine: set[str] | None = None):
        self.cfg = cfg
        self.mine = own_addresses() if mine is None else mine
        self.deny = Deny(load(cfg).get("prefixes", []))
        self.told: dict[str, float] = {}

    def feed(self, f: dict, now: float | None = None) -> dict | None:
        src = f.get("src_ip") or f.get("src") or ""
        dst = f.get("dst_ip") or f.get("dst") or ""
        if src not in self.mine or dst not in self.deny:
            return None
        now = time.time() if now is None else now
        if dst in self.told and now - self.told[dst] < ONCE_S:
            return None
        self.told[dst] = now
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
        who = holder(dst)
        sent = f.get("sent_bytes") or f.get("bytes_sent") or ""
        return {"kind": "egress_deny", "source": src, "count": 1, "internal": True, "first": stamp, "last": stamp,
                "samples": [f.get("_raw", "")[:600]],
                "detail": {"title": f"Verso una rete in blacklist: {dst}",
                           "why": f"Questa macchina ha aperto una connessione verso {dst}:{f.get('dst_port', '?')}, "
                                  f"in una rete della blacklist (AURORA_EGRESS_DENY_ASNS)"
                                  + (f"; processo: {who}" if who else "; il processo non si vede più")
                                  + (f"; byte inviati: {sent}" if sent else "") + ".",
                           "action": "Guarda il processo: un servizio di Aurora non può arrivarci (le sue unit lo "
                                     "vietano), quindi è un altro programma di questa macchina, o le unit vanno "
                                     "riscritte (install.sh).",
                           "destination": dst, "process": who}}
