# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Guards the routes share, a part of core without routes (security audits of 9 and 10 Nov, C535 and C570):

 - `body_cap`: how large a body a caller may send, decided on the headers alone (sys_bodylimit asks before it reads);
 - `who_now`, `live`: a stream that goes on for minutes asks again who its caller is — a device revoked, an
   assistance ended, a key changed end it;
 - `confirm_again`, `wrong`: the password (and the authenticator's code) asked again before a lasting credential is
   made; a wrong one counted like a failed login;
 - `upstream_error`: what is said of a service that failed — its kind, never its text as it came;
 - `address_problem`, `secrets_of`: a user's own address of a service (their Home Assistant, a calendar's server)
   is never one of the house's unless the admin uses the same, and a changed address forgets the secret that went
   with the old one.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request

from aurora.sys_bodylimit import CAP
from aurora.sys_devices import COOKIE

from .core import (BASE, _admin, _failed, _from_this_machine, _is_key, _locked, devices, is_maintenance_key, log, me,
                   user_of)

RECHECK_S = 15.0                                        # a stream's caller looked at again, at most this often
CAMERA_PUSH = "/v1/aurora/astro/camera/push"


# ---- the body's ceiling (C535) -----------------------------------------------------------------------------------
def _bearer(value: str) -> str:
    return value.removeprefix("Bearer ").strip()


def body_cap(path: str, headers: dict) -> int | None:
    """The largest body this caller may send: 0 a stranger (the small one everybody may), CAP a caller whose
    credential is good now, None the camera's endless stream from a PC whose key is known. `headers`: the raw ASGI
    ones (bytes), no body read yet."""
    from starlette.requests import cookie_parser
    get = lambda k: headers.get(k, b"").decode("latin-1")            # noqa: E731
    camera = get(b"x-aurora-camera").strip()
    if camera:
        from .astro_cam import relay
        if relay().who(camera):
            return None if path == CAMERA_PUSH else CAP
    token = get(b"x-aurora-conductor")
    if token:
        from aurora import prj_act
        if prj_act.lookup(token) is not None:
            return CAP
    bearer = _bearer(get(b"authorization"))
    if bearer and (_is_key(bearer) or is_maintenance_key(bearer)):
        return CAP
    cookie = cookie_parser(get(b"cookie")).get(COOKIE, "") if headers.get(b"cookie") else ""
    if devices.check(bearer) or devices.check(cookie):
        return CAP
    return 0


# ---- a stream's caller, asked again (C535) -----------------------------------------------------------------------
def who_now(conn) -> str | None | bool:
    """Whose request this would be now, by the same rules as `auth` (the assistance too); False: nobody's any more.
    `conn`: a Request or a WebSocket."""
    from aurora import sys_assist
    bearer = _bearer(conn.headers.get("authorization", ""))
    if _is_key(bearer) or (is_maintenance_key(bearer) and _from_this_machine(conn)):
        return _admin()
    dev = devices.check(bearer) or devices.check(conn.cookies.get(COOKIE, ""))
    if dev is None:
        return False
    user = dev.get("user") or _admin()
    if user == _admin():
        s = sys_assist.acting(BASE.base or BASE, dev.get("id", ""))
        if s:
            return s["user"]
    return user


async def live(request: Request, stream, every: float = RECHECK_S):
    """`stream`, for as long as its caller is who they were when it began: looked at again every `every` seconds, and
    ended without a word when the device was revoked, the user deleted or the assistance over."""
    who, at = user_of(request), time.monotonic()
    try:
        async for item in stream:
            if time.monotonic() - at >= every:
                at = time.monotonic()
                if await asyncio.to_thread(who_now, request) != who:
                    log.info("audit: a live stream ended: its caller's right is over (%s)", request.url.path)
                    return
            yield item
    finally:
        close = getattr(stream, "aclose", None)
        if close:
            await close()


# ---- the password again (C570) -----------------------------------------------------------------------------------
def wrong(request: Request, detail: str) -> HTTPException:
    """A wrong password or code given inside a session: counted like a failed login (it was a free guess)."""
    _failed(request)
    return HTTPException(status_code=401, detail=detail)


def confirm_again(request: Request, body: dict) -> None:
    """Before a lasting credential is made (an API key): {"password"} again and, with an authenticator on, its
    {"code"}. Not asked of the installation's own key (it is the stronger credential already) nor of an account
    that has no password."""
    from aurora.sys_users import Users
    if getattr(request.state, "device", None) is None:
        return
    users, name = Users(BASE.base or BASE), me()
    u = users.by_name(name or "")
    if u is None or not u["has_password"]:
        return
    _locked(request)
    if users.check_password(name, str(body.get("password", ""))) is None:
        raise wrong(request, "the password is wrong")
    if u["totp_on"] and not users.totp_current(u["id"], str(body.get("code", "")).strip()):
        raise wrong(request, "the authenticator's code is wrong")


# ---- a service's failure, said without its text (C570) -----------------------------------------------------------
_URL = re.compile(r"\b([a-z][a-z0-9+.-]*)://[^\s'\"<>]+", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9_\-.~+/=]{24,}")


def upstream_error(e: BaseException, limit: int = 160) -> str:
    """What a page is told of a service that failed: an HTTP error's kind and status; of anything else its words
    without addresses and without anything long enough to be a key. The whole text goes to the log."""
    log.warning("upstream: %s: %s", type(e).__name__, re.sub(r"\?\S*", "?…", str(e)[:500]))   # no query: a key may be there
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    if isinstance(e, httpx.TimeoutException):
        return "no answer in time"
    if isinstance(e, httpx.HTTPError):
        return f"not reachable ({type(e).__name__})"
    text = _URL.sub(lambda m: f"{m.group(1)}://…", str(e))
    return f"{type(e).__name__}: {_TOKEN.sub('…', text)[:limit]}".rstrip(": ")


# ---- a user's own addresses (C535) -------------------------------------------------------------------------------
# an address of a service the user gives, and the secrets Aurora sends to it
ADDRESS_SECRETS = {"AURORA_HA_URL": ("AURORA_HA_TOKEN",), "AURORA_CALDAV_URL": ("AURORA_CALDAV_PASSWORD",),
                   "AURORA_WEBDAV_URL": ("AURORA_WEBDAV_PASSWORD",), "AURORA_MASTODON_URL": ("AURORA_MASTODON_TOKEN",),
                   "AURORA_EMAIL_IMAP_HOST": ("AURORA_EMAIL_PASSWORD",), "AURORA_EMAIL_SMTP_HOST": ("AURORA_EMAIL_PASSWORD",)}


def _same(a: str, b: str) -> bool:
    return a.strip().rstrip("/") == b.strip().rstrip("/")


def secrets_of(changes: dict, current) -> list[str]:
    """The secrets to forget with this change: those of an address that was set and is now another, unless the same
    change brings the secret again (C535: the token kept for the old address was sent to the new one)."""
    out = []
    for key, secrets_ in ADDRESS_SECRETS.items():
        if key not in changes:
            continue
        old = str(current[key] or "")
        if old.strip() and not _same(old, str(changes[key])):
            out += [s for s in secrets_ if s not in changes and s not in out]
    return out


def _host_port(value: str) -> tuple[str, int | None]:
    u = urlparse(value.strip() if "://" in value else f"//{value.strip()}")
    try:
        return (u.hostname or "").lower(), u.port
    except ValueError:
        return "", None


def _resolve(host: str) -> list[str]:
    return sorted({a[4][0].split("%")[0] for a in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})


def private_host(host: str, resolve=None) -> bool:
    """Whether a host is this machine's or the house's: a literal address that is not a public one, or a name that
    resolves to one (a name that does not resolve is not refused here: nothing is reached through it)."""
    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:
        if host == "localhost" or host.endswith((".localhost", ".local", ".lan", ".home", ".internal")):
            return True
        try:
            addrs = (resolve or _resolve)(host)
        except OSError:
            return False
    return any(not ipaddress.ip_address(a).is_global for a in addrs)


def address_problem(key: str, value: str, user: str | None, admin_cfg, resolve=None) -> str | None:
    """Why a user (not the admin) may not have this address, or None (C535: a user's own «Home Assistant» pointed at
    the house's addresses, and Aurora's requests to it told them what answers there). The house's own is allowed when
    it is the admin's too: the same host and port in the admin's same setting."""
    if key not in ADDRESS_SECRETS or not value.strip() or not user or user == _admin():
        return None
    host, port = _host_port(value)
    if not host:
        return f"{key}: not an address"
    if not private_host(host, resolve):
        return None
    if (host, port) == _host_port(str(admin_cfg[key] or "")):
        return None
    return f"{key}: an address of the house or of this machine is the admin's to set (the same as the admin's is allowed)"
