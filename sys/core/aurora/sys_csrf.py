# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A request that changes something, carried by the WebUI's cookie, comes from Aurora's own pages only (security review,
28 Oct, C441: the only defence was the cookie's SameSite=Strict — another site of the same name's family, a browser
without SameSite, could post with the person's session).

POST, PUT, PATCH, DELETE with the device cookie and no API key: refused when the browser says the request comes from
elsewhere — its Origin is not the host it was sent to, or (no Origin) Sec-Fetch-Site says «cross-site». A request
with no such headers (a program, the phone app's own calls) is let through: it carries no browser's session of
someone else's page. The API key's calls (Authorization: Bearer) are never looked at.

The login is checked without a cookie too (C570, login CSRF: another site could post its own name and password and
leave the person inside the attacker's account), and so is the call's WebSocket (`foreign_socket`: a browser sends
its cookie with a socket opened by any page, and no same-origin rule stops it).
"""
from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .sys_devices import COOKIE

CHANGES = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN = ("/v1/aurora/login",)                           # C570: a session is made here: checked with no cookie yet


def _elsewhere(headers) -> bool:
    """The browser says the request comes from another site (no such header: not a browser's page, False)."""
    origin = headers.get("origin")
    if origin:
        if origin == "null":                             # a sandboxed frame (a preview, an artifact): never the session's
            return True
        host = headers.get("x-forwarded-host") or headers.get("host") or ""
        o = urlparse(origin)
        if o.scheme.lower() == "http" and (headers.get("x-forwarded-proto") or "").lower() == "https":
            return True                                  # C595: the same name over plain http is not this site
        return o.netloc.lower() != host.lower()
    return headers.get("sec-fetch-site", "").lower() == "cross-site"


def foreign_socket(headers) -> bool:
    """C570: a WebSocket opened by another site's page (the phone app and programs send no Origin: let through)."""
    return _elsewhere(headers)


def foreign(method: str, headers, cookies, path: str = "") -> bool:
    """Whether a request is a browser's from another site, using the person's session (or making one: LOGIN)."""
    if method not in CHANGES:
        return False
    if path in LOGIN:
        return _elsewhere(headers)
    if COOKIE not in cookies or headers.get("authorization", "").lower().startswith("bearer "):
        return False
    return _elsewhere(headers)


class SameOrigin(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if foreign(request.method, request.headers, request.cookies, request.url.path):
            return JSONResponse({"detail": "refused: a change from another site (CSRF)"}, status_code=403)
        return await call_next(request)
