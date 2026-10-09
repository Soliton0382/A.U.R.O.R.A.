# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall syslog: parse the lines, detect incidents. Defensive only (ethics code, level A).

Lines are key=value syslog (Sophos and most firewalls: `log_type="Firewall" status="Deny"
src_ip=... dst_port=...`); a line without pairs is kept as plain text. The detector keeps a
sliding window per source address and raises an incident when:
  deny_burst   denied connections from one source >= AURORA_SENTINEL_DENY_THRESHOLD in the window
  port_scan    distinct destination ports from one source >= AURORA_SENTINEL_SCAN_PORTS in the window
  ips_alert    an intrusion-prevention (IPS/IDP) event
  auth_fail    failed authentications from one source >= 10 in the window
An incident per (kind, source) is raised at most once an hour.
"""
from __future__ import annotations

import ipaddress
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

PAIR = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')


def parse(line: str) -> dict:
    fields = {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)) for m in PAIR.finditer(line)}
    fields["_raw"] = line.strip()
    return fields


def src_of(f: dict) -> str | None:
    for k in ("src_ip", "srcip", "src", "source_ip"):
        if f.get(k):
            return f[k]
    return None


def is_ips(f: dict) -> bool:
    """An intrusion-prevention or threat-protection event (IDP/IPS/ATP): the rule the detector and the security
    plugin share."""
    kind = (f.get("log_type") or "").lower()
    return kind in ("idp", "ips", "intrusion", "atp") or "intrusion" in f.get("_raw", "").lower() \
        or (f.get("log_component") or "").lower() == "ips"


# the house's own chatter the firewall refuses (M161: 98 % of 585,591 «Appliance Access Denied» lines from the LAN went
# to broadcast or multicast addresses — device discovery: Tuya 6667, Plex 32412/32414, NetBIOS 137/138, Spotify
# 57621, NAT-PMP 5351, DHCP 67 — and the rest asked the firewall's own DNS, HTTP, DNS over TLS; no LAN device ever
# touched more than 9 ports): logged and learned by the baseline, never a «port scan» (81 % of the incidents were these)
HOUSE_PORTS = {"53", "67", "68", "80", "123", "137", "138", "139", "443", "853", "1900", "3702", "5351", "5353", "5355"}


def _broadcast(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_multicast or ip.endswith(".255") or ip == "255.255.255.255"


def household(f: dict) -> bool:
    """A LAN device's discovery broadcast, or its question to the firewall's own house services, refused by the
    firewall: noise for the detectors (still logged, still in the baseline)."""
    if (f.get("log_subtype") or "").lower() != "denied" or not str(f.get("log_id", "")).startswith("010302"):
        return False
    src = src_of(f)
    if not src or not is_private(src):
        return False
    return _broadcast(f.get("dst_ip", "")) or str(f.get("dst_port", "")) in HOUSE_PORTS


class Recon:
    """A device that looks around the house, then reaches out to a flagged address: the owner, 10 Oct — «una minaccia è
    se prova ad uscire esternamente, non limitarsi a mandare messaggi broadcast interni; un'accoppiata delle due in
    rapida successione può determinare un problema di security». The house's chatter alone is noise (M161); the same
    device's chatter followed within WINDOW_S by a threat match going out is one high incident: «ricognizione, poi
    uscita» — what a compromised device does (look for neighbours, call its server).
    «Looking around» is not the steady chatter (a smart plug broadcasts every few seconds, all day): it is many
    services asked at once — MIN_PORTS distinct ports in WINDOW_S. Measured on 10 days of the owner's network: the most
    any device reached was 6 (a phone), the others 5 or fewer; with lines alone (20 a window) the check fired 20 times
    in 10 days on chatty devices, i.e. at every threat match they made."""
    WINDOW_S = 600
    MIN_PORTS = 8

    def __init__(self):
        self.seen: dict[str, deque] = {}

    def chatter(self, src: str, now: float, port: str = "") -> None:
        q = self.seen.setdefault(src, deque())
        q.append((now, port))
        while q and now - q[0][0] > self.WINDOW_S:
            q.popleft()

    def out(self, f: dict, now: float) -> dict | None:
        """The correlated incident when this threat line goes out from a device that was looking around."""
        src, dst = src_of(f), f.get("dst_ip", "")
        if not src or not is_private(src) or not dst or is_private(dst):
            return None
        q = self.seen.get(src) or deque()
        while q and now - q[0][0] > self.WINDOW_S:
            q.popleft()
        ports = sorted({p for _, p in q if p})
        if len(ports) < self.MIN_PORTS:
            return None
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        return {"kind": "recon_then_out", "source": src, "count": len(q), "internal": True, "first": stamp,
                "last": stamp, "samples": [f.get("_raw", "")[:600]],
                "detail": {"title": "Ricognizione, poi uscita", "destination": dst, "ports": ports[:30],
                           "why": f"{len(ports)} servizi diversi cercati nella rete di casa negli ultimi "
                                  f"{self.WINDOW_S // 60} minuti (di solito un dispositivo ne usa 1-6), poi un contatto "
                                  f"verso {dst}, segnalato come minaccia",
                           "action": "Isola il dispositivo (Wi-Fi ospiti o blocco sul firewall) e controlla cosa ha "
                                     "installato: è lo schema di un dispositivo compromesso"}}


LOCAL_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
                                                  "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10")]


def is_private(ip: str) -> bool:
    """A local network address (the owner's own LAN): an incident from there means a host inside."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a.version == n.version and a in n for n in LOCAL_NETS)


@dataclass
class Incident:
    kind: str
    source: str
    count: int
    first: float
    last: float
    internal: bool
    samples: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "source": self.source, "count": self.count, "internal": self.internal,
                "first": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.first)),
                "last": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.last)),
                "samples": self.samples[-5:], "detail": self.detail}


class Detector:
    def __init__(self, window_s: float, deny_threshold: int, scan_ports: int, auth_threshold: int = 10):
        self.window, self.deny_n, self.scan_n, self.auth_n = window_s, deny_threshold, scan_ports, auth_threshold
        self.denies: dict[str, deque] = defaultdict(deque)
        self.ports: dict[str, deque] = defaultdict(deque)
        self.auths: dict[str, deque] = defaultdict(deque)
        self.raised: dict[tuple[str, str], float] = {}

    def _trim(self, q: deque, now: float) -> None:
        while q and now - q[0][0] > self.window:
            q.popleft()

    def _raise(self, kind: str, src: str, q: deque, now: float, detail: dict | None = None) -> Incident | None:
        last = self.raised.get((kind, src))
        if last is not None and now - last < 3600:
            return None
        self.raised[(kind, src)] = now
        return Incident(kind, src, len(q) if q else 1, q[0][0] if q else now, now, is_private(src),
                        [x[1] for x in list(q)[-5:]] if q else [], detail or {})

    def feed(self, f: dict, now: float | None = None) -> list[Incident]:
        now = time.time() if now is None else now
        src = src_of(f)
        if not src:
            return []
        text = f["_raw"].lower()
        kind = (f.get("log_type") or "").lower()
        out = []
        if is_ips(f):
            if (i := self._raise("ips_alert", src, deque([(now, f["_raw"])]), now,
                                 {"signature": f.get("signature_msg") or f.get("message") or ""})):
                out.append(i)
        denied = (f.get("status") or f.get("action") or "").lower() in ("deny", "denied", "drop", "dropped", "reject", "blocked")
        if denied:
            q = self.denies[src]
            q.append((now, f["_raw"]))
            self._trim(q, now)
            if len(q) >= self.deny_n and (i := self._raise("deny_burst", src, q, now)):
                out.append(i)
            port = f.get("dst_port") or f.get("dstport") or f.get("dport")
            if port:
                p = self.ports[src]
                p.append((now, port))
                self._trim(p, now)
                distinct = {x[1] for x in p}
                if len(distinct) >= self.scan_n and (i := self._raise("port_scan", src, p, now,
                                                                      {"ports": sorted(distinct, key=str)[:30]})):
                    out.append(i)
        if ("fail" in text or "invalid" in text) and ("auth" in text or "login" in text):
            q = self.auths[src]
            q.append((now, f["_raw"]))
            self._trim(q, now)
            if len(q) >= self.auth_n and (i := self._raise("auth_fail", src, q, now)):
                out.append(i)
        return out
