# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Sophos Firewall dialect (docs.sophos.com, SFOS 21.0–22.0, "API" and "Post an API request"): an HTTPS POST to
<AURORA_FIREWALL_API_URL>/webconsole/APIController with the form field "reqxml" holding
<Request><Login><Username/><Password/></Login> ... </Request>. No APIVersion: the firewall then answers with its own
(an example's "1905.2" was refused with 529 "There is no API Version", C131). API access is off by default on the
firewall: the owner turns it on and allows Aurora's address. Moved here from sec_fwapi and sec_fwwrite (ROADMAP 108,
step 1): the same XML byte for byte."""
from __future__ import annotations

import re
from xml.sax.saxutils import escape

import httpx


# ---- the call -------------------------------------------------------------------------------------------------------
def request(cfg, body: str) -> str:
    """One API call; returns the firewall's XML answer. FirewallAPIError when the login or the call is refused."""
    from ..sec_fwapi import FirewallAPIError, _one_at_a_time, base_url
    xml = (f'<Request><Login><Username>{escape(str(cfg["AURORA_FIREWALL_API_USER"]))}</Username>'
           f'<Password>{escape(str(cfg["AURORA_FIREWALL_API_PASSWORD"]))}</Password></Login>{body}</Request>')
    url = base_url(cfg) + "/webconsole/APIController"
    try:
        with _one_at_a_time(cfg):
            r = httpx.post(url, files={"reqxml": (None, xml)}, timeout=30, verify=bool(cfg["AURORA_FIREWALL_VERIFY_TLS"]))
    except httpx.HTTPError as e:
        raise FirewallAPIError(f"the firewall does not answer: {e}") from None
    text = r.text
    if re.search(r"<Login>\s*<status>\s*Authentication Failure", text, re.I) or "Authentication Failure" in text:
        raise FirewallAPIError("the firewall refused the login (user, password, or Aurora's address not allowed for the API)")
    if r.status_code != 200:
        raise FirewallAPIError(f"HTTP {r.status_code}: {text[:200]}")
    top = re.search(r"<Response[^>]*>\s*<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    if top and top.group(1) != "200":                     # the firewall refused the whole request (C131)
        raise FirewallAPIError(f"the firewall answered {top.group(1)}: {top.group(2).strip()[:200]}")
    if "Authentication Successful" not in text:
        raise FirewallAPIError(f"no login in the firewall's answer: {re.sub(chr(10), ' ', text)[:200]}")
    return text


def status(text: str, entity: str) -> tuple[str, str]:
    m = re.search(rf"<{entity}[^>]*>.*?<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", text[:200])


def step_status(text: str, entity: str) -> tuple[str, str]:
    """The status of a plan's step: right after the object's tag, nothing when absent."""
    m = re.search(rf"<{entity}[^>]*>\s*<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", "")


def ok_codes(op: str) -> tuple[str, ...]:
    return ("200", "502", "503") if op == "add_host" else ("200",)    # 502/503: the host is there already


READ_ONLY_HINT = (" — l'utente API di Aurora sul firewall ha solo la lettura: nel Sophos, Amministrazione → Profili di "
                  "dispositivo, dagli lettura e scrittura su Regole e policy e su Oggetti di sistema; poi riprova "
                  "(il 9 ottobre: due modifiche annullate così)")


def read_only(code: str, msg: str) -> bool:
    return str(code) == "599" or "privilege" in msg.lower()


def has_group(text: str, name: str) -> bool:
    return f"<Name>{name}</Name>" in text


# ---- the blocking group ---------------------------------------------------------------------------------------------
def get_group(name: str) -> str:
    return f"<Get><IPHostGroup><Name>{escape(name)}</Name></IPHostGroup></Get>"


def add_group(name: str) -> str:
    return (f'<Set operation="add"><IPHostGroup><Name>{escape(name)}</Name><IPFamily>IPv4</IPFamily>'
            f"<Description>Aurora: addresses the owner blocked</Description></IPHostGroup></Set>")


def add_host(name: str, ip: str, desc: str, group: str) -> str:
    return (f'<Set operation="add"><IPHost><Name>{name}</Name><IPFamily>IPv4</IPFamily>'
            f"<Description>{escape(desc)}</Description><HostType>IP</HostType>"
            f"<IPAddress>{ip}</IPAddress><HostGroupList><HostGroup>{escape(group)}</HostGroup></HostGroupList>"
            "</IPHost></Set>")


def ungroup_host(name: str, ip: str, group: str = "") -> str:      # the group: for a dialect that needs it
    return (f'<Set operation="update"><IPHost><Name>{name}</Name><IPFamily>IPv4</IPFamily>'
            f"<HostType>IP</HostType><IPAddress>{ip}</IPAddress><HostGroupList></HostGroupList></IPHost></Set>")


def remove_host(name: str) -> str:
    return f"<Remove><IPHost><Name>{name}</Name></IPHost></Remove>"


# ---- the objects of a plan ------------------------------------------------------------------------------------------
def x(tag: str, value) -> str:
    if isinstance(value, list):
        return "".join(x(tag, v) for v in value)
    return f"<{tag}>{escape(str(value))}</{tag}>"


def set_(entity: str, body: str, op: str = "add") -> str:
    return f'<Set operation="{op}"><{entity}>{body}</{entity}></Set>'


def remove(entity: str, name: str) -> str:
    return f"<Remove><{entity}><Name>{escape(name)}</Name></{entity}></Remove>"


def host(name: str, ip: str, groups: list[str] | None = None) -> str:
    return (x("Name", name) + "<IPFamily>IPv4</IPFamily><HostType>IP</HostType>" + x("IPAddress", ip)
            + ("<HostGroupList>" + x("HostGroup", groups) + "</HostGroupList>" if groups else ""))


def release(name: str, ip: str) -> str:
    return (x("Name", name) + "<IPFamily>IPv4</IPFamily><HostType>IP</HostType>" + x("IPAddress", ip)
            + "<HostGroupList></HostGroupList>")


def group(name: str, desc: str) -> str:
    return x("Name", name) + f"<Description>{desc}</Description><IPFamily>IPv4</IPFamily>"


def service(name: str, ports: list[tuple[str, str]]) -> str:
    details = "".join(f"<ServiceDetail><SourcePort>1:65535</SourcePort>{x('DestinationPort', p)}{x('Protocol', proto)}"
                      "</ServiceDetail>" for proto, p in ports)
    return x("Name", name) + "<Type>TCPorUDP</Type><ServiceDetails>" + details + "</ServiceDetails>"


def rule(name: str, desc: str, src_zones: list[str], dst_zones: list[str], services: list[str],
         src_nets: list[str], dst_nets: list[str], action: str, ips: str, after: str | None) -> str:
    pos = f"<Position>After</Position><After>{x('Name', after)}</After>" if after else "<Position>Top</Position>"
    pol = (x("Action", action) + "<LogTraffic>Enable</LogTraffic><SkipLocalDestined>Disable</SkipLocalDestined>"
           + ("<SourceZones>" + x("Zone", src_zones) + "</SourceZones>" if src_zones else "")
           + ("<DestinationZones>" + x("Zone", dst_zones) + "</DestinationZones>" if dst_zones else "")
           + "<Schedule>All The Time</Schedule>"
           + ("<SourceNetworks>" + x("Network", src_nets) + "</SourceNetworks>" if src_nets else "")
           + ("<Services>" + x("Service", services) + "</Services>" if services else "")
           + ("<DestinationNetworks>" + x("Network", dst_nets) + "</DestinationNetworks>" if dst_nets else "")
           + x("IntrusionPrevention", ips or "None"))
    return (x("Name", name) + x("Description", desc[:250]) + "<IPFamily>IPv4</IPFamily><Status>Enable</Status>" + pos
            + "<PolicyType>Network</PolicyType><NetworkPolicy>" + pol + "</NetworkPolicy>")


def dnat(name: str, desc: str, wan: str, host_name: str, service_name: str, sources: list[str]) -> str:
    return (x("Name", name) + x("Description", desc[:250]) + "<IPFamily>IPv4</IPFamily><Status>Enable</Status>"
            "<Position>Top</Position><LinkedFirewallrule>None</LinkedFirewallrule>"
            + ("<OriginalSourceNetworks>" + x("Network", sources) + "</OriginalSourceNetworks>" if sources else "")
            + "<OriginalDestinationNetworks>" + x("Network", wan) + "</OriginalDestinationNetworks>"
            + x("TranslatedDestination", host_name) + "<OriginalServices>" + x("Service", service_name) + "</OriginalServices>"
            "<TranslatedService>Original</TranslatedService><OverrideInterfaceNATPolicy>Disable</OverrideInterfaceNATPolicy>"
            "<TranslatedSource>Original</TranslatedSource>")


# ---- an owner's rule ------------------------------------------------------------------------------------------------
def get_rules() -> str:
    return "<Get><FirewallRule/></Get>"


def find_rule(text: str, name: str) -> str | None:
    m = re.search(rf"<FirewallRule[^>]*>(?:(?!</FirewallRule>).)*?<Name>{re.escape(escape(name))}</Name>.*?</FirewallRule>", text, re.S)
    return re.sub(r"<FirewallRule[^>]*>", "<FirewallRule>", m.group(0), count=1) if m else None


def network_rule(before: str) -> bool:
    return "<NetworkPolicy>" in before


def harden(before: str, ips: str, log: bool) -> str:
    after = re.sub(r"<IntrusionPrevention>[^<]*</IntrusionPrevention>", f"<IntrusionPrevention>{escape(ips)}</IntrusionPrevention>", before)
    if "<IntrusionPrevention>" not in after:
        after = after.replace("</NetworkPolicy>", f"<IntrusionPrevention>{escape(ips)}</IntrusionPrevention></NetworkPolicy>")
    if log:
        after = re.sub(r"<LogTraffic>[^<]*</LogTraffic>", "<LogTraffic>Enable</LogTraffic>", after)
    return after


def inner(rule_xml: str) -> str:
    """A rule's XML without its outer tag: the body of a Set."""
    return rule_xml[len("<FirewallRule>"):-len("</FirewallRule>")]
