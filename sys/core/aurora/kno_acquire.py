# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Acquire missing knowledge from arXiv, iteratively, until the question is answerable.

One round (M22 measured that a single round finds the source 1 time in 17):
 1. the reasoner writes AURORA_ARXIV_QUERIES new English queries, knowing the
    queries and titles of the previous rounds;
 2. arXiv returns AURORA_ARXIV_RESULTS entries per query (title + abstract);
 3. the re-ranker orders every unseen entry against the question;
 4. the best AURORA_ARXIV_PAPERS PDFs are imported into the domain of their
    primary category (config/arxiv_domains.json), chunked and indexed;
 5. the answer pipeline runs again: an answer (gate open) ends the search.
There is no score threshold: nothing measured supports one yet.

Only the queries leave the machine; arXiv is asked no more than once every
AURORA_ARXIV_DELAY_S seconds, as its terms of use require.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import kno_arxiv, sys_config, sys_log, txt_lang
from .kno_ingest import Importer

MAP_FILE = Path(__file__).resolve().parents[1] / "config" / "arxiv_domains.json"
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

SYS_QUERIES = ("You write search queries for the arXiv search engine. Given a question and the queries already "
               "tried, write {n} NEW English queries, one per line, 2 to 6 keywords each, no quotes, no numbering, "
               "no boolean operators. Vary the wording: synonyms, the technical name of the concept, the likely "
               "title of a paper that answers.")
SYS_ORIGIN = ("If the question is about a named method, model or result, write the exact title of the paper that "
              "introduced it, on one line, nothing else. If you are not sure, or it is not about a named method, write NONE.")


def _words(title: str) -> set[str]:
    return set(re.sub(r"[^\w\s]", " ", title.lower()).split())


def same_title(a: str, b: str) -> bool:
    """Jaccard of the words >= 0.8: a shortened or invented title must not import another paper (M33)."""
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.8


@dataclass
class Entry:
    arxiv_id: str
    title: str
    abstract: str
    category: str
    pdf: str
    score: float = 0.0
    source: str = "arxiv"                 # beyond arXiv (kno_acquire_more): where it comes from
    fetch: object = None                  # () -> (file name, data, licence, url), for a source other than arXiv


def domain_of(category: str, table: dict[str, str]) -> str:
    if category in table:
        return table[category]
    return table.get(category.split(".")[0] + ".*", "general")


def parse_atom(xml: str) -> list[Entry]:
    out = []
    for e in ET.fromstring(xml).findall("a:entry", ATOM):
        raw_id = e.findtext("a:id", "", ATOM).rsplit("/abs/", 1)[-1]
        if not raw_id:
            continue
        pdf = next((l.get("href") for l in e.findall("a:link", ATOM) if l.get("title") == "pdf"),
                   f"https://arxiv.org/pdf/{raw_id}")
        prim = e.find("arxiv:primary_category", ATOM)
        out.append(Entry(arxiv_id=re.sub(r"v\d+$", "", raw_id),
                         title=" ".join(e.findtext("a:title", "", ATOM).split()),
                         abstract=" ".join(e.findtext("a:summary", "", ATOM).split()),
                         category=prim.get("term", "") if prim is not None else "",
                         pdf=pdf.replace("http://", "https://", 1)))      # arXiv serves HTTPS: never in clear
    return out


class ArxivAgent:
    def __init__(self, pipeline, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.p = pipeline
        self.importer = Importer(pipeline.writer, pipeline.indexer, self.cfg)
        self.table = json.loads(MAP_FILE.read_text(encoding="utf-8"))["map"]
        self.http = httpx.Client(timeout=120, follow_redirects=True,
                                 headers={"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal knowledge agent)"})
        # Wikimedia refuses a user agent without a way to reach its author (403): the harvester's own
        self.log = sys_log.get_logger("acquire")
        self._last_call = 0.0
        self.more = [s.strip() for s in str(self.cfg["AURORA_ACQUIRE_SOURCES"]).split(",") if s.strip() in more.SEARCH]
        self._other_last = 0.0

    def _get(self, url: str, **params) -> httpx.Response:
        """The other sources: one call a second at most (they ask for no delay; arXiv's own rule stays its own)."""
        wait = self._other_last + 1.0 - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.http.get(url, params=params or None)
        finally:
            self._other_last = time.time()
        r.raise_for_status()
        return r

    def _polite_get(self, url: str, **params) -> httpx.Response:
        wait = self._last_call + self.cfg["AURORA_ARXIV_DELAY_S"] - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.http.get(url, params=params or None)
        finally:
            self._last_call = time.time()
        r.raise_for_status()
        return r

    def _original(self, english: str, emit) -> Entry | None:
        """Ask the reasoner for the title of the paper that introduced the method asked about, and keep it only
        if arXiv has a paper with that same title. M33: originals among the candidates 4/12 → 8/12."""
        title = self.p.llm.complete(SYS_ORIGIN, english, 40).answer.strip().splitlines()[0].strip().strip('"')
        if title.upper().startswith("NONE") or len(title.split()) > 20 or "*" in title or len(title) < 8:
            return None
        try:
            xml = self._polite_get(self.cfg["AURORA_ARXIV_API"], search_query=f'ti:"{" ".join(re.sub(r"[^\w\s]", " ", title).split())}"',
                                   start=0, max_results=5).text
        except httpx.HTTPError as e:
            emit("acquire.error", {"stage": "original", "message": str(e)})
            return None
        match = next((e for e in parse_atom(xml) if same_title(title, e.title)), None)
        emit("acquire.original", {"title": title, "found": match.arxiv_id if match else None})
        if match:
            match.score = 1.0
        return match

    def _queries(self, question: str, tried: list[str], titles: list[str]) -> list[str]:
        n = self.cfg["AURORA_ARXIV_QUERIES"]
        user = f"QUESTION: {question}\n"
        if tried:
            user += "QUERIES ALREADY TRIED:\n" + "\n".join(tried) + "\n"
        if titles:
            user += "PAPERS ALREADY READ (they did not answer):\n" + "\n".join(titles[-30:]) + "\n"
        out = self.p.llm.complete(SYS_QUERIES.format(n=n), user, 200).answer
        qs = [re.sub(r"^[\s\-*\d.)]+", "", l).strip().strip('"') for l in out.splitlines()]
        return [q for q in qs if q and q.lower() not in {t.lower() for t in tried}][:n]

    def run(self, question: str, emit, run_id: str, remember: bool = True, min_score: float = 0.0):
        """The final Answer of the pipeline, answered or still abstained; only this outcome is remembered,
        with the whole path of the search."""
        from .kno_answer import Trail
        from .sol_schema import now_iso
        trail, outer, asked_at = Trail(), emit, now_iso()

        def emit(event, payload):
            trail.add(event, payload)
            outer(event, payload)
        lang = txt_lang.detect(question)
        english = question if lang == "en" else self.p.llm.complete(
            "Translate the user's text to English. Reply with the translation only.", question, 200).answer
        tried, seen, read_titles, last = [], set(), [], None
        origin = self._original(english, emit)            # the paper that introduced a named method, if any
        for rnd in range(1, self.cfg["AURORA_ARXIV_ROUNDS"] + 1):
            queries = self._queries(english, tried, read_titles)
            tried += queries
            emit("acquire.round", {"round": rnd, "queries": queries})
            fresh: dict[str, Entry] = {}
            for q in queries:
                try:
                    xml = self._polite_get(self.cfg["AURORA_ARXIV_API"], search_query=f"all:{q}", start=0,
                                           max_results=self.cfg["AURORA_ARXIV_RESULTS"]).text
                except httpx.HTTPError as e:
                    emit("acquire.error", {"stage": "search", "query": q, "message": str(e)})
                    xml = ""
                for en in parse_atom(xml) if xml else []:
                    if en.arxiv_id not in seen:
                        fresh.setdefault(en.arxiv_id, en)
                for name in self.more:                    # the other sources, the same query (owner, 2026-10-04)
                    try:
                        for en in more.SEARCH[name](self._get, q, self.cfg["AURORA_ARXIV_RESULTS"]):
                            if en.arxiv_id not in seen:
                                fresh.setdefault(en.arxiv_id, en)
                    except Exception as e:  # noqa: BLE001 — one source down never stops the search
                        emit("acquire.error", {"stage": "search", "source": name, "query": q, "message": str(e)[:200]})
            seen.update(fresh)
            entries = list(fresh.values())
            if entries:
                scores = self.p.search.reranker.score([(english, f"{e.title}. {e.abstract}") for e in entries])
                for e, s in zip(entries, scores):
                    e.score = float(s)
                entries.sort(key=lambda e: e.score, reverse=True)
            if origin and rnd == 1:                       # the original comes before its derivatives (A9, M33)
                entries = [origin] + [e for e in entries if e.arxiv_id != origin.arxiv_id]
                seen.add(origin.arxiv_id)
            emit("acquire.candidates", {"round": rnd, "count": len(entries),
                                        "top": [{"id": e.arxiv_id, "title": e.title, "score": round(e.score, 3),
                                                 "category": e.category} for e in entries[:10]]})
            imported = 0
            for e in [x for x in entries if x.score >= min_score][:self.cfg["AURORA_ARXIV_PAPERS"]]:   # the night is pickier
                read_titles.append(e.title)
                try:
                    if e.source == "arxiv":
                        domain = domain_of(e.category, self.table)
                        name, data = kno_arxiv.paper(e.arxiv_id, e.pdf, self._polite_get)   # HTML first (C137)
                        rep = self.importer.add(name, data, domain, title=e.title,
                                                origin=f"arxiv:{e.arxiv_id}", run_id=run_id)
                    else:                                 # chosen among all the sources: its domain, its licence
                        name, data, lic, url = e.fetch()
                        domain = more.choose_domain(self.p.llm, e.source, english, e.title)
                        rep = self.importer.add(name, data, domain, title=e.title, origin=e.arxiv_id, run_id=run_id,
                                                meta={"licence": lic, "url": url})
                except (httpx.HTTPError, ValueError) as err:
                    emit("acquire.error", {"stage": "import", "id": e.arxiv_id, "message": str(err)})
                    continue
                imported += rep.written
                emit("acquire.paper", {"id": e.arxiv_id, "title": e.title, "domain": domain, "chunks": rep.chunks,
                                       "written": rep.written, "score": round(e.score, 3)})
            if not imported:
                continue                                  # nothing new in the vault: asking again changes nothing
            last = self.p.run(question, emit=emit, run_id=run_id, remember=False)
            if not last.abstained:
                emit("acquire.done", {"round": rnd, "found": True, "papers": len(read_titles)})
                if remember:                              # the night's study keeps its own record (kno_study)
                    self.p.remember(question, last, run_id, emit, trail, asked_at)
                return last
        emit("acquire.done", {"round": self.cfg["AURORA_ARXIV_ROUNDS"], "found": False, "papers": len(read_titles)})
        self.log.info("acquire %s: not found after %d queries, %d papers read", run_id, len(tried), len(read_titles))
        if last is None:
            last = self.p.run(question, emit=emit, run_id=run_id, remember=False)
        if remember:
            self.p.remember(question, last, run_id, emit, trail, asked_at)
        return last


from . import kno_acquire_more as more  # noqa: E402 — at the end: it uses Entry, defined above
