# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "web": read public pages, search. Never local or private addresses (no internal probing).
The search is the answers' own (kno_web.search): Brave Search when the machine has its key, else ddgs — DuckDuckGo and,
when one refuses, the other engines it knows, with no key (C368: this tool knew only Brave, with no key since the
first day, while the answers searched through ddgs)."""
from __future__ import annotations

import html.parser
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

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
def fetch_url(url: str, max_chars: int = 12000, offset: int = 0) -> str:
    """A public web page as plain text (title first). Follows redirects, but only to public addresses. A long page
    says where it stops; `offset` reads on from that character (C381)."""
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
        return _part(r.text, max_chars, offset)
    p = _Text()
    p.feed(r.text)
    text = "\n".join(line.strip() for line in "".join(p.out).splitlines() if line.strip())
    return f"{p.title.strip()}\n{url}\n\n{_part(text, max_chars, offset)}"


def _part(text: str, max_chars: int, offset: int) -> str:
    offset = max(0, offset)
    part, left = text[offset:offset + max_chars], len(text) - offset - max_chars
    return part + (f"\n[page cut here: {left} more characters; fetch_url(url, offset={offset + max_chars}) reads on]"
                   if left > 0 else "")


@server.tool()
def search(query: str, count: int = 8) -> str:
    """Web search: Brave Search when its key is set, else the engines without a key (DuckDuckGo and the others of
    ddgs): title, address, snippet of the best results."""
    from aurora import kno_web
    hits = kno_web.search(query, n=max(1, min(count, 20)))
    if not hits:
        raise ToolError("search: no results (every engine refused or failed) — read the known sources with fetch_url")
    return "\n\n".join(f"{x['title']}\n{x['url']}\n{x['text']}" for x in hits)


if __name__ == "__main__":
    server.run("stdio")
