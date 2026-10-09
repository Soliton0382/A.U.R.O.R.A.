# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner, 10 Oct: the firewall's suggestions «non credo funzionino bene… prima di applicarlo dovrebbe almeno chiedermi
a quali paesi limitare l'accesso… la modifica sul firewall l'avevo già fatta ma sembra che non se ne sia accorto»."""
import xml.etree.ElementTree as ET

from aurora import sec_audit, sec_fwplan

RULE = """<FirewallRule><Name>DNAT to plex</Name><Description>DNAT wizard</Description><Position>after</Position>
<After><Name>Web</Name></After><Section>Local</Section><Status>Enable</Status>
<NetworkPolicy><Action>Accept</Action><SourceZones><Zone>WAN</Zone></SourceZones>
<Services><Service>Plex</Service></Services><DestinationZones><Zone>LAN</Zone></DestinationZones></NetworkPolicy></FirewallRule>"""


def test_an_origin_to_limit_is_asked_never_chosen(cfg):
    req = "Correggi questo rilievo dell'audit: … Suggerimento: limitare l'origine (paesi o indirizzi) se il servizio serve"
    out = sec_fwplan.plan(cfg, req, model=object(), conf={})            # the model is not even asked
    assert out["need"] == "origin" and "paesi" in out["questions"][0]


def test_an_update_keeps_the_rules_place_and_says_what_changes(cfg):
    model_xml = RULE.replace("<Position>after</Position>\n<After><Name>Web</Name></After>", "<Position>top</Position>") \
        .replace("DNAT wizard", "Limita a Italia").replace("<Section>Local</Section>", "<Section>Other</Section>") \
        .replace("<SourceZones><Zone>WAN</Zone></SourceZones>",
                 "<SourceZones><Zone>WAN</Zone></SourceZones><SourceNetworks><Network>Italy</Network></SourceNetworks>")
    new, old = ET.fromstring(model_xml), ET.fromstring(RULE)
    assert sorted(sec_fwplan.keep_placement(new, old)) == ["After", "Description", "Position", "Section"]
    assert sec_fwplan.diff(new, old) == [{"field": "NetworkPolicy/SourceNetworks/Network", "before": "", "after": "Italy"}]
    assert new.findtext("Position") == "after" and new.findtext("Description") == "DNAT wizard"


def test_an_origin_limited_on_the_nat_rule_is_seen():
    conf = {"FirewallRule": [{"Name": "DNAT to plex", "Status": "Enable", "PolicyType": "Network", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "WAN"}, "DestinationZones": {"Zone": "LAN"},
        "Services": {"Service": "Plex"}, "LogTraffic": "Enable", "IntrusionPrevention": "generalpolicy"}}],
            "NATRule": [{"Name": "DNAT to plex", "Status": "Enable", "OriginalSourceNetworks": {"Network": "Italy"},
                         "OriginalServices": {"Service": "Plex"}},
                        {"Name": "Loopback_NAT#1_DNAT to plex", "Status": "Enable", "OriginalServices": {"Service": "Plex"}}],
            "Services": []}
    f = sec_audit.exposed(conf)[0]
    assert f["origin"] == ["Italy"] and f["origin_from"] == "nat" and "aperta a tutta Internet" not in f["why"]
    assert "origine limitata a Italy dal NAT" in f["why"]
