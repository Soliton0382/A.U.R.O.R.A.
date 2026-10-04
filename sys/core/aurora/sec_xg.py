# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Defence on the Sophos firewall through its XML API (owner, 2026-10-04) — only on the owner's click.

The API (docs.sophos.com, Sophos Firewall 21.0, "API" and "Post an API request"): an HTTPS POST to
<AURORA_XG_API_URL>/webconsole/APIController with the form field "reqxml" holding
<Request APIVersion=...><Login><Username/><Password/></Login> ... </Request>. API access is off by default on the
firewall: the owner turns it on and allows Aurora's address (Backup & firmware → API).

What Aurora does, and nothing else: an IP host "aurora-block-<address>" (IPHost: Name, IPFamily, HostType IP,
IPAddress, HostGroupList/HostGroup) in the group AURORA_XG_BLOCK_GROUP (IPHostGroup), and its removal. The group
must be used by a firewall rule that drops, made once by the owner on the firewall: Aurora never writes rules.
Never blocked: loopback, link-local, multicast, the firewall itself, this machine's own addresses.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx

from . import sys_config

API_VERSION = "1905.2"          # the version in the documentation's own example; the firewall answers with its own


class XGError(Exception):
    pass


def configured(cfg: sys_config.Config) -> bool:
    return bool(str(cfg["AURORA_XG_API_URL"] or "").strip() and cfg["AURORA_XG_API_USER"] and cfg["AURORA_XG_API_PASSWORD"])


def _own_addresses() -> set[str]:
    out = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            out.add(info[4][0])
    except OSError:
        pass
    return out


def blockable(cfg: sys_config.Config, ip: str) -> str:
    """The address as the firewall takes it; XGError for one never to be blocked."""
    try:
        a = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise XGError(f"not an IP address: {ip!r}") from None
    if a.version != 4:
        raise XGError("IPv6 is not handled yet")
    if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified or a.is_reserved:
        raise XGError(f"{a} is never blocked")
    fw = urlparse(str(cfg["AURORA_XG_API_URL"])).hostname or ""
    if str(a) == fw or str(a) in _own_addresses():
        raise XGError(f"{a} is the firewall or this machine: never blocked")
    return str(a)


def request(cfg: sys_config.Config, body: str) -> str:
    """One API call; returns the firewall's XML answer. XGError when the login or the call is refused."""
    if not configured(cfg):
        raise XGError("the XG API is not set: address, user and password in the security plugin's card")
    xml = (f'<Request APIVersion="{API_VERSION}"><Login><Username>{escape(str(cfg["AURORA_XG_API_USER"]))}</Username>'
           f'<Password>{escape(str(cfg["AURORA_XG_API_PASSWORD"]))}</Password></Login>{body}</Request>')
    url = str(cfg["AURORA_XG_API_URL"]).rstrip("/") + "/webconsole/APIController"
    try:
        r = httpx.post(url, files={"reqxml": (None, xml)}, timeout=30, verify=bool(cfg["AURORA_XG_VERIFY_TLS"]))
    except httpx.HTTPError as e:
        raise XGError(f"the firewall does not answer: {e}") from None
    text = r.text
    if re.search(r"<Login>\s*<status>\s*Authentication Failure", text, re.I) or "Authentication Failure" in text:
        raise XGError("the firewall refused the login (user, password, or Aurora's address not allowed for the API)")
    if r.status_code != 200:
        raise XGError(f"HTTP {r.status_code}: {text[:200]}")
    return text


def _status(text: str, tag: str) -> tuple[str, str]:
    m = re.search(rf"<{tag}[^>]*>.*?<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", text[:200])


def test(cfg: sys_config.Config) -> dict:
    """Log in and read the blocking group: the card's "Try the connection"."""
    text = request(cfg, f"<Get><IPHostGroup><Name>{escape(str(cfg['AURORA_XG_BLOCK_GROUP']))}</Name></IPHostGroup></Get>")
    return {"ok": True, "group_exists": f"<Name>{cfg['AURORA_XG_BLOCK_GROUP']}</Name>" in text}


def block(cfg: sys_config.Config, ip: str, reason: str = "") -> dict:
    """The address into the blocking group (the group is made first when missing)."""
    ip = blockable(cfg, ip)
    group = escape(str(cfg["AURORA_XG_BLOCK_GROUP"]))
    request(cfg, f'<Set operation="add"><IPHostGroup><Name>{group}</Name><IPFamily>IPv4</IPFamily>'
                 f"<Description>Aurora: addresses the owner blocked</Description></IPHostGroup></Set>")   # 502: exists
    text = request(cfg, f'<Set operation="add"><IPHost><Name>aurora-block-{ip}</Name><IPFamily>IPv4</IPFamily>'
                        f"<Description>{escape(reason[:200])}</Description><HostType>IP</HostType>"
                        f"<IPAddress>{ip}</IPAddress><HostGroupList><HostGroup>{group}</HostGroup></HostGroupList>"
                        "</IPHost></Set>")
    code, msg = _status(text, "IPHost")
    if code not in ("200", "502", "503"):          # 502/503: the host is there already
        raise XGError(f"the firewall did not add {ip}: {code} {msg}")
    return {"blocked": ip, "group": cfg["AURORA_XG_BLOCK_GROUP"], "status": code, "message": msg}


def unblock(cfg: sys_config.Config, ip: str) -> dict:
    ip = blockable(cfg, ip)
    text = request(cfg, f"<Remove><IPHost><Name>aurora-block-{ip}</Name></IPHost></Remove>")
    code, msg = _status(text, "IPHost")
    if code != "200":
        raise XGError(f"the firewall did not remove {ip}: {code} {msg}")
    return {"unblocked": ip, "status": code, "message": msg}
