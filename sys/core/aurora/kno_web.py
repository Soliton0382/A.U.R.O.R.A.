# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The web for an answer (owner, 2026-10-07: «per la ricerca usiamo duck… ddgs»; M130): a search through ddgs (DuckDuckGo
and, when one refuses, the other engines it knows: no key), and a public page read as text.

Only a query on the subject leaves the machine — written by the local model, masked (query) —, never the owner's
question. A page is read only at a public address: the name resolved once, every address global, the
connection made to that address (a DNS answer changed in between cannot reach the home network).
"""
from __future__ import annotations

import html.parser
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import httpx

UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal assistant)"}
ENGINES = ("auto", "duckduckgo,brave,mojeek", "bing,yahoo")       # M130: a burst of searches is refused by one engine
SYS_QUERY = ("Write a web search query (at most 8 words) for the GENERAL subject of this question, in its language: "
             "the topic, the work, the law, the scientific term. Never a private person's name, an address, a phone, an "
             "e-mail, a number that identifies someone, or any personal detail. Output only the query.")


def query(model, question: str, cfg) -> str:
    """What leaves the machine: a query on the general subject written by the local model — never the question —
    then masked (sec_mask), its placeholders removed, and every run of digits longer than a year dropped (the masker
    missed «333 1234567» and plain names: a query of the subject alone is the real protection)."""
    from .sec_mask import BARE, PLACEHOLDER, Pseudonymizer
    q = model.complete(SYS_QUERY, question[:600], 40).answer.strip().splitlines()[0] if question else ""
    q = Pseudonymizer(cfg).mask(q)
    q = BARE.sub(" ", PLACEHOLDER.sub(" ", q))
    q = re.sub(r"\d[\d\s./-]{4,}\d|\d{5,}", " ", q)
    return " ".join(re.sub(r"[^\w\s'’-]", " ", q).split()[:10])


def search(query: str, n: int = 6, region: str = "it-it") -> list[dict]:
    """[{"title", "url", "text"}]: the results' titles and snippets; [] when every engine refuses or fails."""
    if not query.strip():
        return []
    try:
        from ddgs import DDGS
    except ImportError:                                  # not installed: no web, said by the caller
        return []
    for i, backend in enumerate(ENGINES):
        try:
            found = DDGS().text(query, region=region, max_results=n, backend=backend)
        except Exception:  # noqa: BLE001 — «No results found», a timeout, an engine down: the next one
            found = []
        if found:
            return [{"title": x.get("title") or "", "url": x.get("href") or "", "text": x.get("body") or ""}
                    for x in found if x.get("href", "").startswith(("https://", "http://"))]
        if i + 1 < len(ENGINES):
            time.sleep(1.5)
    return []


def _public(url: str) -> str | None:
    """The address to connect to when every address of the name is global; None otherwise."""
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        return None
    try:
        addrs = [ai[4][0] for ai in socket.getaddrinfo(u.hostname, None)]
    except socket.gaierror:
        return None
    if not addrs or any(not ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs):
        return None
    v4 = [a for a in addrs if ":" not in a]
    return (v4 or addrs)[0]


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg", "form", "aside"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in self.SKIP
        if tag in ("p", "br", "li", "h1", "h2", "h3", "tr", "div", "td"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        self.skip -= tag in self.SKIP and self.skip > 0

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def page(url: str, chars: int = 12000) -> str:
    """A public page as plain text (its first `chars`); "" when it cannot be read."""
    addr = _public(url)
    if not addr:
        return ""
    u = urlparse(url)
    host = f"[{addr}]" if ":" in addr else addr
    target = u._replace(netloc=host + (f":{u.port}" if u.port else "")).geturl()
    try:                                                 # the name travels in Host and in TLS (SNI): the certificate is checked
        with httpx.Client(timeout=10, follow_redirects=False) as c:
            r = c.get(target, headers={**UA, "Host": u.hostname},
                      extensions={"sni_hostname": u.hostname} if u.scheme == "https" else {})
    except (httpx.HTTPError, ValueError):
        return ""
    if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
        return ""
    p = _Text()
    try:
        p.feed(r.text[:600000])
    except Exception:  # noqa: BLE001 — a broken page is no page
        return ""
    lines = [" ".join(x.split()) for x in "".join(p.out).splitlines()]
    return "\n".join(x for x in lines if len(x) > 30)[:chars]
