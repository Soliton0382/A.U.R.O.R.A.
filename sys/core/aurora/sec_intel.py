# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Public lists of known attackers (owner, 2026-10-06: "security capabilities well beyond blocking an address").

Downloaded once a day (aurora-rem's daily round), kept in <STATUS>/security/intel.json, looked up for every incident
from an address on the internet: an address on a list makes the incident "high" and says which list and why — the
autonomous defence (sec_defence) then acts on it like on any high incident, within its limits.
Lists (free, public, no key): Spamhaus DROP (networks run by criminals, never to be routed), abuse.ch Feodo Tracker
(botnet command servers), FireHOL level1 (a union of the safest lists, few false positives). AURORA_INTEL_ENABLED off:
nothing is downloaded, nothing looked up.
"""
from __future__ import annotations

import bisect
import ipaddress
import json
import re
import time

import httpx

from . import sys_config

FEEDS = {
    "spamhaus_drop": ("https://www.spamhaus.org/drop/drop_v4.json", "Spamhaus DROP: rete gestita da criminali"),
    "feodo": ("https://feodotracker.abuse.ch/downloads/ipblocklist.txt", "abuse.ch Feodo: server di comando di una botnet"),
    "firehol_l1": ("https://iplists.firehol.org/files/firehol_level1.netset",
                   "FireHOL livello 1: attaccante noto"),
}
# Shared infrastructure (owner, 2026-10-07: Aurora blocked three Cloudflare addresses in one day): networks that serve
# millions of sites and the owner's own tunnel. Not attackers — kept apart from FEEDS: an address here is never blocked
# by Aurora alone (sec_defence) and is named in the hunt's judgement.
SHARED = {
    "Cloudflare": "https://www.cloudflare.com/ips-v4",
    "Google Cloud": "https://www.gstatic.com/ipranges/cloud.json",
    "Google": "https://www.gstatic.com/ipranges/goog.json",
}
_shared: dict = {"at": 0.0, "nets": []}
_NET = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)")
_cache: dict = {"at": 0.0, "ranges": [], "starts": []}


def _file(cfg: sys_config.Config):
    d = cfg.path("AURORA_STATUS_DIR") / "security"
    d.mkdir(parents=True, exist_ok=True)
    return d / "intel.json"


def parse(name: str, text: str) -> list[str]:
    nets = []
    if text.lstrip().startswith("{") and "prefixes" in text[:2000]:   # Google's ranges: {"prefixes": [{"ipv4Prefix"}]}
        try:
            return [p["ipv4Prefix"] for p in json.loads(text).get("prefixes", []) if p.get("ipv4Prefix")]
        except ValueError:
            return []
    if name == "spamhaus_drop":                       # one JSON object a line
        for line in text.splitlines():
            try:
                cidr = json.loads(line).get("cidr")
            except ValueError:
                continue
            if cidr:
                nets.append(cidr)
        return nets
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        m = _NET.match(line)
        if m:
            nets.append(m.group(1))
    return nets


def refresh(cfg: sys_config.Config) -> dict:
    """Download every list; a list that fails keeps yesterday's. Returns how many networks each one has."""
    try:
        old = json.loads(_file(cfg).read_text())
    except (OSError, ValueError):
        old = {"lists": {}}
    out = {"at": time.time(), "lists": dict(old.get("lists", {}))}
    for name, (url, _) in FEEDS.items():
        try:
            r = httpx.get(url, timeout=60, follow_redirects=True)
            r.raise_for_status()
            nets = parse(name, r.text)
            if nets:
                out["lists"][name] = {"at": time.time(), "nets": nets}
        except httpx.HTTPError:
            continue
    out["shared"] = dict(old.get("shared", {}))
    for name, url in SHARED.items():
        try:
            r = httpx.get(url, timeout=60, follow_redirects=True)
            r.raise_for_status()
            nets = parse(name, r.text)
            if nets:
                out["shared"][name] = nets
        except httpx.HTTPError:
            continue
    _file(cfg).write_text(json.dumps(out))
    _cache["at"] = 0.0
    _shared["at"] = 0.0
    return {n: len(v["nets"]) for n, v in out["lists"].items()}


def _ranges(cfg: sys_config.Config):
    """[(start, end, list name)] sorted, read again when the file changes (once a minute at most)."""
    if time.time() - _cache["at"] < 60:
        return _cache
    try:
        data = json.loads(_file(cfg).read_text())
    except (OSError, ValueError):
        data = {"lists": {}}
    ranges = []
    for name, v in data.get("lists", {}).items():
        for n in v.get("nets", []):
            try:
                net = ipaddress.ip_network(n, strict=False)
            except ValueError:
                continue
            ranges.append((int(net.network_address), int(net.broadcast_address), name))
    ranges.sort()
    _cache.update(at=time.time(), ranges=ranges, starts=[r[0] for r in ranges])
    return _cache


def lookup(cfg: sys_config.Config, ip: str) -> list[dict]:
    """The lists an address is on, with why (empty: on none, or not an address of the internet)."""
    if not cfg["AURORA_INTEL_ENABLED"]:
        return []
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return []
    if not a.is_global:
        return []
    c, x = _ranges(cfg), int(a)
    i = bisect.bisect_right(c["starts"], x)
    found, j = set(), i - 1
    while j >= 0 and i - j <= 64:                     # overlapping networks: look back a little
        s, e, name = c["ranges"][j]
        if s <= x <= e:
            found.add(name)
        j -= 1
    return [{"list": n, "why": FEEDS[n][1]} for n in sorted(found)]


def summary(cfg: sys_config.Config) -> dict:
    try:
        data = json.loads(_file(cfg).read_text())
    except (OSError, ValueError):
        return {"at": None, "lists": {}}
    return {"at": data.get("at"), "lists": {n: len(v.get("nets", [])) for n, v in data.get("lists", {}).items()}}


def shared(cfg: sys_config.Config, ip: str) -> str:
    """The provider whose shared network holds `ip` ("Cloudflare", "Google Cloud"…), or ""."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if time.time() - _shared["at"] > 60:
        try:
            data = json.loads(_file(cfg).read_text()).get("shared", {})
        except (OSError, ValueError):
            data = {}
        nets = []
        for name, items in data.items():
            for n in items:
                try:
                    nets.append((ipaddress.ip_network(n, strict=False), name))
                except ValueError:
                    continue
        _shared.update(at=time.time(), nets=nets)
    return next((name for net, name in _shared["nets"] if a.version == net.version and a in net), "")
