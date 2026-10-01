# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "web": read public pages, search. Never local or private addresses (no internal probing)."""
from __future__ import annotations

import html.parser
import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

KEY = os.environ.get("AURORA_BRAVE_SEARCH_KEY", "")
server = MCPServer("web", version="1.0")


def _public(url: str) -> tuple[str, str]:
    """(url, address): the name resolved once, every address public; the connection goes to that address, so a
    DNS answer that changes between the check and the connection (rebinding) cannot reach the local network."""
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise ToolError("only http(s) URLs")
    try:
        addrs = [ai[4][0] for ai in socket.getaddrinfo(u.hostname, None)]
    except socket.gaierror:
        raise ToolError(f"cannot resolve {u.hostname}")
    if not addrs or any(not ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs):
        raise ToolError(f"{u.hostname} resolves to a local or private address: refused")
    v4 = [a for a in addrs if ":" not in a]
    return url, (v4 or addrs)[0]


def _get(c: httpx.Client, url: str, addr: str) -> httpx.Response:
    """GET to the checked address; the name travels in Host and in TLS (SNI), so the certificate is checked."""
    u = urlparse(url)
    host = f"[{addr}]" if ":" in addr else addr
    netloc = host + (f":{u.port}" if u.port else "")
    headers = {"Host": u.hostname + (f":{u.port}" if u.port else "")}
    ext = {"sni_hostname": u.hostname} if u.scheme == "https" else {}
    return c.get(u._replace(netloc=netloc).geturl(), headers=headers, extensions=ext)


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg"}

    def __init__(self):
        super().__init__()
        self.out, self.skip, self.title, self._t = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        self.skip += tag in self.SKIP
        self._t = tag == "title"
        if tag in ("p", "br", "li", "h1", "h2", "h3", "tr", "div"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        self.skip -= tag in self.SKIP and self.skip > 0
        self._t = False

    def handle_data(self, d):
        if self._t:
            self.title += d
        elif not self.skip:
            self.out.append(d)


@server.tool()
def fetch_url(url: str, max_chars: int = 12000) -> str:
    """A public web page as plain text (title first). Follows redirects, but only to public addresses."""
    url, addr = _public(url)
    with httpx.Client(timeout=30, follow_redirects=False, headers={"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal assistant)"}) as c:
        for _ in range(5):
            r = _get(c, url, addr)
            if r.is_redirect:
                url, addr = _public(urljoin(url, r.headers.get("location", "")))
                continue
            break
    if r.status_code >= 400:
        raise ToolError(f"HTTP {r.status_code}")
    if "html" not in r.headers.get("content-type", "html"):
        return r.text[:max_chars]
    p = _Text()
    p.feed(r.text)
    text = "\n".join(line.strip() for line in "".join(p.out).splitlines() if line.strip())
    return f"{p.title.strip()}\n{url}\n\n{text[:max_chars]}"


@server.tool()
def search(query: str, count: int = 8) -> str:
    """Web search (Brave Search API): title, address, snippet of the best results."""
    if not KEY:
        return "not available: AURORA_BRAVE_SEARCH_KEY is empty"
    r = httpx.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": max(1, min(count, 20))},
                  headers={"X-Subscription-Token": KEY, "Accept": "application/json"}, timeout=30)
    if r.status_code != 200:
        raise ToolError(f"Brave Search {r.status_code}")
    return "\n\n".join(f"{x['title']}\n{x['url']}\n{x.get('description', '')}" for x in r.json().get("web", {}).get("results", []))


if __name__ == "__main__":
    server.run("stdio")
