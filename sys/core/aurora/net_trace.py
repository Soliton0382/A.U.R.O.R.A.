# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The visual traceroute (owner, 10 Oct: «dato un indirizzo IP ti faceva vedere sul mappamondo gli hop fino ad
arrivare alla posizione… direttamente dagli incident un tasto geolocalizza… con animazione sul globo terrestre»).

mtr in raw mode (its mtr-packet has CAP_NET_RAW: no root), read line by line: each hop is told as soon as it answers,
with its place from the offline databases (net_geo), then its round-trip times. Unlike netintel's lookups, a trace
SENDS packets towards the address (TTL-limited probes; the last ones reach it): the target sees this machine's
public address, as with any traceroute. Private hops (the home router, the ISP's CGNAT) have no place.
"""
from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
import threading
import time

from . import net_geo, sys_config

_busy = threading.Lock()
FIBRE_KM_PER_MS = 200.0       # light in fibre: ~2/3 c, about 200 km a millisecond one way


def km(a: dict, b: dict) -> float:
    """Great-circle distance between two places (haversine), in km."""
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def plausible(origin: dict | None, place: dict | None, rtt_ms: float | None) -> bool | None:
    """Can a reply come back from there in that time? The databases place a network at its registered seat (Google's
    routers in Mountain View, answering from Europe in 4 ms): farther than half the round trip lets light go in fibre
    (plus 300 km of slack for the routes' detours and the database's city) is not where the router is. None: unknown."""
    if not origin or not place or rtt_ms is None or origin.get("lat") is None or place.get("lat") is None:
        return None
    return km(origin, place) <= rtt_ms / 2 * FIBRE_KM_PER_MS + 300


class TraceError(Exception):
    pass


# the traces started from an incident's 📍 button: the firewall sees this machine reach a listed address and would open
# a new incident on the owner's own click (C265: three on 11 Oct, the dog chasing its tail)
OWN_WINDOW_S = 900            # after a trace ends, its alerts may still arrive (the firewall's log is minutes late)


def _own_file(cfg: sys_config.Config):
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "traces_from_incidents.json"


def _own(cfg: sys_config.Config) -> list[dict]:
    import json
    try:
        return json.loads(_own_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def remember(cfg: sys_config.Config, ip: str, incident: str, start: float, end: float | None = None) -> None:
    import json
    now = time.time()
    items = [t for t in _own(cfg) if (t.get("end") or t["start"]) > now - 86400 and not (t["ip"] == ip and t["start"] == start)]
    items.append({"ip": ip, "incident": incident, "start": start, "end": end})
    f = _own_file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(items), encoding="utf-8")


def own_trace(cfg: sys_config.Config, source: str, destination: str, at: float | None = None) -> str | None:
    """The incident whose 📍 button made this machine reach `destination` around now, when `source` is this machine;
    None otherwise (a trace typed by hand stays an incident: the owner's choice)."""
    if not destination or source not in local_addresses():
        return None
    at = at or time.time()
    for t in _own(cfg):
        if t["ip"] == destination and t["start"] - 60 <= at <= (t.get("end") or t["start"] + 120) + OWN_WINDOW_S:
            return t["incident"]
    return None


def local_addresses() -> set[str]:
    """This machine's own addresses (every interface)."""
    import psutil
    out = set()
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family in (socket.AF_INET, socket.AF_INET6):
                out.add(a.address.split("%")[0])
    return out


def target_ip(target: str) -> str:
    """A public address, or the first public address of a host name."""
    t = (target or "").strip()
    try:
        a = ipaddress.ip_address(t)
    except ValueError:
        if not t or len(t) > 253 or not all(c.isalnum() or c in ".-" for c in t):
            raise TraceError("an IP address or a host name") from None
        try:
            infos = socket.getaddrinfo(t, None)
        except socket.gaierror:
            raise TraceError(f"{t}: no such host") from None
        addrs = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]
        a = next((x for x in addrs if x.is_global), None)
        if a is None:
            raise TraceError(f"{t}: no public address")
    if not a.is_global:
        raise TraceError("a private address is not traced: it is in your own network")
    return str(a)


def trace(cfg: sys_config.Config, target: str, emit, cycles: int = 3, max_hops: int = 30, limit_s: float = 90,
          incident: str | None = None):
    """emit("start", {target, ip, geo}), emit("hop", {n, ip, geo}) at each new hop, emit("rtt", {n, ms}) and at the
    end emit("done", {hops: [...], reached, seconds}). One trace at a time on the machine."""
    if not shutil.which("mtr"):
        raise TraceError("mtr is not installed (sudo apt install mtr-tiny)")
    ip = target_ip(target)
    if not _busy.acquire(blocking=False):
        raise TraceError("a trace is already running: wait for it")
    t0 = time.time()
    hops: dict[int, dict] = {}
    if incident:                                               # from an incident's button: its alerts are ours
        remember(cfg, ip, incident, t0)
    try:
        emit("start", {"target": target, "ip": ip, "geo": net_geo.locate(cfg, ip)})
        p = subprocess.Popen(["mtr", "--raw", "-n", "-c", str(cycles), "-m", str(max_hops), ip],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for line in p.stdout:
                if time.time() - t0 > limit_s:
                    break
                parts = line.split()
                if len(parts) < 3 or parts[0] not in ("h", "p") or not parts[1].isdigit():
                    continue
                n = int(parts[1]) + 1
                if parts[0] == "h":
                    h = hops.setdefault(n, {"n": n, "ips": [], "rtt": []})
                    if parts[2] not in h["ips"]:
                        h["ips"].append(parts[2])
                        if len(h["ips"]) == 1:
                            h["geo"] = net_geo.locate(cfg, parts[2])
                            emit("hop", {"n": n, "ip": parts[2], "geo": h["geo"]})
                elif n in hops and parts[2].isdigit():
                    ms = int(parts[2]) / 1000
                    hops[n]["rtt"].append(ms)
                    emit("rtt", {"n": n, "ms": round(ms, 1)})
        finally:
            p.kill()
            p.wait(timeout=5)
        out = []
        origin = next((hops[n].get("geo") for n in sorted(hops) if (hops[n].get("geo") or {}).get("lat") is not None),
                      None)                                    # the first placed hop: the ISP, near home
        for n in sorted(hops):
            h = hops[n]
            r = h["rtt"]
            ms = round(min(r), 1) if r else None               # the fastest reply: the least queueing
            out.append({"n": n, "ips": h["ips"], "geo": h.get("geo"), "ms": ms, "lost": not r,
                        "plausible": plausible(origin, h.get("geo"), ms)})
        reached = any(ip in h["ips"] for h in out)
        if incident:
            remember(cfg, ip, incident, t0, time.time())
        emit("done", {"hops": out, "reached": reached, "seconds": round(time.time() - t0, 1),
                      "credit": net_geo.CREDIT})
        return out
    finally:
        _busy.release()
