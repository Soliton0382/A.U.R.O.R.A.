# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall drivers (ROADMAP 108, step 1): the dialect of before moved behind the interface, its XML byte for byte —
the strings below are what sec_fwapi and sec_fwwrite wrote before the move."""
import pytest

from aurora import fw_drivers, sec_fwapi, sec_fwwrite
from aurora.fw_drivers import sophos


def test_the_setting_chooses_the_driver_and_an_unknown_kind_is_said():
    assert fw_drivers.driver({"AURORA_FIREWALL_API_KIND": "sophos"}) is sophos and fw_drivers.driver() is sophos
    with pytest.raises(ValueError, match="one of"):
        fw_drivers.driver({"AURORA_FIREWALL_API_KIND": "other"})
    with pytest.raises(sec_fwapi.FirewallAPIError, match="one of"):
        sec_fwapi._driver({"AURORA_FIREWALL_API_KIND": "other"})


def test_the_blocking_group_is_written_as_before():
    assert sophos.get_group("Aurora Block") == "<Get><IPHostGroup><Name>Aurora Block</Name></IPHostGroup></Get>"
    assert sophos.add_host("aurora-block-198.51.100.7", "198.51.100.7", "scan <x>", "Aurora Block") == (
        '<Set operation="add"><IPHost><Name>aurora-block-198.51.100.7</Name><IPFamily>IPv4</IPFamily><Description>scan '
        '&lt;x&gt;</Description><HostType>IP</HostType><IPAddress>198.51.100.7</IPAddress><HostGroupList><HostGroup>'
        'Aurora Block</HostGroup></HostGroupList></IPHost></Set>')
    assert sophos.ungroup_host("aurora-block-198.51.100.7", "198.51.100.7") == (
        '<Set operation="update"><IPHost><Name>aurora-block-198.51.100.7</Name><IPFamily>IPv4</IPFamily><HostType>IP'
        '</HostType><IPAddress>198.51.100.7</IPAddress><HostGroupList></HostGroupList></IPHost></Set>')
    assert sophos.remove_host("aurora-block-1.2.3.4") == "<Remove><IPHost><Name>aurora-block-1.2.3.4</Name></IPHost></Remove>"


def test_the_objects_of_a_plan_are_written_as_before():
    assert sec_fwwrite.host_step("aurora-h", "10.0.0.5", ["G1", "G&2"])["xml"] == (
        '<Set operation="add"><IPHost><Name>aurora-h</Name><IPFamily>IPv4</IPFamily><HostType>IP</HostType><IPAddress>'
        '10.0.0.5</IPAddress><HostGroupList><HostGroup>G1</HostGroup><HostGroup>G&amp;2</HostGroup></HostGroupList>'
        '</IPHost></Set>')
    assert sec_fwwrite.rule_step("Aurora-r", "d", ["LAN"], ["WAN"], ["HTTPS"], ["n1"], ["n2"], "Accept", "", "Prev")["xml"] == (
        '<Set operation="add"><FirewallRule><Name>Aurora-r</Name><Description>d</Description><IPFamily>IPv4</IPFamily>'
        '<Status>Enable</Status><Position>After</Position><After><Name>Prev</Name></After><PolicyType>Network'
        '</PolicyType><NetworkPolicy><Action>Accept</Action><LogTraffic>Enable</LogTraffic><SkipLocalDestined>Disable'
        '</SkipLocalDestined><SourceZones><Zone>LAN</Zone></SourceZones><DestinationZones><Zone>WAN</Zone>'
        '</DestinationZones><Schedule>All The Time</Schedule><SourceNetworks><Network>n1</Network></SourceNetworks>'
        '<Services><Service>HTTPS</Service></Services><DestinationNetworks><Network>n2</Network></DestinationNetworks>'
        '<IntrusionPrevention>None</IntrusionPrevention></NetworkPolicy></FirewallRule></Set>')
    assert sec_fwwrite.dnat_step("Aurora-n", "y", "#Port2", "aurora-h", "Aurora-s", ["any1"])["xml"] == (
        '<Set operation="add"><NATRule><Name>Aurora-n</Name><Description>y</Description><IPFamily>IPv4</IPFamily>'
        '<Status>Enable</Status><Position>Top</Position><LinkedFirewallrule>None</LinkedFirewallrule>'
        '<OriginalSourceNetworks><Network>any1</Network></OriginalSourceNetworks><OriginalDestinationNetworks><Network>'
        '#Port2</Network></OriginalDestinationNetworks><TranslatedDestination>aurora-h</TranslatedDestination>'
        '<OriginalServices><Service>Aurora-s</Service></OriginalServices><TranslatedService>Original</TranslatedService>'
        '<OverrideInterfaceNATPolicy>Disable</OverrideInterfaceNATPolicy><TranslatedSource>Original</TranslatedSource>'
        '</NATRule></Set>')
    assert sec_fwwrite.service_step("Aurora-s", [("TCP", "443")])["undo"] == (
        "<Remove><Services><Name>Aurora-s</Name></Services></Remove>")


def test_an_owners_rule_is_hardened_in_its_own_xml():
    rule = ("<FirewallRule><Name>Web</Name><NetworkPolicy><LogTraffic>Disable</LogTraffic><IntrusionPrevention>None"
            "</IntrusionPrevention></NetworkPolicy></FirewallRule>")
    after = sophos.harden(rule, "lan_to_wan", True)
    assert "<IntrusionPrevention>lan_to_wan</IntrusionPrevention>" in after and "<LogTraffic>Enable</LogTraffic>" in after
    assert sophos.inner(after).startswith("<Name>Web</Name>") and sophos.find_rule(f"<x>{rule}</x>", "Web") == rule
