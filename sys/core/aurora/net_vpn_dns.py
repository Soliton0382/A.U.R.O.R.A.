# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 Aurora's resolver while her VPN is up (net_vpn, run by aurora-vpn): the services ask ADDRESS; a name under one
of the chosen domains goes to the machine's resolver (the home's DNS: the firewall, which knows the devices' panels at
private addresses — owner, 30 Oct: «split tunneling anche per domini selezionati… passa dalla rete standard»), any
other to the tunnel's DNS (asked from this unit, as the service user: through the tunnel).

A chosen name that answers with public addresses: those addresses are told back (on_split) so the unit marks them for
the normal line too; private ones already are on it (the LAN's routes). UDP only: an answer too long for it comes
back truncated and the asker's TCP retry reaches no one (said in STATUS)."""
from __future__ import annotations

import ipaddress
import socket
import struct
import threading

ADDRESS = ("127.0.0.71", 53)
MACHINE = ("127.0.0.53", 53)                       # systemd-resolved's stub: the home's DNS
FALLBACK = "1.1.1.1"                               # the tunnel pushed no DNS: a public one, asked through the tunnel
TIMEOUT_S = 4


def qname(packet: bytes) -> str:
    """The name asked in a DNS query ("" when it cannot be read)."""
    labels, i = [], 12
    try:
        while packet[i]:
            n = packet[i]
            labels.append(packet[i + 1:i + 1 + n].decode("ascii", "replace"))
            i += 1 + n
    except IndexError:
        return ""
    return ".".join(labels).lower()


def _skip_name(p: bytes, i: int) -> int:
    while True:
        n = p[i]
        if n & 0xC0 == 0xC0:
            return i + 2
        if n == 0:
            return i + 1
        i += 1 + n


def addresses(packet: bytes) -> list[tuple[str, int]]:
    """The A and AAAA records of an answer: [(address, ttl)]."""
    try:
        qd, an = struct.unpack("!HH", packet[4:8])
        i = 12
        for _ in range(qd):
            i = _skip_name(packet, i) + 4
        out = []
        for _ in range(an):
            i = _skip_name(packet, i)
            typ, _cls, ttl, ln = struct.unpack("!HHIH", packet[i:i + 10])
            data = packet[i + 10:i + 10 + ln]
            if typ == 1 and ln == 4:
                out.append((socket.inet_ntop(socket.AF_INET, data), ttl))
            elif typ == 28 and ln == 16:
                out.append((socket.inet_ntop(socket.AF_INET6, data), ttl))
            i += 10 + ln
        return out
    except (IndexError, struct.error, ValueError):
        return []


def split(name: str, domains: list[str]) -> bool:
    """`name` is one of the chosen domains or under one."""
    name = name.rstrip(".").lower()
    return any(name == d or name.endswith("." + d) for d in domains)


def public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


class Forwarder:
    """A small UDP forwarder on ADDRESS; `domains()` and `upstream()` are read at each query (the prefs may change)."""

    def __init__(self, domains, upstream, on_split=None, log=None):
        self.domains, self.upstream, self.on_split, self.log = domains, upstream, on_split, log
        self.sock = None

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(ADDRESS)
        threading.Thread(target=self._serve, name="vpn-dns", daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                data, client = self.sock.recvfrom(4096)
            except OSError:
                return
            threading.Thread(target=self._one, args=(data, client), daemon=True).start()

    def _one(self, data: bytes, client) -> None:
        name = qname(data)
        home = split(name, self.domains())
        to = MACHINE if home else ((self.upstream() or [FALLBACK])[0], 53)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as up:
                up.settimeout(TIMEOUT_S)
                up.sendto(data, to)
                answer, _ = up.recvfrom(4096)
        except OSError as e:
            if self.log:
                self.log.warning("vpn dns: %s for a %s name", type(e).__name__, "home" if home else "tunnel")
            return
        if home and self.on_split:
            found = [(a, t) for a, t in addresses(answer) if public(a)]
            if found:
                self.on_split(found)
        try:
            self.sock.sendto(answer, client)
        except OSError:
            pass
