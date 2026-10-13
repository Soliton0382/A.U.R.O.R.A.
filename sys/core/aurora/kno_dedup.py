# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One document, one copy in the vault (owner, 2026-10-05: "the vault is the base, it must be solid").

The vault already refuses a passage whose text is identical (content hash). It did not see the same document come
again in another form — the PDF of a paper and later its HTML, an article of the previous installation and the same
one from the harvester — because the passages are cut differently: measured, 76 such documents in 672,423 passages
(1,732 passages), removed (M109). Here a document is recognised before it is written:
- the same title (normalised, at least 12 characters), in the same language — Wikipedia's English and Italian
  articles share a title and are both kept;
- and the same content: a bottom-k signature of its words (the 32 smallest hashes of the words of its first
  passages; the share of the union's smallest hashes found in both estimates the overlap of the word sets).
Measured on the 126 groups of same-titled documents: true copies share 67-99% of their words, different documents
with one title 1-37% — the threshold 0.5 sits in between.
The signatures of the whole knowledge are built once per process (a few seconds), then kept up to date on imports.
"""
from __future__ import annotations

import hashlib
import re
import threading

from . import sys_config

K, SAME, SAME_SHORT = 32, 0.5, 0.7
# an official identity: two documents that both have one, different, are two documents — Normattiva has hundreds of
# acts with one title and nearly one text ("Modificazioni allo statuto dell'Università di Roma", 226 acts): without
# this rule 38,625 pairs of distinct acts looked like copies (measured before switching the check on)
OFFICIAL = ("normattiva:", "arxiv:", "europepmc:", "pmc", "biorxiv:", "medrxiv:", "github:", "wikipedia:", "docs:", "doi:")


_LEGACY_WIKI = re.compile(r"^legacy:wiki_(.+?)(?:_txt_done|_done)?$")


def official(origin: str) -> str:
    """The document's official identity, or "": the v1 Wikipedia articles («legacy:wiki_Karl_Marx_txt_done») are
    «wikipedia:Karl Marx», as the v2 harvester names them (13 Oct: 8 such articles were in the vault twice)."""
    o = origin or ""
    m = _LEGACY_WIKI.match(o)
    if m:
        return "wikipedia:" + m.group(1).replace("_", " ").strip()
    return o if o.lower().startswith(OFFICIAL) else ""


def scheme(identity: str) -> str:
    """The archive of an identity: «arxiv», «biorxiv», «normattiva», «wikipedia»… — a preprint posted on two archives
    (13 Oct: one paper on bioRxiv and on arXiv, in two domains) is one document, two acts of Normattiva are two."""
    return identity.split(":", 1)[0].lower()


def same_identity(a: str, b: str) -> bool:
    return bool(a) and a.lower() == b.lower()
_lock = threading.Lock()
_index: dict[str, dict[str, list]] = {}          # root -> title key -> [(domain, source_id, lang, signature)]


def title_key(title: str) -> str:
    t = re.sub(r"\W+", " ", (title or "").lower()).strip()
    return t if len(t) >= 4 else ""


def signature(text: str) -> list[int]:
    words = set(re.findall(r"[a-zà-ÿ]{4,}", (text or "").lower()))
    return sorted(int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big") for w in words)[:K]


def similarity(a: list[int], b: list[int]) -> float:
    if not a or not b:
        return 0.0
    union = sorted(set(a) | set(b))[:K]
    both = set(a) & set(b)
    return sum(1 for h in union if h in both) / len(union)


def _build(cfg: sys_config.Config, reader) -> dict[str, list]:
    first: dict[tuple, list] = {}
    meta: dict[tuple, tuple] = {}
    for dom in reader.layout.domains("knowledge"):
        for _k, _r, s in reader.iter_domain(dom):
            key = title_key(s.title)                      # "" too: a document without a title has its identity
            if s.chunk_index < 3:                         # the first passages carry the document's words
                first.setdefault((dom, s.source_id), []).append(s.text)
                meta[(dom, s.source_id)] = (key, s.lang, official(str((s.extra or {}).get("origin") or s.source_id)))
    out: dict[str, list] = {}
    for (dom, src), texts in first.items():
        key, lang, origin = meta[(dom, src)]
        out.setdefault(key, []).append((dom, src, lang, signature(" ".join(texts)), origin))
    return out


def find(cfg: sys_config.Config, reader, title: str, lang: str, first_text: str, origin: str = "") -> tuple[str, str] | None:
    """(domain, source_id) of the document already in the vault that this one copies, or None. The same official
    identity (an arXiv id, a Wikipedia article, a PMC id…) is the same document whatever its title, text or domain:
    an arXiv paper taken once as HTML and once as PDF shared under half its words and went in twice, in two domains
    (13 Oct); a short title («Karl Marx», 9 characters) was not looked at."""
    root = str(cfg.root)
    mine = official(origin)
    with _lock:
        if root not in _index:
            _index[root] = _build(cfg, reader)
        if mine:
            for entries in _index[root].values():
                for dom, src, _lg, _sig, theirs in entries:
                    if same_identity(mine, theirs) or same_identity(mine, official(src)):
                        return dom, src
        key = title_key(title)
        known = list(_index[root].get(key, [])) if key else []
    sig = signature(first_text)
    need = SAME if len(key) >= 12 else SAME_SHORT      # a short title is often a generic one: more words in common
    for dom, src, lg, other, theirs in known:
        if mine and theirs and mine != theirs and scheme(mine) == scheme(theirs):
            continue                                  # two identities of one archive (two Normattiva acts): two documents
        if lg == lang and similarity(sig, other) >= need:     # across archives (bioRxiv and arXiv) the text decides
            return dom, src
    return None


def remember(cfg: sys_config.Config, title: str, domain: str, source_id: str, lang: str, first_text: str,
             origin: str = "") -> None:
    key = title_key(title)
    root = str(cfg.root)
    with _lock:
        if key and root in _index:
            _index[root].setdefault(key, []).append((domain, source_id, lang, signature(first_text), official(origin)))


def known(cfg: sys_config.Config, reader, origin: str) -> tuple[str, str] | None:
    """(domain, source_id) of a document already in the vault with this official identity, or None: the check of a
    document sent as ready passages (POST /v1/aurora/solitons: Normattiva's articles, the migration) — one ingest
    rule for every way in."""
    mine = official(origin)
    if not mine:
        return None
    root = str(cfg.root)
    with _lock:
        if root not in _index:
            _index[root] = _build(cfg, reader)
        for entries in _index[root].values():
            for dom, src, _lg, _sig, theirs in entries:
                if same_identity(mine, theirs) or same_identity(mine, official(src)):
                    return dom, src
    return None

