# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The network as the firewall sees it (owner, 2026-10-06): parsed, sealed, compared, names for the incidents."""
import xml.etree.ElementTree as ET

from aurora import sec_netmap as N

XML = """<Response><IPHost><Name>NAS</Name><IPFamily>IPv4</IPFamily><HostType>IP</HostType><IPAddress>192.0.2.10</IPAddress>
<HostGroupList><HostGroup>Server</HostGroup></HostGroupList></IPHost>
<IPHost><Name>LAN_net</Name><HostType>Network</HostType><IPAddress>192.0.2.0</IPAddress><Subnet>255.255.255.0</Subnet></IPHost>
<IPHost><Name>aurora-block-198.51.100.7</Name><HostType>IP</HostType><IPAddress>198.51.100.7</IPAddress></IPHost>
<IPHostGroup><Name>Server</Name><HostList><Host>NAS</Host></HostList></IPHostGroup>
<Interface><Name>Port1</Name><Hardware>Port1</Hardware><IPAddress>192.0.2.1</IPAddress><Netmask>255.255.255.0</Netmask>
<NetworkZone>LAN</NetworkZone><InterfaceStatus>ON</InterfaceStatus></Interface>
<Zone><Name>LAN</Name></Zone>
<DHCPServer><Name>Default</Name><Status>1</Status><Interface>Port1</Interface><IPLease><IP>192.0.2.100-192.0.2.200</IP></IPLease>
<StaticLease><Lease><HostName>TV_SALA</HostName><MACAddress>00:00:5e:00:53:01</MACAddress><IPAddress>192.0.2.20</IPAddress></Lease></StaticLease></DHCPServer>
</Response>"""


def raw(xml=XML):
    root = ET.fromstring(xml)
    return {e: [x for x in root.iter(e)] for e in N.ENTITIES}


def test_parsed_compared_named(cfg, monkeypatch):
    m = N.parse(raw())
    assert N.summary(m)["devices"] == 2 and N.summary(m)["reserved"] == 1 and m["hosts"][1]["address"] == "192.0.2.0/255.255.255.0"
    assert N.diff(None, m)["first"]
    later = N.parse(raw(XML.replace("192.0.2.10", "192.0.2.11").replace("TV_SALA", "TV_CUCINA")))
    d = N.diff(m, later)
    assert d["moved"] == ["NAS: 192.0.2.10 → 192.0.2.11"] and d["new"] == ["TV_CUCINA (DHCP) (192.0.2.20)"]
    assert d["gone"] == ["TV_SALA (DHCP) (192.0.2.20)"]
    assert "🆕 Nuovi: TV_CUCINA" in N.changes_text(d) and N.changes_text(N.diff(m, m)) == ""
    monkeypatch.setattr(N, "_get", lambda cfg, e: raw()[e])
    r = N.refresh(cfg)
    assert r["changes"]["first"] and (N._dir(cfg) / "netmap.sealed").exists()
    assert b"NAS" not in (N._dir(cfg) / "netmap.sealed").read_bytes()                  # sealed
    assert N.label(cfg, "192.0.2.10") == "NAS (192.0.2.10)" and N.label(cfg, "192.0.2.20") == "TV_SALA (192.0.2.20)"
    assert N.label(cfg, "198.51.100.7") == "198.51.100.7"                                  # Aurora's own blocks are not names
    assert any("interfaccia Port1" in x for x in N.find(N.load(cfg), "192.0.2.55"))
    assert N.find(N.load(cfg), "tv_sala")[0].startswith("- TV_SALA (192.0.2.20)")
    assert "Port1" in N.text(N.load(cfg))


def test_the_drawing_puts_each_device_on_its_interface():
    g = N.graph(N.parse(raw()))
    lan = g["interfaces"][0]
    assert lan["name"] == "Port1" and lan["network"] == "192.0.2.0/24" and lan["zone"] == "LAN"
    assert [(d["name"], d["ip"], d["kind"]) for d in lan["devices"]] == [("NAS", "192.0.2.10", "host"), ("TV_SALA", "192.0.2.20", "dhcp")]
    assert g["other"] == []                                     # Aurora's blocks are not devices
    assert N.graph(None)["interfaces"] == []
