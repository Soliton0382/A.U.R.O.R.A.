# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Defence on the firewall through its API (owner, 2026-10-04) — only on the owner's click.

Any firewall in principle; one dialect today, AURORA_FIREWALL_API_KIND = sophos (docs.sophos.com, Sophos Firewall
21.0, "API" and "Post an API request"): an HTTPS POST to <AURORA_FIREWALL_API_URL>/webconsole/APIController with the
form field "reqxml" holding <Request><Login><Username/><Password/></Login> ... </Request>. No APIVersion: the
firewall then answers with its own (an example's "1905.2" was refused with 529 "There is no API Version", C131).
API access is off by default on the firewall: the owner turns it on and allows Aurora's address.

What Aurora does, and nothing else: an IP host "aurora-block-<address>" (IPHost: Name, IPFamily, HostType IP,
IPAddress, HostGroupList/HostGroup) in the group AURORA_FIREWALL_BLOCK_GROUP (IPHostGroup), and its removal. The group
must be used by a firewall rule that drops, made once by the owner on the firewall: Aurora never writes rules.
Never blocked: loopback, link-local, multicast, the firewall itself, this machine's own addresses.
"""
from __future__ import annotations

import contextlib
import ipaddress
import re
import socket
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx

from . import sys_config

KINDS = ("sophos",)


class FirewallAPIError(Exception):
    pass


def base_url(cfg: sys_config.Config) -> str:
    """https://address:port only: whatever follows (a path, a copied curl example) is left out (C131)."""
    raw = str(cfg["AURORA_FIREWALL_API_URL"] or "").strip().split()
    u = urlparse(raw[0]) if raw else None
    if not u or u.scheme not in ("https", "http") or not u.hostname:
        return ""
    return f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else "")


def configured(cfg: sys_config.Config) -> bool:
    return bool(base_url(cfg) and cfg["AURORA_FIREWALL_API_USER"] and cfg["AURORA_FIREWALL_API_PASSWORD"])


def _own_addresses() -> set[str]:
    """Every address of this machine's interfaces (`ip -j addr`), and its host name's. The host name alone gave only
    127.0.1.1 (C180): the LAN address was blockable — and a Cloudflare tunnel's traffic comes from it."""
    import json
    import subprocess
    out = set()
    try:
        r = subprocess.run(["ip", "-j", "addr", "show"], capture_output=True, text=True, timeout=5)
        for iface in json.loads(r.stdout or "[]"):
            out.update(a["local"] for a in iface.get("addr_info", []) if a.get("local"))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            out.add(info[4][0])
    except OSError:
        pass
    return out


def blockable(cfg: sys_config.Config, ip: str) -> str:
    """The address as the firewall takes it; FirewallAPIError for one never to be blocked."""
    try:
        a = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise FirewallAPIError(f"not an IP address: {ip!r}") from None
    if a.version != 4:
        raise FirewallAPIError("IPv6 is not handled yet")
    if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified or a.is_reserved:
        raise FirewallAPIError(f"{a} is never blocked")
    fw = urlparse(base_url(cfg)).hostname or ""
    if str(a) == fw or str(a) in _own_addresses():
        raise FirewallAPIError(f"{a} is the firewall or this machine: never blocked")
    return str(a)


@contextlib.contextmanager
def _one_at_a_time(cfg: sys_config.Config):
    """One API call at a time on this machine, across processes (the API, the security plugin, the sentinel): the
    firewall refused simultaneous logins of the same user as «wrong credentials» — three in one second (C192), and it
    locks the user out after 5 failures in a minute."""
    import fcntl
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "fwapi.lock"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a") as h:
        fcntl.flock(h, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(h, fcntl.LOCK_UN)


def request(cfg: sys_config.Config, body: str) -> str:
    """One API call; returns the firewall's XML answer. FirewallAPIError when the login or the call is refused."""
    if not configured(cfg):
        raise FirewallAPIError("the firewall's API is not set: address, user and password in the security plugin's card")
    if str(cfg["AURORA_FIREWALL_API_KIND"]) not in KINDS:
        raise FirewallAPIError(f"firewall API kind {cfg['AURORA_FIREWALL_API_KIND']!r}: one of {KINDS}")
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


def _status(text: str, tag: str) -> tuple[str, str]:
    m = re.search(rf"<{tag}[^>]*>.*?<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", text[:200])


def test(cfg: sys_config.Config) -> dict:
    """Log in and read the blocking group: the card's "Try the connection"."""
    text = request(cfg, f"<Get><IPHostGroup><Name>{escape(str(cfg['AURORA_FIREWALL_BLOCK_GROUP']))}</Name></IPHostGroup></Get>")
    return {"ok": True, "group_exists": f"<Name>{cfg['AURORA_FIREWALL_BLOCK_GROUP']}</Name>" in text}


def block(cfg: sys_config.Config, ip: str, reason: str = "") -> dict:
    """The address into the blocking group (the group is made first when missing)."""
    ip = blockable(cfg, ip)
    group = escape(str(cfg["AURORA_FIREWALL_BLOCK_GROUP"]))
    request(cfg, f'<Set operation="add"><IPHostGroup><Name>{group}</Name><IPFamily>IPv4</IPFamily>'
                 f"<Description>Aurora: addresses the owner blocked</Description></IPHostGroup></Set>")   # 502: exists
    text = request(cfg, f'<Set operation="add"><IPHost><Name>aurora-block-{ip}</Name><IPFamily>IPv4</IPFamily>'
                        f"<Description>{escape(reason[:200])}</Description><HostType>IP</HostType>"
                        f"<IPAddress>{ip}</IPAddress><HostGroupList><HostGroup>{group}</HostGroup></HostGroupList>"
                        "</IPHost></Set>")
    code, msg = _status(text, "IPHost")
    if code not in ("200", "502", "503"):          # 502/503: the host is there already
        raise FirewallAPIError(f"the firewall did not add {ip}: {code} {msg}")
    return {"blocked": ip, "group": cfg["AURORA_FIREWALL_BLOCK_GROUP"], "status": code, "message": msg}


def unblock(cfg: sys_config.Config, ip: str) -> dict:
    """Out of the group first, then removed: the firewall refuses to delete a host a group still refers to (509, C146)."""
    ip = blockable(cfg, ip)
    text = request(cfg, f'<Set operation="update"><IPHost><Name>aurora-block-{ip}</Name><IPFamily>IPv4</IPFamily>'
                        f"<HostType>IP</HostType><IPAddress>{ip}</IPAddress><HostGroupList></HostGroupList></IPHost></Set>")
    code, msg = _status(text, "IPHost")
    if code != "200":
        raise FirewallAPIError(f"the firewall did not take {ip} out of the group: {code} {msg}")
    text = request(cfg, f"<Remove><IPHost><Name>aurora-block-{ip}</Name></IPHost></Remove>")
    code, msg = _status(text, "IPHost")
    if code != "200":
        raise FirewallAPIError(f"the firewall did not remove {ip}: {code} {msg}")
    return {"unblocked": ip, "status": code, "message": msg}
