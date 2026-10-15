# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Defence on the firewall through its API (owner, 2026-10-04) — only on the owner's click.

Any firewall: the device's dialect is a driver of aurora/fw_drivers, chosen by AURORA_FIREWALL_API_KIND (ROADMAP 108);
this module keeps what every device shares — the address, the addresses never blocked, one call at a time.

What Aurora does, and nothing else: an IP host "aurora-block-<address>" in the group AURORA_FIREWALL_BLOCK_GROUP, and
its removal. The group
must be used by a firewall rule that drops, made once by the owner on the firewall: Aurora never writes rules.
Never blocked: loopback, link-local, multicast, the firewall itself, this machine's own addresses.
"""
from __future__ import annotations

import contextlib
import ipaddress
import socket
from urllib.parse import urlparse

from . import sys_config
from .fw_drivers import KINDS, driver  # noqa: F401 — KINDS read from here by the settings' page


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
    return _driver(cfg).request(cfg, body)


def _driver(cfg: sys_config.Config):
    try:
        return driver(cfg)
    except ValueError as e:
        raise FirewallAPIError(str(e)) from None


def test(cfg: sys_config.Config) -> dict:
    """Log in and read the blocking group: the card's "Try the connection"."""
    text = request(cfg, _driver(cfg).get_group(str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])))
    return {"ok": True, "group_exists": _driver(cfg).has_group(text, str(cfg["AURORA_FIREWALL_BLOCK_GROUP"]))}


def block(cfg: sys_config.Config, ip: str, reason: str = "") -> dict:
    """The address into the blocking group (the group is made first when missing)."""
    ip = blockable(cfg, ip)
    d = _driver(cfg)
    group = str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])
    request(cfg, d.add_group(group))                                                    # made once; then: exists
    text = request(cfg, d.add_host(f"aurora-block-{ip}", ip, reason[:200], group))
    code, msg = d.status(text, "IPHost")
    if code not in d.ok_codes("add_host"):
        raise FirewallAPIError(f"the firewall did not add {ip}: {code} {msg}")
    return {"blocked": ip, "group": cfg["AURORA_FIREWALL_BLOCK_GROUP"], "status": code, "message": msg}


def unblock(cfg: sys_config.Config, ip: str) -> dict:
    """Out of the group first, then removed: the firewall refuses to delete a host a group still refers to (509, C146)."""
    ip = blockable(cfg, ip)
    d = _driver(cfg)
    text = request(cfg, d.ungroup_host(f"aurora-block-{ip}", ip, str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])))
    code, msg = d.status(text, "IPHost")
    if code != "200":
        raise FirewallAPIError(f"the firewall did not take {ip} out of the group: {code} {msg}")
    text = request(cfg, d.remove_host(f"aurora-block-{ip}"))
    code, msg = d.status(text, "IPHost")
    if code != "200":
        raise FirewallAPIError(f"the firewall did not remove {ip}: {code} {msg}")
    return {"unblocked": ip, "status": code, "message": msg}
