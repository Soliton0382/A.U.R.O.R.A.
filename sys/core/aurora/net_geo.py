# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where an IP address is, offline (the visual traceroute, owner 10 Oct: «dato un indirizzo IP ti faceva vedere sul
mappamondo gli hop fino ad arrivare alla posizione dell'IP»).

DB-IP's free «lite» databases (IP Geolocation by DB-IP, https://db-ip.com, CC BY 4.0): city (country, region, city,
latitude, longitude) and ASN (the network's number and organisation), MaxMind DB files downloaded once a month into
<STATUS>/geo — no address is ever sent to anyone to be placed. Read by the small MaxMind DB reader below (the format
is public: a binary search tree on the address's bits, then a data section), so no library is added.
A position is the database's estimate for the network, often its city or only its country — never a street.
"""
from __future__ import annotations

import ipaddress
import mmap
import struct
import threading
import time
from pathlib import Path

from . import sys_config

FILES = {"city": "dbip-city-lite.mmdb", "asn": "dbip-asn-lite.mmdb"}
URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{month}.mmdb.gz"
CREDIT = "IP Geolocation by DB-IP (db-ip.com, CC BY 4.0)"
MARKER = b"\xab\xcd\xefMaxMind.com"


class Reader:
    """A MaxMind DB file, read on a memory map."""

    def __init__(self, path: Path):
        self.f = open(path, "rb")
        self.buf = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        at = self.buf.rfind(MARKER, max(0, len(self.buf) - 128 * 1024))
        if at < 0:
            raise ValueError(f"{path.name}: not a MaxMind DB file")
        self.meta, _ = self._decode(at + len(MARKER), base=at + len(MARKER))
        self.nodes, self.size = int(self.meta["node_count"]), int(self.meta["record_size"])
        self.tree = self.size * 2 // 8 * self.nodes
        self.data = self.tree + 16
        self.v4 = 0
        if int(self.meta.get("ip_version", 4)) == 6:          # IPv4 addresses live under ::/96
            node = 0
            for _ in range(96):
                if node >= self.nodes:
                    break
                node = self._record(node, 0)
            self.v4 = node

    def _record(self, node: int, bit: int) -> int:
        b, s = self.buf, self.size
        o = node * s * 2 // 8
        if s == 24:
            return int.from_bytes(b[o + bit * 3: o + bit * 3 + 3], "big")
        if s == 28:
            mid = b[o + 3]
            if bit == 0:
                return ((mid & 0xF0) << 20) | int.from_bytes(b[o: o + 3], "big")
            return ((mid & 0x0F) << 24) | int.from_bytes(b[o + 4: o + 7], "big")
        if s == 32:
            return int.from_bytes(b[o + bit * 4: o + bit * 4 + 4], "big")
        raise ValueError(f"record size {s}")

    def get(self, ip: str):
        a = ipaddress.ip_address(ip)
        bits = a.max_prefixlen
        node = self.v4 if a.version == 4 and int(self.meta.get("ip_version", 4)) == 6 else 0
        n = int(a)
        for i in range(bits):
            if node >= self.nodes:
                break
            node = self._record(node, (n >> (bits - 1 - i)) & 1)
        if node <= self.nodes:                                 # == nodes: not in the database
            return None
        return self._decode(self.data + (node - self.nodes - 16), base=self.data)[0]

    def _decode(self, o: int, base: int):
        b = self.buf
        ctrl = b[o]
        o += 1
        kind = ctrl >> 5
        if kind == 1:                                          # a pointer into the data section
            ss, v = (ctrl >> 3) & 3, ctrl & 7
            if ss == 0:
                p, o = (v << 8) | b[o], o + 1
            elif ss == 1:
                p, o = ((v << 16) | int.from_bytes(b[o: o + 2], "big")) + 2048, o + 2
            elif ss == 2:
                p, o = ((v << 24) | int.from_bytes(b[o: o + 3], "big")) + 526336, o + 3
            else:
                p, o = int.from_bytes(b[o: o + 4], "big"), o + 4
            return self._decode(base + p, base)[0], o
        if kind == 0:
            kind, o = 7 + b[o], o + 1
        size = ctrl & 0x1F
        if size == 29:
            size, o = 29 + b[o], o + 1
        elif size == 30:
            size, o = 285 + int.from_bytes(b[o: o + 2], "big"), o + 2
        elif size == 31:
            size, o = 65821 + int.from_bytes(b[o: o + 3], "big"), o + 3
        if kind == 2:
            return b[o: o + size].decode("utf-8", "replace"), o + size
        if kind == 3:
            return struct.unpack(">d", b[o: o + 8])[0], o + 8
        if kind == 4:
            return bytes(b[o: o + size]), o + size
        if kind in (5, 6, 9, 10):
            return int.from_bytes(b[o: o + size], "big"), o + size
        if kind == 8:
            return int.from_bytes(b[o: o + size].rjust(4, b"\0"), "big", signed=True), o + size
        if kind == 7:
            out = {}
            for _ in range(size):
                k, o = self._decode(o, base)
                out[k], o = self._decode(o, base)
            return out, o
        if kind == 11:
            out = []
            for _ in range(size):
                v, o = self._decode(o, base)
                out.append(v)
            return out, o
        if kind == 14:
            return bool(size), o
        if kind == 15:
            return struct.unpack(">f", b[o: o + 4])[0], o + 4
        return None, o


_readers: dict[str, tuple[float, Reader]] = {}               # kind → (the file's mtime, its reader)
_lock = threading.Lock()


def folder(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "geo"


def _reader(cfg: sys_config.Config, kind: str) -> Reader | None:
    p = folder(cfg) / FILES[kind]
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    with _lock:
        if kind not in _readers or _readers[kind][0] != mtime:     # a new month's file: read again
            _readers[kind] = (mtime, Reader(p))
        return _readers[kind][1]


def _name(d: dict | None) -> str:
    names = (d or {}).get("names") or {}
    return names.get("it") or names.get("en") or ""


def locate(cfg: sys_config.Config, ip: str) -> dict:
    """{"ip", "public", "lat", "lon", "city", "region", "country", "asn", "org"} — the fields the databases have."""
    a = ipaddress.ip_address(ip)
    out = {"ip": ip, "public": a.is_global}
    if not a.is_global:
        return out
    city = _reader(cfg, "city")
    if city:
        d = city.get(ip) or {}
        loc = d.get("location") or {}
        out.update(lat=loc.get("latitude"), lon=loc.get("longitude"), city=_name(d.get("city")),
                   region=_name((d.get("subdivisions") or [{}])[0]), country=_name(d.get("country")),
                   cc=(d.get("country") or {}).get("iso_code", ""))
    asn = _reader(cfg, "asn")
    if asn:
        d = asn.get(ip) or {}
        out.update(asn=d.get("autonomous_system_number"), org=d.get("autonomous_system_organization", ""))
    return out


def status(cfg: sys_config.Config) -> dict:
    out = {"credit": CREDIT}
    for kind, name in FILES.items():
        p = folder(cfg) / name
        out[kind] = {"present": p.exists(), "updated": p.stat().st_mtime if p.exists() else None,
                     "mb": round(p.stat().st_size / 2**20, 1) if p.exists() else 0}
    return out


def update(cfg: sys_config.Config, get=None, month: str | None = None) -> dict:
    """This month's databases (or the last one's, early in a month), downloaded and swapped in."""
    import gzip
    import httpx
    from datetime import date, timedelta
    get = get or (lambda u: httpx.get(u, timeout=600, follow_redirects=True))
    d = folder(cfg)
    d.mkdir(parents=True, exist_ok=True)
    today = date.today()
    months = [month] if month else [today.strftime("%Y-%m"), (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")]
    done = {}
    for kind, name in FILES.items():
        for m in months:
            r = get(URL.format(kind=kind, month=m))
            if r.status_code == 200:
                tmp = d / (name + ".tmp")
                tmp.write_bytes(gzip.decompress(r.content))
                Reader(tmp)                                   # a file that reads, or nothing replaced
                tmp.replace(d / name)
                done[kind] = m
                break
    with _lock:
        _readers.clear()
    return {"updated": done, "at": time.time()}


def due(cfg: sys_config.Config, days: int = 30) -> bool:
    p = folder(cfg) / FILES["city"]
    return not p.exists() or time.time() - p.stat().st_mtime > days * 86400

