# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Beyond arXiv (owner, 2026-10-04): when Aurora does not know, the search agent also asks the harvester's sources
that can be searched by words, and the re-ranker picks the best among all of them.

    europepmc   open-access articles with their full text (medicine, biology; also bioRxiv and medRxiv preprints)
    wikipedia   encyclopaedia articles, plain text (CC BY-SA)
    github      READMEs of repositories with an open licence

Normattiva is not here: it is fetched only as whole collections, never by words. Each candidate carries a short text
for the re-ranker (title and abstract or snippet); the document itself is fetched only when it is chosen. Its domain
is one of the domains that use that source in config/harvest_sources.json, chosen by the reasoner for the question.
Only the queries leave the machine, as for arXiv.
"""
from __future__ import annotations

import re
from typing import Callable

from .kno_acquire import Entry
from .kno_sources import EPMC, OPEN_LICENCES, WIKI, catalogue, jats_text

Get = Callable[..., object]             # ArxivAgent._polite_get(url, **params) -> httpx.Response
SEARCHERS = ("europepmc", "wikipedia", "github")


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def europepmc(get: Get, query: str, n: int) -> list[Entry]:
    r = get(f"{EPMC}/search", query=f"OPEN_ACCESS:y AND HAS_FT:y AND ({query})", resultType="core", format="json",
            pageSize=n).json()
    out = []
    for h in r.get("resultList", {}).get("result", []):
        pmc = h.get("pmcid")
        if not pmc:
            continue
        lic = h.get("license") or "open access"

        def fetch(pmc=pmc, lic=lic):
            title, text = jats_text(get(f"{EPMC}/{pmc}/fullTextXML").content)
            return f"{pmc}.txt", text.encode(), lic, f"https://europepmc.org/article/PMC/{pmc}"
        about = _plain(h.get("abstractText", "")) or ", ".join(        # no abstract: its MeSH terms for the re-ranker
            m.get("descriptorName", "") for m in (h.get("meshHeadingList") or {}).get("meshHeading", []))
        out.append(Entry(f"europepmc:{pmc}", h.get("title", pmc), about[:1500], "",
                         "", source="europepmc", fetch=fetch))
    return out


def wikipedia(get: Get, query: str, n: int) -> list[Entry]:
    r = get(WIKI, action="query", list="search", srsearch=query, srlimit=n, format="json").json()
    out = []
    for h in r.get("query", {}).get("search", []):
        title = h["title"]

        def fetch(title=title):
            page = next(iter(get(WIKI, action="query", prop="extracts", explaintext=1, titles=title, redirects=1,
                                 format="json").json().get("query", {}).get("pages", {}).values()), {})
            text = re.split(r"\n== (See also|References|Notes|Further reading|External links|Bibliography) ==",
                            page.get("extract", ""))[0]
            return (re.sub(r"\W+", "_", title)[:80] + ".txt", text.encode(), catalogue()["licences"]["wikipedia"],
                    "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"))
        out.append(Entry(f"wikipedia:{title}", title, _plain(h.get("snippet", "")), "", "", source="wikipedia",
                         fetch=fetch))
    return out


def github(get: Get, query: str, n: int) -> list[Entry]:
    r = get("https://api.github.com/search/repositories", q=f"{query} stars:>50", sort="stars", per_page=n).json()
    out = []
    for it in r.get("items", []):
        lic = (it.get("license") or {}).get("spdx_id") or ""
        if lic not in OPEN_LICENCES or it.get("archived") or it.get("fork"):
            continue

        def fetch(it=it, lic=lic):
            for readme in ("README.md", "readme.md", "README.rst", "README"):
                try:
                    text = get(f"https://raw.githubusercontent.com/{it['full_name']}/{it['default_branch']}/{readme}").text
                except Exception:  # noqa: BLE001 — try the next spelling
                    continue
                return re.sub(r"\W+", "_", it["full_name"]) + ".md", text.encode(), lic, it["html_url"]
            raise ValueError("no README")
        out.append(Entry(f"github:{it['full_name']}", f"{it['full_name']}: {it.get('description') or ''}".strip(": "),
                         it.get("description") or "", "", "", source="github", fetch=fetch))
    return out


SEARCH = {"europepmc": europepmc, "wikipedia": wikipedia, "github": github}


def domains_of(source: str) -> list[str]:
    """The vault domains whose harvester uses this source (their order in the file: the first is the default)."""
    return [d for d, srcs in catalogue()["domains"].items() if any(s["source"] == source for s in srcs)]


def choose_domain(llm, source: str, question: str, title: str) -> str:
    doms = domains_of(source)
    if len(doms) <= 1:
        return doms[0] if doms else "general"
    out = llm.complete("Choose the domain of a document for a knowledge vault. Reply with one name from the list, "
                       "nothing else.", f"DOMAINS: {', '.join(doms)}\nQUESTION: {question}\nDOCUMENT: {title}",
                       20).answer.strip().lower()
    return next((d for d in doms if d in out), doms[0])
