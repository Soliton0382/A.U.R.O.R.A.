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
        if kind in ("idp", "ips", "intrusion", "atp") or "intrusion" in text or "ips" == (f.get("log_component") or "").lower():
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
