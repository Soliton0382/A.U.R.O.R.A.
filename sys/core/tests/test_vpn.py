# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 Aurora's own internet through a VPN (net_vpn, net_vpn_dns; owner, 29–30 Oct): an .ovpn adapted (only a client's
connection kept), the profiles tried in order, the rules for the service user alone, the kill switch, the domains kept
on the normal network, the DNS answers read. A made-up provider and addresses."""
import socket
import struct

import pytest

from aurora import net_vpn as V, net_vpn_dns as D

OVPN = """client
dev tun
proto udp
remote vpn-made-up.example.net 1195
remote-random
nobind
persist-key
ns-cert-type server
comp-lzo no
cipher AES-256-GCM
auth SHA512
auth-user-pass
route-method exe
redirect-gateway def1
up /tmp/evil.sh
script-security 3
verb 3
<ca>
-----BEGIN CERTIFICATE-----
MIIBmadeup
-----END CERTIFICATE-----
</ca>
<tls-auth>
-----BEGIN OpenVPN Static key V1-----
00ff
-----END OpenVPN Static key V1-----
</tls-auth>
"""


def test_an_ovpn_keeps_only_a_client_s_connection():
    kept, dropped = V.adapt(OVPN)
    assert "remote vpn-made-up.example.net 1195" in kept and "remote-cert-tls server" in kept and "ns-cert-type" not in kept
    for bad in ("up /tmp/evil.sh", "script-security 3", "redirect-gateway def1", "route-method exe", "auth-user-pass", "dev tun"):
        assert bad not in kept.split("\n"), bad
    assert "up /tmp/evil.sh" in dropped and "comp-lzo no" not in kept
    assert "<ca>" in kept and "MIIBmadeup" in kept and "</tls-auth>" in kept
    run = V.runtime_config(kept, __import__("pathlib").Path("/run/aurora-vpn"), '"py hook"')
    assert "route-nopull" not in run and "dns-updown disable" in run   # C476: the pushed DNS kept
    for line in ("dev avpn0", 'pull-filter ignore "route"', "mark 1809", "auth-user-pass /run/aurora-vpn/auth", 'up "py hook"'):
        assert line in run, line
    assert V.place_of(kept) == "vpn-made-up.example.net"
    with pytest.raises(ValueError):
        V.adapt(OVPN.replace("<ca>", "<script>").replace("</ca>", "</script>"))     # not a block of a connection
    with pytest.raises(ValueError):
        V.adapt("client\nremote x 1\n")                                               # nothing to check the server by
    with pytest.raises(ValueError):
        V.adapt("client\n<ca>\nx\n</ca>\n")                                           # which server?


def test_profiles_the_default_the_order_and_the_account(cfg):
    a = V.add(cfg, "Milano.ovpn", OVPN)
    b = V.add(cfg, "Zurigo.ovpn", OVPN)
    p = V.prefs(cfg)
    assert a["name"] == "Milano" and p["default"] == a["id"] and p["through"] == list(V.RECOMMENDED)
    raw = (V.folder(cfg) / f"{a['id']}.sealed").read_bytes()
    assert b"MIIBmadeup" not in raw and V.profile(cfg, a["id"]).startswith("client")
    V.set_default(cfg, b["id"])
    p = V.prefs(cfg)
    assert V.order(p) == [b["id"], a["id"]] and V.order(p, {b["id"]}) == [a["id"]] and V.order(p, {a["id"], b["id"]}) == []
    V.want(cfg, use=a["id"])
    assert V.order({**V.prefs(cfg), "use": a["id"]})[0] == a["id"] and V.prefs(cfg)["on"]
    V.set_account(cfg, "made-up-user", "pw")
    assert V.account(cfg) == "made-up-user\npw\n" and b"pw" not in (V.folder(cfg) / "account.sealed").read_bytes()
    with pytest.raises(ValueError):
        V.set_account(cfg, "a\nb", "c")
    V.remove(cfg, b["id"])
    assert V.prefs(cfg)["default"] == a["id"]


def test_the_rules_are_the_service_user_s_alone_and_the_kill_switch_never_leaks():
    rules = V.rules(997)
    assert ["ip", "-4", "rule", "add", "priority", "17110", "fwmark", "0x711", "lookup", "main"] in rules
    assert ["ip", "-4", "rule", "add", "priority", "17111", "uidrange", "997-997", "lookup", "main", "suppress_prefixlength", "0"] in rules
    assert ["ip", "-6", "rule", "add", "priority", "17113", "uidrange", "997-997", "lookup", "711"] in rules
    # C475: the home's other subnets (a NAS behind the firewall) by the main table, before the tunnel's
    assert ["ip", "-4", "rule", "add", "priority", "17112", "uidrange", "997-997", "to", "192.168.0.0/16", "lookup", "main"] in rules
    assert all(r[3] == "del" and len(r) == 6 for r in V.rules(997, False))
    # C477: the floor «unreachable» always there, under the tunnel's route (which goes with its device)
    for up in (True, False):
        floor = [r for r in V.table(up) if "unreachable" in r]
        assert [r[1] for r in floor] == ["-4", "-6"] and all(r[r.index("metric") + 1] == str(V.FLOOR_METRIC) for r in floor)
    assert ["ip", "-4", "route", "replace", "default", "dev", "avpn0", "metric", "10", "table", "711"] in V.table(True)
    assert ["ip", "-4", "route", "del", "default", "dev", "avpn0", "metric", "10", "table", "711"] in V.table(False)
    nft = V.nft_exclusions(["aurora-tunnel.service"])
    assert 'socket cgroupv2 level 2 "system.slice/aurora-tunnel.service" meta mark set 0x711' in nft and "@split4" in nft
    assert V.nft_split([("203.0.113.9", 5)])[0][-1] == "{ 203.0.113.9 timeout 60s }"


def test_what_passes_the_dns_options_and_back_to_the_recommended(cfg):
    cfg.values["AURORA_DOMAIN"] = "aurora.example.org"
    V.set_through(cfg, ["aurora-api.service", "aurora-tunnel.service"])
    p = V.prefs(cfg)
    assert "aurora-harvester.service" in V.bypass(p) and "aurora-tunnel.service" not in V.bypass(p)
    with pytest.raises(ValueError):
        V.set_through(cfg, ["sshd.service"])
    with pytest.raises(ValueError):
        V.set_options(cfg, dns="custom")                                  # no servers given
    V.set_options(cfg, dns="custom", dns_servers=["9.9.9.9"], killswitch=False)
    p = V.prefs(cfg)
    assert V.upstream(p, ["10.8.0.1"]) == ["9.9.9.9"] and not p["killswitch"]
    with pytest.raises(ValueError):
        V.set_options(cfg, dns_servers=["2001:db8::1"])
    V.set_split(cfg, ["*.Cugini.example.com", "cugini.example.com"])
    assert V.prefs(cfg)["split"] == ["cugini.example.com"]
    with pytest.raises(ValueError):
        V.set_split(cfg, ["not a domain"])
    V.recommended(cfg)
    p = V.prefs(cfg)
    assert p["through"] == list(V.RECOMMENDED) and p["killswitch"] and p["dns"] == "provider"
    assert p["split"] == ["cugini.example.com", "example.org"] and V.upstream(p, ["10.8.0.1"]) == ["10.8.0.1"]


def _answer(name: str, ips: list[str]) -> bytes:
    q = b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00" + struct.pack("!HH", 1, 1)
    head = struct.pack("!HHHHHH", 7, 0x8180, 1, len(ips), 0, 0)
    ans = b"".join(b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 120, 4) + socket.inet_aton(ip) for ip in ips)
    return head + q + ans


def test_the_resolver_tells_the_kept_domains_and_reads_their_addresses():
    pkt = _answer("panel.cugini.example.com", ["192.168.1.20", "9.9.9.9"])
    assert D.qname(pkt) == "panel.cugini.example.com"
    assert D.addresses(pkt) == [("192.168.1.20", 120), ("9.9.9.9", 120)]
    assert D.split("panel.cugini.example.com", ["cugini.example.com"]) and D.split("cugini.example.com.", ["cugini.example.com"])
    assert not D.split("notcugini.example.com", ["cugini.example.com"])
    assert [a for a, _ in D.addresses(pkt) if D.public(a)] == ["9.9.9.9"]                # the private one: the LAN already
    assert not D.public("192.168.1.20") and D.public("8.8.8.8")
    assert D.addresses(b"\x00" * 5) == [] and D.qname(b"\x00" * 12 + b"\x05ab") == ""


def test_the_forwarder_sends_a_kept_name_home_and_any_other_through_the_tunnel(monkeypatch):
    import threading
    import time

    def fake_dns(answer_ips):                                   # a made-up upstream on a free port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        asked = []

        def serve():
            while True:
                data, who = s.recvfrom(4096)
                asked.append(D.qname(data))
                s.sendto(_answer(D.qname(data), answer_ips), who)
        threading.Thread(target=serve, daemon=True).start()
        return s.getsockname(), asked
    home, home_asked = fake_dns(["192.168.1.20", "9.9.9.9"])
    tunnel, tunnel_asked = fake_dns(["8.8.4.4"])
    monkeypatch.setattr(D, "MACHINE", home)
    monkeypatch.setattr(D, "ADDRESS", ("127.0.0.1", 0))
    kept = []
    f = D.Forwarder(lambda: ["cugini.example.com"], lambda: ["127.0.0.1"], kept.extend)
    f.start()
    port = f.sock.getsockname()[1]
    real_one = f._one

    def one(data, client):                                      # the tunnel's DNS at its made-up port
        if not D.split(D.qname(data), ["cugini.example.com"]):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as up:
                up.sendto(data, tunnel)
                f.sock.sendto(up.recvfrom(4096)[0], client)
            return
        real_one(data, client)
    f._one = one
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
        c.settimeout(3)
        for name in ("panel.cugini.example.com", "news.example.net"):
            c.sendto(_answer(name, [])[:12 + len(name) + 2 + 4], ("127.0.0.1", port))
            assert D.qname(c.recvfrom(4096)[0]) == name
    time.sleep(.1)
    assert home_asked == ["panel.cugini.example.com"] and tunnel_asked == ["news.example.net"]
    assert kept == [("9.9.9.9", 120)]                           # the public address of a kept name: the normal line


def test_keepalive_the_reset_timer_and_the_traffic(cfg):
    kept, _ = V.adapt(OVPN)
    from pathlib import Path
    run = V.runtime_config(kept, Path("/run/aurora-vpn"), "h")
    assert "keepalive 10 60" in run and "status /run/aurora-vpn/status 10" in run
    own, _ = V.adapt(OVPN.replace("verb 3", "verb 3\nkeepalive 5 30"))
    assert V.runtime_config(own, Path("/run/aurora-vpn"), "h").count("keepalive") == 1     # the profile's own holds
    assert V.prefs(cfg)["reset_h"] == 2                                                      # owner, 30 Oct: every 2 h
    V.set_options(cfg, reset_h=0)
    assert V.prefs(cfg)["reset_h"] == 0
    for bad in (49, -1, "x"):
        with pytest.raises(ValueError):
            V.set_options(cfg, reset_h=bad)
    status = "OpenVPN STATISTICS\nUpdated,2026-10-30 18:00:00\nTUN/TAP read bytes,100\nTCP/UDP read bytes,52345\nTCP/UDP write bytes,1200\nEND\n"
    assert V.traffic(status) == {"bytes_in": 52345, "bytes_out": 1200} and V.traffic("") == {}


def test_the_rules_are_reconciled_without_a_gap():
    """30 Oct: the unit restarted deleted every rule and added it again — for an instant Aurora's traffic took the
    normal line. Now only what is missing is added and only what is not wanted deleted."""
    want = V.rules(997)
    present = {"-4": [{"priority": 17110, "src": "all", "fwmark": "0x711", "table": "main"},
                      {"priority": 17112, "src": "all", "uid_start": 997, "uid_end": 997, "table": "711"},  # an old layout
                      {"priority": 17113, "src": "all", "uid_start": 997, "uid_end": 997, "table": "711"}],
               "-6": []}
    adds, dels = V.reconcile(997, present)
    assert ["ip", "-4", "rule", "add", "priority", "17110", "fwmark", "0x711", "lookup", "main"] not in adds
    assert ["ip", "-4", "rule", "add", "priority", "17113", "uidrange", "997-997", "lookup", "711"] not in adds
    assert len(adds) == len(want) - 2
    assert dels == [["ip", "-4", "rule", "del", "priority", "17112", "uidrange", "997-997", "lookup", "711"]]
    assert V.reconcile(997, {"-4": [], "-6": []})[0] == want and V.reconcile(997, {"-4": [], "-6": []})[1] == []
