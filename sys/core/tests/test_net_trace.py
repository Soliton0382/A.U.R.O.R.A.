# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The visual traceroute (owner, 10 Oct): addresses placed offline (a MaxMind DB read by net_geo), hops streamed from
mtr as they answer, a place the round trip makes impossible marked as a registered seat."""
import ipaddress
import struct

import pytest

from aurora import net_geo as G
from aurora import net_trace as T


def _enc(v) -> bytes:
    """A tiny MaxMind DB data encoder: maps, strings, doubles, unsigned ints."""
    def head(kind, size):
        assert size < 285
        small, extra = (size, b"") if size < 29 else (29, bytes([size - 29]))
        return (bytes([(kind << 5) | small]) if kind < 8 else bytes([small, kind - 7])) + extra
    if isinstance(v, dict):
        return head(7, len(v)) + b"".join(_enc(k) + _enc(x) for k, x in v.items())
    if isinstance(v, str):
        b = v.encode()
        return head(2, len(b)) + b
    if isinstance(v, float):
        return head(3, 8) + struct.pack(">d", v)
    if isinstance(v, int):
        b = v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big")
        return head(6, len(b)) + b
    raise TypeError(v)


def mmdb(path, nets: dict, meta: dict):
    """An IPv4 tree (record size 24): each network → its record."""
    nodes = [[None, None]]
    datas, offsets = b"", {}
    for net, rec in nets.items():
        offsets[net] = len(datas)
        datas += _enc(rec)
    leaves = []
    for net in nets:
        n = ipaddress.ip_network(net)
        bits = format(int(n.network_address), "032b")[: n.prefixlen]
        node = 0
        for i, bit in enumerate(bits):
            side = int(bit)
            if i == len(bits) - 1:
                leaves.append((node, side, net))
            else:
                if nodes[node][side] is None:
                    nodes.append([None, None])
                    nodes[node][side] = len(nodes) - 1
                node = nodes[node][side]
    count = len(nodes)
    for node, side, net in leaves:
        nodes[node][side] = count + 16 + offsets[net]
    tree = b"".join((a if a is not None else count).to_bytes(3, "big") + (b if b is not None else count).to_bytes(3, "big")
                    for a, b in nodes)
    meta = {**meta, "node_count": count, "record_size": 24, "ip_version": 4}
    path.write_bytes(tree + b"\0" * 16 + datas + G.MARKER + _enc(meta))


@pytest.fixture
def geo(cfg):
    d = G.folder(cfg)
    d.mkdir(parents=True)
    mmdb(d / G.FILES["city"], {
        "8.8.8.0/24": {"city": {"names": {"en": "Mountain View"}}, "country": {"iso_code": "US", "names": {"en": "United States"}},
                       "location": {"latitude": 37.42, "longitude": -122.08}},
        "93.62.0.0/16": {"city": {"names": {"en": "Milan"}}, "country": {"iso_code": "IT", "names": {"en": "Italy"}},
                         "location": {"latitude": 45.49, "longitude": 9.16}}}, {"database_type": "test-city"})
    mmdb(d / G.FILES["asn"], {"8.8.8.0/24": {"autonomous_system_number": 15169, "autonomous_system_organization": "Google LLC"}},
         {"database_type": "test-asn"})
    G._readers.clear()
    return cfg


def test_an_address_is_placed_offline(geo):
    g = G.locate(geo, "8.8.8.8")
    assert (g["city"], g["cc"], round(g["lat"], 2), g["asn"], g["org"]) == ("Mountain View", "US", 37.42, 15169, "Google LLC")
    assert G.locate(geo, "93.62.1.1")["city"] == "Milan" and G.locate(geo, "9.9.9.9").get("city") in (None, "")
    assert G.locate(geo, "192.168.1.1") == {"ip": "192.168.1.1", "public": False}


def test_a_seat_the_round_trip_makes_impossible_is_marked():
    milan, mv = {"lat": 45.49, "lon": 9.16}, {"lat": 37.42, "lon": -122.08}
    assert T.plausible(milan, mv, 4.0) is False             # 9,500 km in 4 ms: not where the router is
    assert T.plausible(milan, mv, 160.0) is True
    assert T.plausible(None, mv, 4.0) is None


def test_hops_are_told_as_they_answer(geo, monkeypatch):
    raw = "x 0 1\nh 0 192.168.1.1\np 0 900 1\nh 1 93.62.5.5\np 1 3500 2\nh 2 8.8.8.8\np 2 4100 3\np 2 3900 4\n"

    class P:
        stdout = iter(raw.splitlines(keepends=True))

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0
    monkeypatch.setattr(T.shutil, "which", lambda b: "/usr/bin/mtr")
    monkeypatch.setattr(T.subprocess, "Popen", lambda *a, **k: P())
    events = []
    hops = T.trace(geo, "8.8.8.8", lambda e, d: events.append((e, d)))
    assert [e for e, _ in events if e in ("start", "hop", "done")] == ["start", "hop", "hop", "hop", "done"]
    assert [h["n"] for h in hops] == [1, 2, 3] and hops[2]["ms"] == 3.9
    assert hops[0]["geo"]["public"] is False and hops[2]["plausible"] is False and events[-1][1]["reached"]


def test_only_public_addresses_and_names_are_traced():
    with pytest.raises(T.TraceError):
        T.target_ip("192.168.1.10")
    with pytest.raises(T.TraceError):
        T.target_ip("8.8.8.8;ls")
    assert T.target_ip("8.8.8.8") == "8.8.8.8"
