# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own machine seen as a security officer would (owner, 2026-10-08: «un menù a parte per il firewall di Aurora
con la sua gestione… simile ad un mini CISO»): what listens on it and who can reach it.

sockets(): the listening sockets (`ss -tulnpH`, no root: a root service shows no process). Each is
  local      bound to loopback (127.*, ::1, %lo) or a virtual network of this machine (virbr): nobody outside reaches it
  expected   one of Aurora's own doors: Caddy (80, 443 TCP/UDP), the sentinel's syslog port, the decoys
  exposed    reachable from the network: said with what it is and whether it is needed
findings(): the exposed ones judged — an unknown service on every interface is worth a look; SSH and desktop
  services (KDE Connect) are common and said low; outgoing UDP of a client (cloudflared) is not a service.
Read only: Aurora's firewall on this machine (sec_hostfw) blocks addresses; closing a service is the owner's.
"""
from __future__ import annotations

import re
import subprocess

from . import sys_config

KNOWN = {("tcp", "443"): "Caddy: l'interfaccia di Aurora (HTTPS)", ("udp", "443"): "Caddy: HTTP/3",
         ("tcp", "80"): "Caddy: rinvio a HTTPS"}
COMMON = {("tcp", "22"): ("SSH", "Accesso remoto alla macchina: va bene con le chiavi; con le password è il primo bersaglio",
                          "usare solo le chiavi (PasswordAuthentication no) o limitarlo alla LAN"),
          ("tcp", "1716"): ("KDE Connect", "Lo scambio con il telefono del desktop KDE: ascolta su tutta la rete",
                            "se non lo usi, disattivalo; altrimenti va bene in casa"),
          ("udp", "1716"): ("KDE Connect", "La scoperta dei dispositivi di KDE Connect", "come sopra"),
          ("udp", "5353"): ("mDNS", "La scoperta dei dispositivi nella rete (stampanti, Chromecast)", "normale in casa")}
CLIENTS = ("cloudflared", "kdeconnectd", "avahi-daemon")             # their high UDP ports are a client's, not a door


def _local(addr: str) -> bool:
    host = addr.rsplit(":", 1)[0].strip("[]")
    return (host.startswith("127.") or host in ("::1",) or "%lo" in host or "%virbr" in host
            or host.startswith("192.168.122."))                      # libvirt's own network: this machine's guests


def sockets(raw: str | None = None) -> list[dict]:
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
        out.append({"proto": proto, "address": addr, "port": port, "process": proc, "local": _local(addr)})
    return out


def findings(cfg: sys_config.Config, socks: list[dict]) -> list[dict]:
    decoys = {p.strip() for p in str(cfg["AURORA_HONEYPOT_PORTS"] or "").split(",") if p.strip()}
    sentinel = str(cfg["AURORA_SENTINEL_BIND"] or "").rsplit(":", 1)[-1]
    out = []
    for s in socks:
        k = (s["proto"], s["port"])
        if s["local"]:
            s["kind"], s["what"] = "local", "solo da questa macchina"
        elif k in KNOWN:
            s["kind"], s["what"] = "expected", KNOWN[k]
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
