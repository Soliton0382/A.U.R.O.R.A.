# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall syslog: parse the lines, detect incidents. Defensive only (ethics code, level A).

Lines are key=value syslog (Sophos and most firewalls: `log_type="Firewall" status="Deny"
src_ip=... dst_port=...`), or pfSense's and OPNsense's filterlog (comma-separated, by position: docs.netgate.com
«Raw Filter Log Format», the same on OPNsense) turned into the same fields; a line of neither is kept as plain text. The detector keeps a
sliding window per source address and raises an incident when:
  deny_burst   denied connections from one source >= AURORA_SENTINEL_DENY_THRESHOLD in the window
  port_scan    distinct destination ports from one source >= AURORA_SENTINEL_SCAN_PORTS in the window
  ips_alert    an intrusion-prevention (IPS/IDP) event
  auth_fail    failed authentications from one source >= 10 in the window
An incident per (kind, source) is raised at most once an hour.

What a line says is written by whoever sends it, and a UDP datagram's sender can be forged on the LAN (C566): so the
detector never holds more than it can count — new sources a minute and incidents a minute and an hour are capped
(Budget), what no longer counts is forgotten (prune), a datagram is one log line whatever it carries (one_line), and
the decoys tell a touch at a person's pace (Touches). A forged line can still raise a false incident inside these
limits: only a relay on this machine fed over TLS, or the firewall's own anti-spoofing, closes that.
"""
from __future__ import annotations

import ipaddress
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

PAIR = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')


FILTERLOG = re.compile(r"filterlog(?:\[\d+\]:|:|\s+\d+\s+-\s+-)\s*(\S.*)$")   # RFC 3164 and RFC 5424


def filterlog(csv: str) -> dict | None:
    """pfSense / OPNsense: rule, sub-rule, anchor, tracker, interface, reason, action, direction, IP version, then by
    version: v4 tos, ecn, ttl, id, offset, flags, proto id, proto, length, src, dst; v6 class, flow, hop limit, proto,
    proto id, length, src, dst; then for TCP and UDP the source and destination ports."""
    c = csv.split(",")
    if len(c) < 9 or c[8] not in ("4", "6"):
        return None
    if c[8] == "4":
        if len(c) < 20:
            return None
        proto, src, dst, rest = c[16].lower(), c[18], c[19], c[20:]
    else:
        if len(c) < 17:
            return None
        proto, src, dst, rest = c[12].lower(), c[15], c[16], c[17:]
    f = {"log_type": "Firewall", "log_component": "Firewall Rule", "fw_rule_id": c[3] or c[0], "in_interface": c[4],
         "status": "Deny" if c[6] in ("block", "reject") else "Allow", "direction": c[7], "protocol": proto,
         "src_ip": src, "dst_ip": dst}
    if proto in ("tcp", "udp") and len(rest) >= 2:
        f.update(src_port=rest[0], dst_port=rest[1])
    return f


def parse(line: str) -> dict:
    m = FILTERLOG.search(line)
    fields = (filterlog(m.group(1)) if m else None) or \
        {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)) for m in PAIR.finditer(line)}
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


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def one_line(text: str, limit: int = 8192) -> str:
    """C566: a datagram is ONE log line. A line break inside it (or any control character) would write lines of the
    sender's own making in firewall.log — a forged «allowed» address, a forged time — and the reports, the hunt and
    the scorecard read that file. They are written as visible escapes; a line longer than `limit` is cut."""
    return _CONTROL.sub(lambda m: _ESCAPES.get(m.group(0), f"\\x{ord(m.group(0)):02x}"), text.strip())[:limit]


class Budget:
    """C566: at most `per_min` in any minute and `per_hour` in any hour; what is refused is counted (`refused`)."""

    def __init__(self, per_min: int, per_hour: int | None = None):
        self.per_min, self.per_hour = per_min, per_hour if per_hour is not None else per_min * 60
        self.taken: deque = deque()
        self.refused = 0

    def take(self, now: float) -> bool:
        while self.taken and now - self.taken[0] >= 3600:
            self.taken.popleft()
        if len(self.taken) >= self.per_hour or sum(1 for t in reversed(self.taken) if now - t < 60) >= self.per_min:
            self.refused += 1
            return False
        self.taken.append(now)
        return True


class Touches:
    """C566: the decoys had no limit — every connection was an incident posted to the API, and from a source whose
    incident was closed, a new one with its inquiry (a model run each). A touch is told at a person's pace: one
    incident per source every QUIET_S, the touches in between counted into the next one; PER_MIN and PER_HOUR in all
    (measured on 14.8 days of the owner's incidents, 12 Nov: 1 decoy incident; all the detector's kinds together 4 a
    minute and 8 an hour at most). Used from one thread per decoy port."""
    QUIET_S = 600
    PER_MIN, PER_HOUR = 10, 30
    MAX_SOURCES = 4096

    def __init__(self):
        self.last: dict[str, float] = {}
        self.held: dict[str, int] = {}
        self.budget = Budget(self.PER_MIN, self.PER_HOUR)
        self._lock = threading.Lock()

    def touch(self, src: str, now: float | None = None) -> int:
        """How many touches to tell now for this source (0: none, it is counted for the next one)."""
        now = time.time() if now is None else now
        with self._lock:
            for s in [s for s, t in self.last.items()
                      if now - t >= self.QUIET_S and (not self.held.get(s) or now - t >= 3600)]:
                del self.last[s]                           # a source that never came back: its count is not kept
                self.held.pop(s, None)
            if src not in self.last and len(self.last) >= self.MAX_SOURCES:
                self.budget.refused += 1
                return 0
            n = self.held.get(src, 0) + 1
            if (src in self.last and now - self.last[src] < self.QUIET_S) or not self.budget.take(now):
                self.held[src] = n
                self.last.setdefault(src, now - self.QUIET_S)      # held by the budget: told at the next touch
                return 0
            self.last[src] = now
            self.held.pop(src, None)
            return n


def flood_incident(sender: str, skipped: int, held: int) -> dict:
    """C566: the caps were reached — said once, as an incident, with what was left out. `sender` is the address the
    datagrams say they come from (the firewall's: allowed), which on a LAN can be forged."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return {"kind": "syslog_flood", "source": sender, "count": skipped + held, "internal": is_private(sender),
            "first": stamp, "last": stamp, "samples": [],
            "detail": {"title": "Troppi allarmi dai log del firewall",
                       "why": f"Nell'ultimo minuto i log arrivati come {sender} hanno nominato più origini nuove o più "
                              f"allarmi di quanti una rete di casa ne produca: {skipped} righe da origini nuove non "
                              f"contate e {held} allarmi non aperti. O è una scansione molto estesa, o qualcuno nella "
                              "rete locale sta scrivendo log falsi a nome del firewall (UDP non prova chi lo manda).",
                       "action": "Guarda nel log del firewall (firewall.log) cosa è arrivato in quel minuto; se le "
                                 "righe non sono del firewall, cerca il dispositivo che le manda. Nessun blocco "
                                 "automatico parte da questo avviso."}}


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
    MAX_SOURCES = 4096      # C566: devices remembered at once (a house has tens; a forged flood names millions)

    def __init__(self):
        self.seen: dict[str, deque] = {}
        self._swept = 0.0

    def prune(self, now: float) -> None:
        """C566: a device silent for WINDOW_S is forgotten (every source was kept for ever)."""
        self._swept = now
        for src in [s for s, q in self.seen.items() if not q or now - q[-1][0] > self.WINDOW_S]:
            del self.seen[src]

    def chatter(self, src: str, now: float, port: str = "") -> None:
        if now - self._swept >= 60:
            self.prune(now)
        if src not in self.seen and len(self.seen) >= self.MAX_SOURCES:
            return
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
    # C566, the ceilings measured before the thresholds (12 Nov, 7.5 days of the owner's firewall, 2.8 M lines): at
    # most 65 new sources of refused traffic in a minute (176 counting every line), 68 counted at once; the detector's
    # incidents at most 4 in a minute and 8 in an hour (14.8 days). Beyond these a line is still logged, not counted.
    NEW_SOURCES_PER_MIN = 600
    RAISED_PER_MIN, RAISED_PER_HOUR = 20, 60

    def __init__(self, window_s: float, deny_threshold: int, scan_ports: int, auth_threshold: int = 10):
        self.window, self.deny_n, self.scan_n, self.auth_n = window_s, deny_threshold, scan_ports, auth_threshold
        self.denies: dict[str, deque] = defaultdict(deque)
        self.ports: dict[str, deque] = defaultdict(deque)
        self.auths: dict[str, deque] = defaultdict(deque)
        self.raised: dict[tuple[str, str], float] = {}
        self.seen: dict[str, float] = {}                # C566: every source counted now, and when it last spoke
        self.fresh = Budget(self.NEW_SOURCES_PER_MIN)
        self.alarms = Budget(self.RAISED_PER_MIN, self.RAISED_PER_HOUR)
        self._swept: float | None = None

    def _admit(self, src: str, now: float) -> bool:
        """C566: a source already counted, or a new one within the minute's budget."""
        if src not in self.seen and not self.fresh.take(now):
            return False
        self.seen[src] = now
        return True

    def prune(self, now: float) -> None:
        """C566: the counters kept every source for ever (an empty queue per address, an hour mark per alarm): what is
        outside the window, and an alarm's mark older than its hour, is forgotten."""
        self._swept = now
        for table in (self.denies, self.ports, self.auths):
            for src in list(table):
                self._trim(table[src], now)
                if not table[src]:
                    del table[src]
        for key in [k for k, t in self.raised.items() if now - t >= 3600]:
            del self.raised[key]
        for src in [s for s, t in self.seen.items() if now - t > self.window]:
            del self.seen[src]

    def pressure(self) -> tuple[int, int]:
        """(lines of new sources not counted, incidents not raised) since the last call: the caps at work."""
        out = self.fresh.refused, self.alarms.refused
        self.fresh.refused = self.alarms.refused = 0
        return out

    def _trim(self, q: deque, now: float) -> None:
        while q and now - q[0][0] > self.window:
            q.popleft()

    def _raise(self, kind: str, src: str, q: deque, now: float, detail: dict | None = None) -> Incident | None:
        last = self.raised.get((kind, src))
        if last is not None and now - last < 3600:
            return None
        if not self.alarms.take(now):                   # C566: not marked as raised — it may be once the flood is over
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
        if self._swept is None or now - self._swept >= 60:
            self.prune(now)
        # C583 (the owner's choice, 12 Nov): this house's firewall says it in log_subtype="Denied" alone
        denied = (f.get("status") or f.get("action") or f.get("log_subtype") or "").lower() in (
            "deny", "denied", "drop", "dropped", "reject", "blocked")
        failed = ("fail" in text or "invalid" in text) and ("auth" in text or "login" in text)
        if not (is_ips(f) or denied or failed) or not self._admit(src, now):
            return out                                  # nothing to count, or a new source beyond the budget (C566)
        if is_ips(f):
            if (i := self._raise("ips_alert", src, deque([(now, f["_raw"])]), now,
                                 {"signature": f.get("signature_msg") or f.get("message") or ""})):
                out.append(i)
        if denied:
            q = self.denies[src]
            q.append((now, f["_raw"]))
            self._trim(q, now)
            # C583, measured on 8.1 days (3.07 M lines): 1,168 bursts, 1,150 from the house's own devices — the rules
            # refusing what they should, not an attack: a burst is told from outside only; a device inside that
            # scans still is (port_scan), and its novelties are the baseline's
            if len(q) >= self.deny_n and not is_private(src) and (i := self._raise("deny_burst", src, q, now)):
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
        if failed:
            q = self.auths[src]
            q.append((now, f["_raw"]))
            self._trim(q, now)
            if len(q) >= self.auth_n and (i := self._raise("auth_fail", src, q, now)):
                out.append(i)
        return out
