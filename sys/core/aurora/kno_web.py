# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The web for an answer (owner, 2026-10-07: «per la ricerca usiamo duck… ddgs»; M130): a search through ddgs (DuckDuckGo
and, when one refuses, the other engines it knows: no key), and a public page read as text. With a Brave Search key
(AURORA_BRAVE_SEARCH_KEY, the machine's: set once by the admin) Brave answers first, for everyone — the answers and
the agent's tool web.search alike (owner, 2026-10-20: «se uno si vuole installare brave gli mette l'api e lo attiva
come predefinito»); ddgs when it fails or finds nothing.

Only a query on the subject leaves the machine — written by the local model, masked (query) —, never the owner's
question. A page is read only at a public address: the name resolved once, every address global, the
connection made to that address (a DNS answer changed in between cannot reach the home network).
"""
from __future__ import annotations

import html.parser
import ipaddress
import logging
import os
import re
import socket
import time
from urllib.parse import urlparse

import httpx

LOG = logging.getLogger("aurora.web")       # each engine's refusal said (C391: two searches failed and left no trace)
UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal assistant)"}
ENGINES = ("auto", "duckduckgo,brave,mojeek", "bing,yahoo")       # M130: a burst of searches is refused by one engine
SYS_QUERY = ("Write a web search query (at most 8 words) for the GENERAL subject of this question, in its language: "
             "the topic, the work, the law, the scientific term. Never a private person's name, an address, a phone, an "
             "e-mail, a number that identifies someone, or any personal detail. Output only the query.")


SYS_TOWN = ("In the QUESTION below, is «{name}» the name of a town, a city, a province, a region or a country? Not a "
            "person, a nickname, a street, a company or a shop. Reply with one word: YES or NO.")


def query(model, question: str, cfg) -> str:
    """What leaves the machine: a query on the general subject written by the local model — never the question —
    then masked (sec_mask), its placeholders removed, and every run of digits longer than a year dropped (the masker
    missed «333 1234567» and plain names: a query of the subject alone is the real protection). A masked value the
    user wrote in the question and the local model calls a town, a region or a country stays (C466: the shops «da qui
    a <town>» searched as «post offices from here to» — the dynamic masking takes a home town for a private value;
    a town alone in a query names nobody). A person, a street, a company never."""
    lines = model.complete(SYS_QUERY, question[:600], 40).answer.strip().splitlines() if question else []
    q = lines[0] if lines else ""                    # an empty reply: no query, never the question (C256)
    return clean(cfg, q, keep=lambda v: v.lower() in question.lower() and _town(model, v, question))


def _town(model, name: str, question: str) -> bool:
    if any(ch.isdigit() for ch in name) or len(name.split()) > 4:
        return False
    try:
        said = model.complete(SYS_TOWN.format(name=name), f"QUESTION: {question[:600]}", 4).answer
    except Exception:                                # noqa: BLE001 — in doubt, masked
        return False
    return said.strip().upper().startswith("YES")


def clean(cfg, q: str, words: int = 10, keep=None) -> str:
    """A query about to leave the machine, as the web search's: masked (sec_mask), its placeholders removed, every run
    of digits longer than a year dropped, at most `words` words. The paper archives' queries too (N64 phase 6:
    arXiv, EuropePMC, Wikipedia, GitHub got the reasoner's queries written from the question as they were).
    `keep(value)`: a PRIVATE value put back (query(): a town the user wrote)."""
    from .sec_mask import BARE, PLACEHOLDER, Pseudonymizer
    m = Pseudonymizer(cfg)
    q = m.mask(q)
    if keep:
        for ph, v in list(m.to_val.items()):
            if ph.startswith("[PRIVATE_") and keep(v):
                q = q.replace(ph, v)
    q = BARE.sub(" ", PLACEHOLDER.sub(" ", q))
    q = re.sub(r"\d[\d\s./-]{4,}\d|\d{5,}", " ", q)
    return " ".join(re.sub(r"[^\w\s'’-]", " ", q).split()[:words])


def brave_key() -> str:
    """The Brave Search key: the process's own (a plugin's filtered environment) or the machine's settings."""
    key = os.environ.get("AURORA_BRAVE_SEARCH_KEY", "")
    if key:
        return key
    try:
        from . import sys_config
        return str(sys_config.get()["AURORA_BRAVE_SEARCH_KEY"] or "")
    except Exception:  # noqa: BLE001 — no settings (a test, a tool alone): no key
        return ""


def brave(query: str, n: int, key: str) -> list[dict]:
    r = httpx.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": max(1, min(n, 20))},
                  headers={"X-Subscription-Token": key, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return [{"title": x.get("title") or "", "url": x.get("url") or "", "text": x.get("description") or ""}
            for x in r.json().get("web", {}).get("results", []) if str(x.get("url", "")).startswith(("https://", "http://"))]


def search(query: str, n: int = 6, region: str = "it-it") -> list[dict]:
    """[{"title", "url", "text"}]: the results' titles and snippets; [] when every engine refuses or fails."""
    if not query.strip():
        return []
    key = brave_key()
    if key:
        try:
            found = brave(query, n, key)
        except Exception as e:  # noqa: BLE001 — over quota, down, a bad key: the engines without a key
            LOG.warning("web search: brave failed (%s: %s)", type(e).__name__, str(e)[:160])
            found = []
        if found:
            return found
    try:
        from ddgs import DDGS
    except ImportError:                                  # not installed: no web, said by the caller
        return []
    for i, backend in enumerate(ENGINES):
        try:
            found = DDGS().text(query, region=region, max_results=n, backend=backend)
        except Exception as e:  # noqa: BLE001 — «No results found», a timeout, an engine down: the next one
            LOG.warning("web search: ddgs %s failed (%s: %s)", backend, type(e).__name__, str(e)[:160])
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
    """A public page as plain text (its first `chars`); "" when it cannot be read, or when its reputation says not to
    open it (the plugin linkcheck: sec_linkcheck)."""
    addr = _public(url)
    if not addr:
        return ""
    from . import sec_linkcheck
    try:
        if sec_linkcheck.check(url)["blocked"]:
            return ""                                    # a bad page is never opened: the next result is read instead
    except Exception:                                    # noqa: BLE001 — the check failing is «not checked», not «clean»:
        pass                                             # the page is a search result, read as text, never run
    u = urlparse(url)
    host = f"[{addr}]" if ":" in addr else addr
    target = u._replace(netloc=host + (f":{u.port}" if u.port else "")).geturl()
    try:                                                 # the name travels in Host and in TLS (SNI): the certificate is checked
        with httpx.Client(timeout=10, follow_redirects=False) as c:
            # up to 1 MB read, in pieces (C438: an endless answer was read whole before the 600,000 characters' cut)
            with c.stream("GET", target, headers={**UA, "Host": u.hostname},
                          extensions={"sni_hostname": u.hostname} if u.scheme == "https" else {}) as s:
                body = b""
                for chunk in s.iter_bytes():
                    body += chunk
                    if len(body) > 1024 * 1024:
                        break
                keep = {k: v for k, v in s.headers.items() if k.lower() not in ("content-encoding", "content-length")}
                r = httpx.Response(s.status_code, headers=keep, content=body[:1024 * 1024], request=s.request)
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
