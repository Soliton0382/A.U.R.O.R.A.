# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "netintel": what the public registries say about an IP address (defence, not attack).

Only organisation-level network data: the network and the organisation it is assigned to, the
registry's country, the abuse contact for reports. Nothing is sent to the address itself.
"""
from __future__ import annotations

import ipaddress
import os
import socket

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

KEY = os.environ.get("AURORA_ABUSEIPDB_KEY", "")
server = MCPServer("netintel", version="1.0")


def _ip(ip: str) -> str:
    try:
        a = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise ToolError(f"not an IP address: {ip!r}")
    if not a.is_global:
        raise ToolError(f"{ip} is not a public address: it belongs to a local or reserved network")
    return str(a)


def _vcard(entity: dict) -> dict:
    out = {}
    for item in (entity.get("vcardArray") or [None, []])[1]:
        if item[0] in ("fn", "email") and item[3]:
            out[item[0]] = item[3]
    return out


@server.tool()
def rdap_ip(ip: str) -> str:
    """Registry data (RDAP) of a public IP: network name and range, organisation, country, abuse contact."""
    ip = _ip(ip)
    r = httpx.get(f"https://rdap.org/ip/{ip}", timeout=30, follow_redirects=True)
    if r.status_code != 200:
        raise ToolError(f"RDAP {r.status_code}")
    d = r.json()
    lines = [f"network: {d.get('name', '?')} {d.get('startAddress', '')}–{d.get('endAddress', '')}",
             f"registry country: {d.get('country', '?')}", f"type: {d.get('type', '?')}"]
    for e in d.get("entities", []):
        roles, card = e.get("roles", []), _vcard(e)
        if "registrant" in roles or "administrative" in roles:
            lines.append(f"organisation: {card.get('fn', e.get('handle', '?'))}")
        if "abuse" in roles and card.get("email"):
            lines.append(f"abuse contact: {card['email']}")
        for sub in e.get("entities", []):
            sc = _vcard(sub)
            if "abuse" in sub.get("roles", []) and sc.get("email"):
                lines.append(f"abuse contact: {sc['email']}")
    return "\n".join(dict.fromkeys(lines))


@server.tool()
def reverse_dns(ip: str) -> str:
    """The public DNS name of an IP address (PTR record), if any."""
    ip = _ip(ip)
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror):
        return "no reverse DNS name"


@server.tool()
def ip_reputation(ip: str) -> str:
    """Reports about an IP on AbuseIPDB in the last 90 days (needs AURORA_ABUSEIPDB_KEY)."""
    ip = _ip(ip)
    if not KEY:
        return "not measured: AURORA_ABUSEIPDB_KEY is empty"
    r = httpx.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": ip, "maxAgeInDays": 90},
                  headers={"Key": KEY, "Accept": "application/json"}, timeout=30)
    if r.status_code != 200:
        raise ToolError(f"AbuseIPDB {r.status_code}")
    d = r.json()["data"]
    return (f"abuse confidence {d.get('abuseConfidenceScore')}%, {d.get('totalReports')} reports from "
            f"{d.get('numDistinctUsers')} users, last {d.get('lastReportedAt')}; usage: {d.get('usageType')}; "
            f"ISP: {d.get('isp')}; domain: {d.get('domain')}; Tor: {d.get('isTor')}")


if __name__ == "__main__":
    server.run("stdio")
