# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Fetching an address someone typed, without opening the machine to them (C426, 28 Oct: a plain user's settings or an
icon's link made the server reach 127.0.0.1 — the local model, the models service, Caddy's admin — and the LAN).

The name resolved once and every address checked; the connection goes to that address (a DNS answer that changes in
between cannot point elsewhere: rebinding), the name kept in Host and in TLS; every redirect checked again; the body
read up to a ceiling. Who may reach what:
  - this machine itself (loopback, link-local, unspecified): never — its services trust 127.0.0.1;
  - the LAN (private addresses): only when allowed (`lan=True`, the admin's own settings: a NAS, a home Nextcloud);
  - the internet: always.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 5 * 1024 * 1024
REDIRECTS = 5


class Refused(ValueError):
    """The address is not one this caller may reach."""


def check(url: str, lan: bool = False) -> str:
    """The address the connection must go to; Refused when the URL is not http(s) or reaches what it may not."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise Refused("only http(s) addresses")
    try:
        addrs = [ai[4][0] for ai in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))]
    except socket.gaierror:
        raise Refused(f"cannot resolve {u.hostname}") from None
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise Refused(f"{u.hostname}: this machine or a reserved address, refused")
        if not ip.is_global and not lan:
            raise Refused(f"{u.hostname}: a local network address, refused")
    v4 = [a for a in addrs if ":" not in a]
    return (v4 or addrs)[0]


def request(method: str, url: str, lan: bool = False, max_bytes: int = MAX_BYTES, timeout: float = 30, **kw) -> httpx.Response:
    """One request to `url` checked (and each redirect, for GET), the body read up to `max_bytes` (Refused beyond)."""
    for _ in range(REDIRECTS + 1):
        addr = check(url, lan)
        u = urlparse(url)
        host = f"[{addr}]" if ":" in addr else addr
        target = u._replace(netloc=host + (f":{u.port}" if u.port else "")).geturl()
        headers = {**kw.pop("headers", {}), "Host": u.hostname + (f":{u.port}" if u.port else "")}
        ext = {"sni_hostname": u.hostname} if u.scheme == "https" else {}
        with httpx.Client(timeout=timeout, follow_redirects=False) as c:
            with c.stream(method, target, headers=headers, extensions=ext, **kw) as r:
                if r.is_redirect and method == "GET" and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    kw["headers"] = {k: v for k, v in headers.items() if k != "Host"}
                    continue
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise Refused(f"the answer is larger than {max_bytes // 1024 // 1024} MB")
                keep = {k: v for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length")}
                return httpx.Response(r.status_code, headers=keep, content=body, request=r.request)
    raise Refused("too many redirects")
