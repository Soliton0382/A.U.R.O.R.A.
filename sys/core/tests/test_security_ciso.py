# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The security officer on the firewall (owner, 2026-10-07): documentation, audit, hunt, posture, planned changes.
Addresses are documentation or private test ranges, never the owner's."""
import re
import time

import pytest

from aurora import sec_audit, sec_defence, sec_fwapi, sec_fwconf, sec_fwdocs, sec_fwwrite, sec_hunt, sec_intel, \
    sec_playbook, sys_ethics


def _rule(name, src, dst, action="Accept", ips="None", log="Disable", services=(), src_nets=(), dst_nets=(), status="Enable"):
    return {"Name": name, "Status": status, "NetworkPolicy": {
        "Action": action, "LogTraffic": log, "IntrusionPrevention": ips,
        "SourceZones": {"Zone": list(src)} if src else "", "DestinationZones": {"Zone": list(dst)} if dst else "",
        "Services": {"Service": list(services)} if services else "",
        "SourceNetworks": {"Network": list(src_nets)} if src_nets else "",
        "DestinationNetworks": {"Network": list(dst_nets)} if dst_nets else ""}}


CONF = {
    "FirewallRule": [_rule("Blocks", [], [], "Reject", src_nets=["Aurora-Blocklist"]),
                     _rule("DNAT to media", ["WAN"], ["LAN"], services=["Media_Port"], dst_nets=["#Port7"]),
                     _rule("Out", ["LAN"], ["WAN"]), _rule("Old", ["LAN"], ["WAN"], status="Disable")],
    "NATRule": [{"Name": "DNAT to media", "Status": "Enable", "OriginalServices": {"Service": "Media_Port"}}],
    "Services": [{"Name": "Media_Port", "ServiceDetails": {"ServiceDetail": [{"DestinationPort": "32400", "Protocol": "TCP"}]}}],
    "IPSPolicy": [{"Name": "generalpolicy"}, {"Name": "WAN TO LAN"}, {"Name": "Media"}],
    "Zone": [{"Name": "WAN", "Type": "WAN", "ApplianceAccess": {"VPNServices": {"SSLVPN": "Enable"}}}],
    "ATP": [{"ThreatProtectionStatus": "Enable", "Policy": "Log and Drop"}],
    "AdminSettings": [{"LoginSecurity": {"BlockLogin": "Enable"}, "PasswordComplexitySettings": {"PasswordComplexityCheck": "Enable"}}],
    "SyslogServers": [{"Name": "Aurora", "ServerAddress": "10.0.0.5", "LogSettings": {"IPS": {"Signatures": "Enable"}, "ATP": {"ATRDestMatch": "Enable"}}}],
    "Interface": [{"Name": "Port1", "NetworkZone": "LAN", "IPAddress": "10.0.0.1", "Netmask": "255.255.255.0", "Status": "Connected"},
                  {"Name": "Port7", "NetworkZone": "WAN", "IPAddress": "192.168.1.2", "Netmask": "255.255.255.0", "Status": "Connected, 2500 Mbps"}],
    "IPHost": [], "IPHostGroup": [], "_errors": {},
}


# ---- configuration and audit --------------------------------------------------------------------------------------
def test_the_firewall_s_xml_becomes_dicts_and_an_entity_is_never_expanded():
    xml = ("<Response><Login><status>Authentication Successful</status></Login><FirewallRule><Name>R</Name><Status>Enable"
           "</Status><NetworkPolicy><Action>Accept</Action><SourceZones><Zone>WAN</Zone></SourceZones></NetworkPolicy>"
           "</FirewallRule></Response>")
    rule = sec_fwconf.parse(xml, "FirewallRule")[0]
    assert sec_fwconf.rule_view(rule)["src_zones"] == ["WAN"] and sec_fwconf.rule_view(rule)["action"] == "Accept"
    with pytest.raises(sec_fwconf.ConfigError):
        sec_fwconf.parse('<!DOCTYPE x [<!ENTITY a "aaaa">]><Response>&a;</Response>', "FirewallRule")


def test_an_entity_the_firewall_does_not_know_is_an_error_not_an_item():
    xml = ('<Response><CountryHostGroup><Status code="529">Input request module is Invalid</Status>'
           "</CountryHostGroup></Response>")
    with pytest.raises(sec_fwconf.ConfigError, match="529|Invalid"):
        sec_fwconf.parse(xml, "CountryHostGroup")


def test_a_service_published_without_ips_names_the_policy_that_exists_for_it(cfg):
    cfg.values.update(AURORA_FIREWALL_BLOCK_GROUP="Aurora-Blocklist")
    found = sec_audit.exposed(CONF)
    assert len(found) == 1 and found[0]["severity"] == "high" and found[0]["ports"] == ["TCP 32400"]
    assert "«Media»" in found[0]["fix"] and "tutta Internet" in found[0]["why"]


def test_the_blocking_rule_must_exist_and_come_first():
    assert sec_audit.blocklist(CONF, "Aurora-Blocklist") == []
    assert sec_audit.blocklist(CONF, "Other-Group")[0]["severity"] == "high"
    late = {**CONF, "FirewallRule": [CONF["FirewallRule"][1], CONF["FirewallRule"][0]]}
    assert sec_audit.blocklist(late, "Aurora-Blocklist")[0]["id"] == "blocklist_order"


def test_the_syslog_must_reach_aurora_with_its_threat_events():
    assert sec_audit.syslog(CONF, {"10.0.0.5"}) == []
    assert sec_audit.syslog(CONF, {"10.0.0.9"})[0]["severity"] == "high"


def test_an_entity_not_read_is_not_judged_absent():
    err = "the firewall refused the login"
    conf = {**CONF, "FirewallRule": [], "SyslogServers": [], "_errors": {"FirewallRule": err, "SyslogServers": err}}
    b = sec_audit.blocklist(conf, "Aurora-Blocklist")
    s = sec_audit.syslog(conf, {"10.0.0.5"})
    assert b[0]["severity"] == "medium" and b[0]["id"] == "unread:FirewallRule" and err in b[0]["why"]
    assert s[0]["severity"] == "medium" and s[0]["id"] == "unread:SyslogServers"
    out = sec_audit.text({"findings": b + s, "counts": {"high": 0, "medium": 2, "low": 0}, "errors": conf["_errors"]})
    assert out.count("motivo: " + err) == 1


def test_administration_from_the_internet_is_high():
    conf = {**CONF, "Zone": [{"Name": "WAN", "Type": "WAN", "ApplianceAccess": {"AdminServices": {"HTTPS": "Enable"}}}]}
    assert sec_audit.zones(conf)[0]["id"] == "admin_wan" and sec_audit.zones(conf)[0]["severity"] == "high"


# ---- hunt ---------------------------------------------------------------------------------------------------------
def _fw(src, dst, port, t, subtype="Allowed"):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(t))
    return {"log_type": "Firewall", "log_component": "Firewall Rule", "log_subtype": subtype, "src_ip": src,
            "dst_ip": dst, "dst_port": port, "timestamp": stamp}


def test_a_device_calling_out_every_five_minutes_is_a_beacon_unless_everyone_calls_it():
    h = sec_hunt.Hunt()
    t0 = 1_800_000_000
    for i in range(14):
        h.feed(_fw("10.0.0.20", "198.51.100.7", "8443", t0 + i * 300 + (i % 3)))
    found = h.beacons()
    assert len(found) == 1 and found[0]["detail"]["every_s"] in range(299, 302)
    for other in ("10.0.0.21", "10.0.0.22"):
        h.feed(_fw(other, "198.51.100.7", "8443", t0))
    assert h.beacons() == []                               # three devices call it: a service everyone uses


def test_a_device_touching_many_others_is_a_sweep():
    h = sec_hunt.Hunt(names={"10.0.0.30": "PC"})
    for i in range(20):
        h.feed(_fw("10.0.0.30", f"10.0.0.{100 + i}", "445", 1_800_000_000 + i * 5, "Denied"))
    s = h.sweeps()
    assert s and s[0]["severity"] == "medium" and "PC (10.0.0.30)" in s[0]["title"]   # a known device: medium


def test_greynoise_on_a_cloud_address_is_judged_a_false_positive_a_malware_feed_is_not():
    h = sec_hunt.Hunt(shared=lambda ip: "Google Cloud" if ip == "198.51.100.9" else "")
    for src in ("10.0.0.40", "10.0.0.41"):
        h.feed({"log_type": "ATP", "log_subtype": "Log destination match", "src_ip": src, "dst_ip": "198.51.100.9",
                "dst_port": "443", "threatfeed": "GreyNoise"})
    h.feed({"log_type": "ATP", "log_subtype": "Log destination match", "src_ip": "10.0.0.42", "dst_ip": "203.0.113.66",
            "dst_port": "8080", "threatfeed": "C2/Generic-A"})
    by_dst = {f["detail"]["dst"]: f for f in h.threats()}
    assert by_dst["198.51.100.9"]["severity"] == "low" and "Google Cloud" in by_dst["198.51.100.9"]["why"]
    assert by_dst["203.0.113.66"]["severity"] == "high"


def test_scanners_of_one_published_service_are_one_finding():
    h = sec_hunt.Hunt()
    for src in ("203.0.113.1", "203.0.113.2", "203.0.113.2"):
        h.feed({"log_type": "ATP", "log_subtype": "Log remote source match", "src_ip": src, "dst_ip": "10.0.0.21",
                "dst_port": "32400", "threatfeed": "GreyNoise", "src_country": "USA"})
    found = h.threats()
    assert len(found) == 1 and found[0]["detail"]["count"] == 3 and "2 indirizzi" in found[0]["title"]


def test_dubious_domains_and_the_firewall_s_dangerous_categories():
    assert sec_hunt.machine_made("xk3q9z7v2m8w4t.com") and not sec_hunt.machine_made("anthropic.com")
    h = sec_hunt.Hunt()
    h.feed({"log_type": "Content Filtering", "src_ip": "10.0.0.50", "dst_ip": "198.51.100.1", "domain": "bad.example",
            "http_category": "Malware Repository"})
    h.feed({"log_type": "Content Filtering", "src_ip": "10.0.0.51", "dst_ip": "198.51.100.2", "domain": "vpn.example",
            "http_category": "Anonymizers"})
    sev = {f["source"]: f["severity"] for f in h.domain_findings()}
    assert sev == {"10.0.0.50": "high", "10.0.0.51": "medium"}      # a VPN is a policy question, not a threat


def test_configuration_changes_and_logins_from_outside_are_told():
    h = sec_hunt.Hunt()
    h.feed({"log_type": "Event", "log_component": "GUI", "status": "Successful", "src_ip": "10.0.0.60",
            "message": "NAT rule 'DNAT to X' was added by 'admin' from '10.0.0.60' using 'GUI'"})
    h.feed({"log_type": "Event", "log_component": "GUI", "status": "Successful", "src_ip": "203.0.113.70",
            "user_name": "admin", "message": "Administrator 'admin' logged in successfully to Web Admin Console."})
    kinds = {f["kind"]: f for f in h.admin_findings()}
    assert kinds["admin_outside"]["severity"] == "high" and kinds["admin_changes"]["severity"] == "low"
    assert "«DNAT to X» added da admin" in kinds["admin_changes"]["why"]


def test_the_routine_tells_each_finding_once_a_day(cfg):
    f = [{"kind": "beacon", "source": "10.0.0.20", "severity": "medium", "title": "t", "why": "w", "fix": "x"}]
    assert sec_hunt.fresh(cfg, f) == f and sec_hunt.fresh(cfg, f) == []


# ---- the security officer's view ----------------------------------------------------------------------------------
def test_two_different_signals_on_one_device_make_a_suspect_with_its_playbook():
    findings = [{"kind": "beacon", "source": "10.0.0.20", "severity": "medium", "title": "beacon"}]
    incidents = [{"kind": "behaviour:new_country", "source": "10.0.0.20", "severity": "medium", "status": "open"}]
    g = sec_playbook.correlate(findings, incidents)[0]
    assert g["severity"] == "high" and g["scenario"] == "compromised"
    risks = sec_playbook.register({"findings": [{"severity": "high", "title": "Plex", "fix": "IPS"}]}, [g])
    assert [r["from"] for r in risks] == ["configurazione", "attività"]
    assert "quarantena" in sec_playbook.text([g], risks)


def test_the_owner_s_own_edits_do_not_make_their_phone_a_suspect_nor_a_false_positive_a_second_signal():
    findings = [{"kind": "admin_changes", "source": "10.0.0.77", "severity": "low", "title": "3 modifiche"},
                {"kind": "atp_out", "source": "10.0.0.77", "severity": "low", "title": "GreyNoise, falso positivo"},
                {"kind": "domain", "source": "10.0.0.77", "severity": "medium", "title": "una VPN"}]
    groups = {g["who"]: g for g in sec_playbook.correlate(findings, [])}
    assert groups["firewall"]["scenario"] == "" and groups["10.0.0.77"]["severity"] == "medium"
    assert groups["10.0.0.77"]["scenario"] == "check" and sec_playbook.register(None, list(groups.values())) == []


def test_a_shared_address_of_a_cdn_is_never_blocked_by_herself(cfg, monkeypatch):
    cfg.values.update(AURORA_DEFENCE_MODE="auto", AURORA_DEFENCE_MIN_SEVERITY="high", AURORA_DEFENCE_PROTECTED="",
                      AURORA_FIREWALL_API_URL="https://192.0.2.1:4444")
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: True)
    monkeypatch.setattr(sec_intel, "shared", lambda cfg, ip: "Cloudflare")
    ok, why = sec_defence.decide(cfg, {"id": "i", "kind": "ips_alert", "source": "45.33.32.156", "severity": "high"})
    assert not ok and "Cloudflare" in why


# ---- planned changes ----------------------------------------------------------------------------------------------
def test_a_publication_is_host_service_rule_after_the_blocks_and_dnat_and_says_the_router_in_front(cfg):
    cfg.values.update(AURORA_FIREWALL_BLOCK_GROUP="Aurora-Blocklist")
    p = sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443/tcp", "Italy", conf=CONF)
    assert [s["entity"] for s in p["steps"]] == ["IPHost", "Services", "FirewallRule", "NATRule"]
    assert all(s["name"].lower().startswith("aurora-") for s in p["steps"])
    rule = p["steps"][2]["xml"]
    assert "<After><Name>Blocks</Name></After>" in rule and "<IntrusionPrevention>WAN TO LAN</IntrusionPrevention>" in rule
    assert "<SourceNetworks><Network>Italy</Network></SourceNetworks>" in rule and "<LogTraffic>Enable</LogTraffic>" in rule
    assert "<TranslatedDestination>aurora-host-10.0.0.8</TranslatedDestination>" in p["steps"][3]["xml"]
    assert any("192.168.1.2" in n for n in p["notes"])


@pytest.mark.parametrize("ports", ["0", "70000", "443/icmp", "9-3", ""])
def test_a_wrong_port_is_refused(cfg, ports):
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwwrite.plan_publish(cfg, "X", "10.0.0.8", ports, conf=CONF)


def test_a_public_address_is_not_published_nor_put_in_quarantine(cfg):
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwwrite.plan_publish(cfg, "X", "45.33.32.156", "443", conf=CONF)
    cfg.values.update(AURORA_FIREWALL_API_URL="https://192.0.2.1:4444", AURORA_QUARANTINE_GROUP="Aurora-Quarantine")
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwwrite.plan_quarantine(cfg, "45.33.32.156", "x", conf=CONF)


class Firewall:
    """The firewall's API as a list of requests: each answered 200, or `refuse` (a substring) answered 500."""

    def __init__(self, refuse=None, read_back=True):
        self.calls, self.refuse, self.read_back = [], refuse, read_back

    def request(self, cfg, xml):
        self.calls.append(xml)
        entity = re.search(r"<(?:Set[^>]*|Remove|Get)><(\w+)", xml).group(1)
        code = "500" if self.refuse and self.refuse in xml else "200"
        if xml.startswith("<Get>"):
            names = re.findall(r"<Name>([^<]+)</Name>", " ".join(c for c in self.calls if c.startswith("<Set")))
            body = "".join(f"<{entity}><Name>{n}</Name></{entity}>" for n in names) if self.read_back else ""
            return f"<Response>{body}</Response>"
        return f'<Response><{entity} transactionid=""><Status code="{code}">done</Status></{entity}></Response>'


@pytest.fixture
def firewall(cfg, monkeypatch):
    cfg.values.update(AURORA_FIREWALL_WRITE=True, AURORA_FIREWALL_CONFIRM_S=10, AURORA_FIREWALL_BLOCK_GROUP="Aurora-Blocklist")
    fw = Firewall()
    monkeypatch.setattr(sec_fwapi, "request", fw.request)
    monkeypatch.setattr(sec_fwwrite.time, "sleep", lambda s: None)
    return fw


def test_a_change_is_applied_read_back_and_reverted_last_first(cfg, firewall):
    ch = sec_fwwrite.propose(cfg, sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443", conf=CONF))
    assert sec_fwwrite.apply(cfg, ch["id"])["status"] == "applied"
    firewall.calls.clear()
    assert sec_fwwrite.revert(cfg, ch["id"])["status"] == "reverted"
    removed = [re.search(r"<Remove><(\w+)>", c).group(1) for c in firewall.calls]
    assert removed == ["NATRule", "FirewallRule", "Services", "IPHost"]


def test_a_plan_not_wanted_is_discarded_and_never_applied(cfg, firewall):
    ch = sec_fwwrite.propose(cfg, sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443", conf=CONF))
    assert sec_fwwrite.discard(cfg, ch["id"])["status"] == "discarded"
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwwrite.apply(cfg, ch["id"])
    assert firewall.calls == []


def test_a_step_the_firewall_refuses_undoes_the_steps_done(cfg, firewall):
    firewall.refuse = "<NATRule>"
    ch = sec_fwwrite.apply(cfg, sec_fwwrite.propose(cfg, sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443", conf=CONF))["id"])
    assert ch["status"] == "undone" and "NATRule" in ch["problems"][0]
    assert [re.search(r"<Remove><(\w+)>", c).group(1) for c in firewall.calls if c.startswith("<Remove>")] == \
        ["FirewallRule", "Services", "IPHost"]


def test_a_change_that_does_not_read_back_is_undone(cfg, firewall, monkeypatch):
    firewall.read_back = False
    clock = iter(range(0, 10_000, 5))
    monkeypatch.setattr(sec_fwwrite.time, "time", lambda: next(clock))
    ch = sec_fwwrite.apply(cfg, sec_fwwrite.propose(cfg, sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443", conf=CONF))["id"])
    assert ch["status"] == "undone" and any("non si rilegge" in p for p in ch["problems"])


def test_writes_off_or_an_object_not_aurora_s_is_refused(cfg, firewall):
    bad = {"kind": "x", "title": "x", "why": "x", "check": [],
           "steps": [sec_fwwrite.step("FirewallRule", "Owner rule", "<Remove><FirewallRule><Name>Owner rule</Name></FirewallRule></Remove>", "", "x")]}
    with pytest.raises(sec_fwwrite.WriteError, match="non è un oggetto di Aurora"):
        sec_fwwrite.apply(cfg, sec_fwwrite.propose(cfg, bad)["id"])
    assert firewall.calls == []
    cfg.values.update(AURORA_FIREWALL_WRITE=False)
    ok = sec_fwwrite.propose(cfg, sec_fwwrite.plan_publish(cfg, "Cloud", "10.0.0.8", "443", conf=CONF))
    with pytest.raises(sec_fwwrite.WriteError, match="spente"):
        sec_fwwrite.apply(cfg, ok["id"])


def test_hardening_an_owner_s_rule_keeps_its_xml_as_the_undo(cfg, monkeypatch):
    before = ("<FirewallRule><Name>DNAT to media</Name><NetworkPolicy><Action>Accept</Action><LogTraffic>Disable"
              "</LogTraffic><IntrusionPrevention>None</IntrusionPrevention></NetworkPolicy></FirewallRule>")
    monkeypatch.setattr(sec_fwwrite, "raw_rule", lambda cfg, name: before)
    p = sec_fwwrite.plan_harden(cfg, "DNAT to media", "Media")
    st = p["steps"][0]
    assert st["owner_object"] and "<IntrusionPrevention>Media</IntrusionPrevention>" in st["xml"]
    assert "<LogTraffic>Enable</LogTraffic>" in st["xml"] and "<IntrusionPrevention>None</IntrusionPrevention>" in st["undo"]
    assert st["xml"].startswith('<Set operation="update"><FirewallRule><Name>')


# ---- documentation ------------------------------------------------------------------------------------------------
def test_an_api_page_keeps_its_sample_request_and_the_index_finds_it(cfg):
    raw = ("<html><title>Add NAT</title><body>Operation: Add NAT policy<br>Sample Configuration<xmp>\t<NATRule>"
           "<Name>Rule</Name></NATRule></xmp> Parameter TranslatedDestination: the translated destination."
           "<div class='companyRights'>© Copyright 2026 Sophos</div></body></html>")
    title, text, samples = sec_fwdocs.page_text(raw)
    assert samples == ["<NATRule><Name>Rule</Name></NATRule>"] and "<NATRule>" in text and "Copyright" not in text
    con = sec_fwdocs._db(cfg)
    sec_fwdocs.add_page(con, "api", "https://docs.example/api/PROTECT/Firewall/NATRule/operations/AddNATpolicy.html", raw)
    con.commit()
    con.close()
    hits = sec_fwdocs.search(cfg, "translated destination NAT")
    assert hits and hits[0]["kind"] == "api"
    assert sec_fwdocs.sample(cfg, "NATRule")[0]["xml"].startswith("<NATRule>")


def test_every_route_of_the_ciso_and_firewall_pages_is_the_admin_s():
    """A user (multi-user) sees neither the pages nor their data: each route depends on admin_only (owner, 2026-10-08).
    Read from the source: importing the API needs the installation's .env (the mirror has none)."""
    from pathlib import Path
    src = (Path(__file__).parents[1] / "aurora/api/security_ciso.py").read_text(encoding="utf-8")
    routes = re.findall(r"@router\.\w+\(([^\n]+)\)\n", src)
    assert len(routes) == 10 and all("dependencies=[Depends(admin_only)]" in r for r in routes)


def test_aurora_s_machine_doors_judged_from_what_listens(cfg):
    from aurora import sec_hostaudit
    cfg.values.update(AURORA_HONEYPOT_PORTS="2222", AURORA_SENTINEL_BIND="10.0.0.5:5514")
    raw = "\n".join([
        'tcp LISTEN 0 4096 127.0.0.1:9700 0.0.0.0:* users:(("python",pid=1,fd=7))',
        "tcp LISTEN 0 4096 *:443 *:*",
        'tcp LISTEN 0 5 0.0.0.0:2222 0.0.0.0:* users:(("python",pid=2,fd=5))',
        'udp UNCONN 0 0 10.0.0.5:5514 0.0.0.0:* users:(("python",pid=2,fd=4))',
        "tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:*",
        'udp UNCONN 0 0 *:41689 *:* users:(("cloudflared",pid=3,fd=4))',
        'tcp LISTEN 0 50 0.0.0.0:6379 0.0.0.0:* users:(("redis-server",pid=4,fd=6))',
        "udp UNCONN 0 0 0.0.0.0%virbr0:67 0.0.0.0:*"])
    socks = sec_hostaudit.sockets(raw)
    found = sec_hostaudit.findings(cfg, socks)
    kinds = {s["port"]: s["kind"] for s in socks}
    assert kinds == {"9700": "local", "443": "expected", "2222": "expected", "5514": "expected", "22": "exposed",
                     "41689": "client", "6379": "exposed", "67": "local"}
    assert [(f["severity"], f["port"]) for f in found] == [("medium", "6379"), ("low", "22")]


def test_the_security_plugin_gets_its_password_and_its_folder_inside_the_sandbox():
    """C195: inside the sandbox the firewall's password was the word "redacted" (a secret passes only when the manifest
    lists it in env) and the plugin's folder read-only: every firewall tool from the chat and the routines failed."""
    import json
    from pathlib import Path
    m = json.loads((Path(__file__).resolve().parents[2] / "plugins" / "security" / "plugin.json").read_text())
    assert "AURORA_FIREWALL_API_PASSWORD" in m["env"]
    assert m["sandbox"]["write"] == ["AURORA_SECURITY_DIR"]


def test_aurora_s_own_objects_on_the_firewall_are_not_new_devices():
    from aurora import sec_netmap
    old = {"hosts": [{"name": "nas", "type": "IP", "address": "10.0.0.2"}], "dhcp": []}
    new = {"hosts": old["hosts"] + [{"name": "aurora-block-203.0.113.9", "type": "IP", "address": "203.0.113.9"},
                                    {"name": "printer", "type": "IP", "address": "10.0.0.9"}], "dhcp": []}
    assert sec_netmap.diff(old, new)["new"] == ["printer (10.0.0.9)"]
