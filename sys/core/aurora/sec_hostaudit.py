# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own machine seen as a security officer would (owner, 2026-10-08: «un menù a parte per il firewall di Aurora
con la sua gestione… simile ad un mini CISO»): what listens on it and who can reach it.

sockets(): the listening sockets (`ss -tulnpH`, no root: a root service shows no process). Each is
  local      bound to loopback (127.*, ::1, %lo) or a virtual network of this machine (a bridge of its own VMs or
             containers: virbr*, docker*, br-*): nobody outside reaches it
  expected   one of Aurora's own doors: Caddy (AURORA_HTTPS_PORT TCP and UDP, AURORA_HTTP_PORT), the sentinel's syslog
             port, the decoys (owner, 27 Oct: «firewall di aurora segnala cose che non capisco» — her own HTTPS port on
             8443 and the VMs' DNS on their bridges were «unknown services reachable from the network»)
  exposed    reachable from the network: said with what it is and whether it is needed
findings(): the exposed ones judged — an unknown service on every interface is worth a look; SSH and desktop
  services (KDE Connect) are common and said low; outgoing UDP of a client (cloudflared) is not a service.
Read only: Aurora's firewall on this machine (sec_hostfw) blocks addresses; closing a service is the owner's.
"""
from __future__ import annotations

import re
import subprocess

from . import sys_config

BRIDGES = ("virbr", "docker", "br-", "vnet", "lxc", "veth")        # this machine's own guests' networks


def known(cfg: sys_config.Config) -> dict:
    """Aurora's own doors, on the ports the settings give them."""
    https, http = str(cfg["AURORA_HTTPS_PORT"]), str(cfg["AURORA_HTTP_PORT"])
    return {("tcp", https): "Caddy: l'interfaccia di Aurora (HTTPS)", ("udp", https): "Caddy: HTTP/3",
            ("tcp", http): "Caddy: rinvio a HTTPS"}


def bridged() -> set[str]:
    """The addresses this machine holds on its guests' bridges (a VM's DHCP and DNS listen there, for the VMs)."""
    try:
        out = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {m.group(2) for m in re.finditer(r"^\d+: (\S+)\s+inet6? ([0-9a-fA-F.:]+)/", out, re.M)
            if m.group(1).startswith(BRIDGES)}
COMMON = {("tcp", "22"): ("SSH", "Accesso remoto alla macchina: va bene con le chiavi; con le password è il primo bersaglio",
                          "usare solo le chiavi (PasswordAuthentication no) o limitarlo alla LAN"),
          ("tcp", "1716"): ("KDE Connect", "Lo scambio con il telefono del desktop KDE: ascolta su tutta la rete",
                            "se non lo usi, disattivalo; altrimenti va bene in casa"),
          ("udp", "1716"): ("KDE Connect", "La scoperta dei dispositivi di KDE Connect", "come sopra"),
          ("udp", "5353"): ("mDNS", "La scoperta dei dispositivi nella rete (stampanti, Chromecast)", "normale in casa")}
CLIENTS = ("cloudflared", "kdeconnectd", "avahi-daemon")             # their high UDP ports are a client's, not a door


def _local(addr: str, bridges: set[str] = frozenset()) -> bool:
    host = addr.rsplit(":", 1)[0].strip("[]")
    return (host.startswith("127.") or host in ("::1",) or "%lo" in host or "%virbr" in host
            or host.startswith("192.168.122.") or host.split("%")[0] in bridges)   # this machine's guests' networks


def sockets(raw: str | None = None, bridges: set[str] | None = None) -> list[dict]:
    bridges = bridged() if bridges is None else bridges
    if raw is None:
        try:
            raw = subprocess.run(["ss", "-tulnpH"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            raw = ""
    out, seen = [], set()
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, addr = parts[0], parts[4]
        port = addr.rsplit(":", 1)[-1]
        proc = (re.search(r'\(\("([^"]+)"', line) or [None, ""])[1]
        key = (proto, addr, proc)
        if key in seen or not port.isdigit():
            continue
        seen.add(key)
        out.append({"proto": proto, "address": addr, "port": port, "process": proc, "local": _local(addr, bridges)})
    return out


def findings(cfg: sys_config.Config, socks: list[dict]) -> list[dict]:
    decoys = {p.strip() for p in str(cfg["AURORA_HONEYPOT_PORTS"] or "").split(",") if p.strip()}
    sentinel = str(cfg["AURORA_SENTINEL_BIND"] or "").rsplit(":", 1)[-1]
    out, doors = [], known(cfg)
    for s in socks:
        k = (s["proto"], s["port"])
        if s["local"]:
            s["kind"], s["what"] = "local", "solo da questa macchina"
        elif k in doors:
            s["kind"], s["what"] = "expected", doors[k]
        elif s["port"] in decoys and s["proto"] == "tcp":
            s["kind"], s["what"] = "expected", "esca: chi la tocca viene bloccato"
        elif s["proto"] == "udp" and s["port"] == sentinel:
            s["kind"], s["what"] = "expected", "la sentinella: riceve il syslog del firewall"
        elif s["process"] in CLIENTS and k not in COMMON:
            s["kind"], s["what"] = "client", f"porta di un client ({s['process']}), non un servizio"
        elif k in COMMON:
            name, why, fix = COMMON[k]
            s["kind"], s["what"] = "exposed", name
            out.append({"severity": "low", "title": f"{name} raggiungibile dalla rete ({s['proto']} {s['port']})",
                        "why": why, "fix": fix, "port": s["port"]})
        else:
            s["kind"], s["what"] = "exposed", s["process"] or "servizio di sistema"
            out.append({"severity": "medium", "title": f"Servizio sconosciuto raggiungibile dalla rete: {s['proto']} "
                                                     f"{s['address']}" + (f" ({s['process']})" if s["process"] else ""),
                        "why": "Una porta aperta su tutta la rete che Aurora non riconosce: se non serve, è una porta in più",
                        "fix": "capire quale programma è (sudo ss -tulnp) e chiuderlo o legarlo a 127.0.0.1", "port": s["port"]})
    # one finding per service, not one per address family
    unique = {f["title"].split(" (")[0] + f.get("port", ""): f for f in out}
    return sorted(unique.values(), key=lambda f: {"high": 0, "medium": 1, "low": 2}[f["severity"]])


def run(cfg: sys_config.Config) -> dict:
    socks = sockets()
    found = findings(cfg, socks)
    return {"sockets": socks, "findings": found,
            "counts": {k: sum(1 for s in socks if s.get("kind") == k) for k in ("local", "expected", "client", "exposed")}}
