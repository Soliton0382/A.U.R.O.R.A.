# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The harvester's sources, per vault domain (config/harvest_sources.json), and the owner's choice of domains.

Each source walks its catalogue with a cursor kept in <AURORA_STATUS_DIR>/harvest/sources/<domain>.<n>.json and
returns Docs: a file for the importer (PDF, text, Markdown) or ready passages (the articles of a law). Every Doc
carries its licence and origin. A source says when it has nothing more: in "until exhausted" mode the domain is
then complete.

    arxiv       PDFs by category (export.arxiv.org API)
    normattiva  Italian law: the official pre-packed collections (Akoma Ntoso), one passage per article
    europepmc   open-access full texts (JATS) for a query, with their licence
    biorxiv / medrxiv  preprints (JATS) by category, with their licence
    wikipedia   the articles linked from a list page (e.g. Vital articles), plain text
    github      READMEs of popular repositories with an open licence, by topic

Domain modes (the owner, Harvester page): off | round (the newest, every AURORA_HARVEST_INTERVAL_H) |
exhaust (round after round until every source of the domain is done).
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from . import sys_config
from .kno_acquire import parse_atom

SOURCES_FILE = Path(__file__).resolve().parents[1] / "config" / "harvest_sources.json"
MODES = ("off", "round", "exhaust")
NORMATTIVA = "https://api.normattiva.it/t/normattiva.api/bff-opendata/v1/api/v1/collections/download/collection-preconfezionata"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
WIKI = "https://en.wikipedia.org/w/api.php"
AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
OPEN_LICENCES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0",
                 "MPL-2.0", "AGPL-3.0", "ISC", "Unlicense", "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "0BSD", "Zlib",
                 "BSL-1.0", "EPL-2.0", "PostgreSQL", "Python-2.0"}

Fetch = Callable[..., "object"]          # Harvester._get(url, **params) -> httpx.Response


@dataclass
class Doc:
    key: str                              # unique across sources ("normattiva:urn...", arXiv id as is)
    domain: str
    title: str
    origin: str
    licence: str
    url: str
    name: str = ""                        # file name for the importer (its suffix picks the reader)
    data: bytes = b""
    passages: list[str] = field(default_factory=list)   # ready passages (no importer)
    lang: str = "en"


def catalogue() -> dict:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))


# ---- the owner's choice ------------------------------------------------------------------------------

def _prefs_file(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "harvest"
    d.mkdir(parents=True, exist_ok=True)
    return d / "domains.json"


def default_modes(cfg: sys_config.Config) -> dict[str, str]:
    """Before the owner chooses: "round" for the domains of AURORA_HARVEST_CATEGORIES, the rest off."""
    cats = set(cfg["AURORA_HARVEST_CATEGORIES"])
    out = {}
    for dom, srcs in catalogue()["domains"].items():
        hit = any(s["source"] == "arxiv" and cats & set(s.get("categories", [])) for s in srcs)
        out[dom] = "round" if hit else "off"
    return out


def modes(cfg: sys_config.Config) -> dict[str, str]:
    out = default_modes(cfg)
    try:
        saved = json.loads(_prefs_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    out.update({k: v for k, v in saved.items() if k in out and v in MODES})
    return out


def set_modes(cfg: sys_config.Config, changes: dict[str, str]) -> dict[str, str]:
    cur = modes(cfg)
    bad = [k for k, v in changes.items() if k not in cur or v not in MODES]
    if bad:
        raise ValueError(f"unknown domain or mode: {bad}")
    cur.update(changes)
    tmp = _prefs_file(cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, _prefs_file(cfg))
    return cur


# ---- cursors --------------------------------------------------------------------------------------------

def _state_file(cfg: sys_config.Config, domain: str, n: int) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "harvest" / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{domain}.{n}.json"


def load_state(cfg: sys_config.Config, domain: str, n: int) -> dict:
    try:
        return json.loads(_state_file(cfg, domain, n).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(cfg: sys_config.Config, domain: str, n: int, st: dict) -> None:
    f = _state_file(cfg, domain, n)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def progress(cfg: sys_config.Config, domain: str) -> dict:
    """What the Harvester page shows per domain: sources, harvested so far, complete or not."""
    srcs = catalogue()["domains"].get(domain, [])
    sts = [load_state(cfg, domain, i) for i in range(len(srcs))]
    return {"sources": [s["source"] for s in srcs], "taken": sum(s.get("taken", 0) for s in sts),
            "done": bool(srcs) and all(s.get("done") for s in sts)}


# ---- parsers (pure: tested offline) ----------------------------------------------------------------------

def _clean(s: str) -> str:
    return " ".join(s.split())


def akn_articles(xml: bytes) -> tuple[str, str, list[str]]:
    """(title, urn, article texts) of an Akoma Ntoso act; each article keeps its number and heading.
    Normattiva writes the codes (civil code, navigation code...) as attachments, one article each, and ships
    a few files base64-encoded: both are read."""
    if xml[:4] == b"PD94":                                       # base64 of "<?xml"
        xml = base64.b64decode(xml)
    root = ET.fromstring(xml)
    title = _clean("".join(next(root.iter(f"{AKN}docTitle"), ET.Element("x")).itertext()))
    title = re.sub(r"\s*\(\w{6,}\)\s*$", "", title)             # the Gazzetta code, e.g. "(10G0089)"
    urn = next((a.get("value", "") for a in root.iter(f"{AKN}FRBRalias") if a.get("name") == "urn:nir"), "")
    body = root.find(f"{AKN}act/{AKN}body")
    arts = [_clean(" ".join(a.itertext())) for a in (body.iter(f"{AKN}article") if body is not None else [])]
    for att in root.iter(f"{AKN}attachment"):                    # num, heading, text: never glued
        mb = att.find(f"{AKN}doc/{AKN}mainBody")
        if mb is not None:
            arts.append(_clean(" ".join(mb.itertext())))
    return title, urn, [a for a in arts if len(a) > 20]


def jats_text(xml: bytes | str) -> tuple[str, str]:
    """(title, text) of a JATS article: abstract and body, one paragraph per line; references dropped."""
    root = ET.fromstring(xml)
    strip = lambda t: t.split("}", 1)[-1]                       # noqa: E731
    title = ""
    for el in root.iter():
        if strip(el.tag) == "article-title":
            title = _clean("".join(el.itertext()))
            break
    parts = []
    for el in root.iter():
        if strip(el.tag) in ("abstract", "body"):
            for p in el.iter():
                if strip(p.tag) in ("title", "p"):
                    t = _clean("".join(p.itertext()))
                    if t:
                        parts.append(t)
    return title, "\n\n".join(parts)


def pack(title: str, items: list[str], size: int, min_chars: int) -> list[str]:
    """Consecutive articles joined into passages of at least `min_chars` (the vault refuses shorter fragments of a
    long document) and, when they are short, up to about `size`; each passage starts with the act's title.
    An article longer than `size` stays alone (the chunker splits it later)."""
    out: list[str] = []
    cur = ""
    for a in items:
        if cur and len(cur) >= min_chars and len(cur) + len(a) + 2 > size:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{a}" if cur else f"{title} — {a}"
    if cur:
        if out and len(cur) < min_chars:
            out[-1] += "\n\n" + cur
        else:
            out.append(cur)
    return out


# ---- sources ---------------------------------------------------------------------------------------------

def arxiv(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
    cats = spec.get("categories", [])
    if not cats:
        st["done"] = True
        return []
    i = st.get("i", 0) % len(cats)
    cat = cats[i]
    offsets = st.setdefault("offsets", {})
    start = offsets.get(cat, 0) if deep else 0
    xml = fetch(cfg["AURORA_ARXIV_API"], search_query=f"cat:{cat}", sortBy="submittedDate", sortOrder="descending",
                start=start, max_results=max(want * 3, 30)).text
    entries = parse_atom(xml)
    st["i"] = i + 1
    if deep:
        offsets[cat] = start + len(entries)
        if not entries:
            st.setdefault("finished", [])
            if cat not in st["finished"]:
                st["finished"].append(cat)
        st["done"] = len(st.get("finished", [])) >= len(cats)
    out = []
    for e in entries:
        if e.arxiv_id in seen or len(out) >= want:
            continue
        pdf = fetch(e.pdf).content
        out.append(Doc(e.arxiv_id, domain, e.title, f"arxiv:{e.arxiv_id}", catalogue()["licences"]["arxiv"],
                       f"https://arxiv.org/abs/{e.arxiv_id}", name=f"{e.arxiv_id.replace('/', '_')}.pdf", data=pdf))
    return out


def _zip_dir(cfg) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "harvest" / "normattiva"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normattiva(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
    """`want` acts per call, collection after collection (the in-force text when Normattiva has it)."""
    cols = spec.get("collections", [])
    out: list[Doc] = []
    while len(out) < want:
        ci = st.get("collection", 0)
        if ci >= len(cols):
            st["done"] = True
            break
        name = cols[ci]
        path = _zip_dir(cfg) / (re.sub(r"\W+", "_", name) + ".zip")
        if not path.exists():
            data = b""
            for vig in ("V", "O"):                               # in force first, else as published
                try:
                    data = fetch(NORMATTIVA, nome=name, formato="AKN", formatoRichiesta=vig).content
                    if data[:2] == b"PK":
                        break
                except httpx.HTTPStatusError as e:                # 400: not in this form; anything else
                    if e.response.status_code != 400:             # (network, TLS, 5xx) is retried next round,
                        raise                                     # never taken for a missing collection
                    data = b""
            if data[:2] != b"PK":
                st["collection"], st["member"] = ci + 1, 0
                st.setdefault("missing", []).append(name)
                continue
            path.write_bytes(data)
        z = zipfile.ZipFile(path)
        members = sorted(n for n in z.namelist() if n.endswith(".xml"))
        mi = st.get("member", 0)
        while mi < len(members) and len(out) < want:
            try:
                title, urn, arts = akn_articles(z.read(members[mi]))
            except ET.ParseError:
                arts, urn, title = [], "", ""
            mi += 1
            key = f"normattiva:{urn or members[mi - 1]}"
            if not arts or key in seen:
                continue
            out.append(Doc(key, domain, title, key, catalogue()["licences"]["normattiva"],
                           f"https://www.normattiva.it/uri-res/N2Ls?{urn}" if urn else "https://www.normattiva.it",
                           passages=pack(title, arts, cfg["AURORA_CHUNK_CHARS"], cfg["AURORA_CHUNK_MIN_CHARS"]),
                           lang="it"))
        st["member"] = mi
        if mi >= len(members):
            st["collection"], st["member"] = ci + 1, 0
            path.unlink(missing_ok=True)                          # done with it: no 100 MB left behind
    return out


def europepmc(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
    q = f"OPEN_ACCESS:y AND HAS_FT:y AND {spec['query']}"
    cursor = st.get("cursor", "*") if deep else "*"
    r = fetch(f"{EPMC}/search", query=q, resultType="core", format="json", pageSize=max(want * 2, 25),
              sort="P_PDATE_D desc", cursorMark=cursor).json()
    hits = r.get("resultList", {}).get("result", [])
    if deep:
        nxt = r.get("nextCursorMark")
        st["done"] = not hits or not nxt or nxt == cursor
        st["cursor"] = nxt or cursor
    out = []
    for h in hits:
        pmc = h.get("pmcid")
        if not pmc or pmc in seen or len(out) >= want:
            continue
        try:
            title, text = jats_text(fetch(f"{EPMC}/{pmc}/fullTextXML").content)
        except Exception:                                         # noqa: BLE001 - one bad paper never stops a round
            continue
        if len(text) < 500:
            continue
        out.append(Doc(pmc, domain, title or h.get("title", pmc), f"europepmc:{pmc}", h.get("license") or "open access",
                       f"https://europepmc.org/article/PMC/{pmc}", name=f"{pmc}.txt", data=text.encode()))
    return out


def rxiv(server: str):
    def source(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
        """One page per call of one category (rotating). The API lists oldest first: a round looks at the last
        week, "until exhausted" walks everything since 2013."""
        cats = spec.get("categories") or [""]
        i = st.get("i", 0)
        if deep and i >= len(cats):
            st["done"] = True
            return []
        cat = cats[i % len(cats)]
        today = dt.date.today()
        since = "2013-01-01" if deep else (today - dt.timedelta(days=7)).isoformat()
        cursor = st.get("cursor", 0) if deep else 0
        r = fetch(f"https://api.biorxiv.org/details/{server}/{since}/{today.isoformat()}/{cursor}",
                  **({"category": cat.replace(" ", "_")} if cat else {})).json()
        col = r.get("collection", [])
        total = int((r.get("messages") or [{}])[0].get("total") or 0)
        out = []
        for d in col:
            key = f"{server}:{d['doi']}"
            if key in seen or len(out) >= want or not d.get("jatsxml"):
                continue
            try:
                title, text = jats_text(fetch(d["jatsxml"]).content)
            except Exception:                                     # noqa: BLE001 - one bad preprint never stops a round
                continue
            if len(text) < 500:
                continue
            out.append(Doc(key, domain, title or d.get("title", ""), key, d.get("license") or "see the preprint",
                           f"https://doi.org/{d['doi']}", name=re.sub(r"\W+", "_", d["doi"]) + ".txt",
                           data=text.encode()))
        if deep:
            cursor += len(col)
            if not col or cursor >= total:
                st["i"], st["cursor"] = i + 1, 0
                st["done"] = st["i"] >= len(cats)
            else:
                st["cursor"] = cursor
        else:
            st["i"] = i + 1
        return out
    return source


def wikipedia(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
    if "titles" not in st:
        titles: list[str] = []
        for page in spec.get("lists", []):
            cont: dict = {}
            while True:
                r = fetch(WIKI, action="query", titles=page, redirects=1, prop="links", plnamespace=0, pllimit="max",
                          format="json", **cont).json()
                for p in r.get("query", {}).get("pages", {}).values():
                    titles += [x["title"] for x in p.get("links", []) if x["title"] not in titles]
                if "continue" not in r:
                    break
                cont = r["continue"]
        st["titles"], st["pos"] = titles, 0
    titles, out = st["titles"], []
    while st["pos"] < len(titles) and len(out) < want:
        t = titles[st["pos"]]
        st["pos"] += 1
        key = f"wikipedia:{t}"
        if key in seen:
            continue
        r = fetch(WIKI, action="query", prop="extracts", explaintext=1, titles=t, redirects=1, format="json").json()
        page = next(iter(r.get("query", {}).get("pages", {}).values()), {})
        text = page.get("extract", "")
        if len(text) < 500:
            continue
        cut = re.split(r"\n== (See also|References|Notes|Further reading|External links|Bibliography) ==", text)[0]
        out.append(Doc(key, domain, page.get("title", t), key, catalogue()["licences"]["wikipedia"],
                       "https://en.wikipedia.org/wiki/" + page.get("title", t).replace(" ", "_"),
                       name=re.sub(r"\W+", "_", t)[:80] + ".txt", data=cut.encode()))
    st["done"] = st["pos"] >= len(titles)
    return out


def github(fetch: Fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list[Doc]:
    topics = spec.get("topics", [])
    if not topics:
        st["done"] = True
        return []
    i = st.get("i", 0) % len(topics)
    pages = st.setdefault("pages", {})
    page = pages.get(topics[i], 1) if deep else 1
    r = fetch("https://api.github.com/search/repositories", q=f"topic:{topics[i]} stars:>300", sort="stars",
              per_page=30, page=page).json()
    items = r.get("items", [])
    st["i"] = i + 1
    if deep:
        pages[topics[i]] = page + 1
        if not items or page >= 33:                                # the search API stops at 1000 results
            st.setdefault("finished", [])
            if topics[i] not in st["finished"]:
                st["finished"].append(topics[i])
        st["done"] = len(st.get("finished", [])) >= len(topics)
    out = []
    for it in items:
        lic = (it.get("license") or {}).get("spdx_id") or ""
        key = f"github:{it['full_name']}"
        if lic not in OPEN_LICENCES or key in seen or len(out) >= want or it.get("archived") or it.get("fork"):
            continue
        for readme in ("README.md", "readme.md", "README.rst", "README"):
            try:
                resp = fetch(f"https://raw.githubusercontent.com/{it['full_name']}/{it['default_branch']}/{readme}")
            except Exception:                                      # noqa: BLE001 - try the next spelling
                continue
            text = resp.text
            if len(text) > 800:
                out.append(Doc(key, domain, f"{it['full_name']}: {it.get('description') or ''}".strip(": "), key, lic,
                               it["html_url"], name=re.sub(r"\W+", "_", it["full_name"]) + ".md", data=text.encode()))
            break
    return out


SOURCES = {"arxiv": arxiv, "normattiva": normattiva, "europepmc": europepmc, "biorxiv": rxiv("biorxiv"),
           "medrxiv": rxiv("medrxiv"), "wikipedia": wikipedia, "github": github}
