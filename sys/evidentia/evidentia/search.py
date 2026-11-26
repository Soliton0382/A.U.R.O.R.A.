# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Reading the archive, read-only, with fixed parameterized queries (CLAUDE.md: never SQL written by a model). The words
of a search are turned into FTS5 terms here — quoted, so that no operator of FTS5 can be smuggled in."""
from __future__ import annotations

import re
import sqlite3
import time

from . import docids

MAX = 50


def fts_query(words: str) -> str:
    """«Wuhan pallet» → '"wuhan" "pallet"'; a phrase in quotes stays a phrase; nothing else of FTS5's syntax passes."""
    phrases = re.findall(r'"([^"]+)"', words)
    rest = re.sub(r'"[^"]*"', " ", words)
    terms = [p for p in (re.sub(r"[^\w\-.@]", " ", t).strip() for t in phrases) if p] + \
            [t for t in re.findall(r"[\w\-.@]+", rest) if len(t) > 1]
    return " ".join('"' + t.replace('"', "") + '"' for t in terms[:16])


# a question in words (owner, 10 Nov: «Cerca Soros e le sue relazioni» → nothing: every word was required, Italian
# ones too, in English documents): the words that ask, not what is asked, are left out
ASKING = set("""cerca cercami trova trovami mostra mostrami dimmi dammi elenca chi cosa che quali quale quando dove come
perché perche sono era erano sulle sulla sullo sui sul delle della dello degli dei del alle alla allo agli ai al nelle
nella negli nei nel con per tra fra una uno un il lo la gli le i e o ed di da in a su mi ti si ci vi suo sua suoi sue
loro tutto tutti tutte ogni anche ancora relazioni relazione legami legame rapporti rapporto collegamenti contatti
documenti documento file informazioni notizie the a an of and or to in on at by for with from about what who whom
which when where how why find show tell me list all any his her their its is are was were be been relations
relationship relationships ties links connections documents information""".split())


def terms(question: str) -> list[str]:
    """The words of a question that are asked about: names, numbers, the rest of the content."""
    phrases = re.findall(r'"([^"]+)"', question)
    rest = re.sub(r'"[^"]*"', " ", question)
    words = [w for w in re.findall(r"[\w\-.@]+", rest) if len(w) > 1 and w.lower() not in ASKING]
    return [f'"{p}"' for p in phrases] + words


TERMS_MAX = 16      # the words of one question looked for (audit E6, B21: «any» ran one query a word, ~100 of them)
BUDGET_S = 15.0     # one question's time on the archive, then what was found so far (not measured on the whole archive)
TICK = 20_000       # SQLite's steps between two looks at the clock


def ask(corpus, question: str, limit: int = 20, offset: int = 0, budget_s: float = BUDGET_S) -> dict:
    """The search behind the chat: all the words that matter; nothing found → only the names and the numbers; still
    nothing → any of the words, best first. It says which words it used and how many passages there are in all.
    At most TERMS_MAX words and BUDGET_S seconds: past it SQLite is interrupted and the answer says «partial»."""
    deadline = time.monotonic() + budget_s
    corpus.set_progress_handler(lambda: time.monotonic() > deadline, TICK)
    got: dict = {}
    try:
        return _ask(corpus, terms(question)[:TERMS_MAX], limit, offset, got)
    except sqlite3.OperationalError as e:
        if "interrupt" not in str(e):
            raise
        return {**got, "hits": got.get("hits", []), "used": got.get("used", ""), "total": len(got.get("hits", [])),
                "cap": COUNT_CAP, "mode": got.get("mode", "all"), "partial": True}
    finally:
        corpus.set_progress_handler(None, 0)


def _ask(corpus, ts: list[str], limit: int, offset: int, got: dict) -> dict:
    tries = [" ".join(ts)]
    strong = [w for w in ts if w[:1].isupper() or any(c.isdigit() for c in w) or w.startswith('"')]
    if strong and len(strong) < len(ts):
        tries.append(" ".join(strong))
    for words in tries:
        hits = search(corpus, words, limit, offset)
        if hits:
            got.update(hits=hits, used=words, mode="all")      # what a late count still returns
            return {"hits": hits, "used": words, "total": total(corpus, words), "cap": COUNT_CAP, "mode": "all"}
    if len(ts) > 1:                                           # any of the words: each one alone, best of each
        seen, hits = set(), []
        for w in ts:
            for h in search(corpus, w, max(5, limit // len(ts)), offset):
                if (h["doc"], h["page"]) not in seen:
                    seen.add((h["doc"], h["page"]))
                    hits.append(h)
            got.update(hits=hits[:limit], used=" | ".join(ts), mode="any")
        if hits:
            return {"hits": hits[:limit], "used": " | ".join(ts), "total": len(hits), "cap": COUNT_CAP, "mode": "any"}
    return {"hits": [], "used": " ".join(ts), "total": 0, "cap": COUNT_CAP, "mode": "all"}


COUNT_CAP = 10_000           # the total is counted up to here, «more than» beyond: 100,000 «Rossi» took 9 s (I10)


def total(corpus, words: str) -> int:
    """How many passages match, up to COUNT_CAP (the chat says «N in all, shown 20»: owner, 10 Nov, «la ricerca deve
    essere completa»)."""
    q = fts_query(words)
    if not q:
        return 0
    return corpus.execute("SELECT COUNT(*) FROM (SELECT 1 FROM passages_fts WHERE passages_fts MATCH ? LIMIT ?)",
                          (q, COUNT_CAP)).fetchone()[0]


def search(corpus, words: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """The best passages; the same passage released again under another number (the collections hold copies: the
    same e-mail in two releases) is one hit, its other places in «copies» (found testing, 10 Nov)."""
    q = fts_query(words)
    if not q:
        return []
    limit = max(1, min(int(limit), MAX))                 # a negative LIMIT is no limit in SQLite (audit, 10 Nov)
    offset = max(0, min(int(offset), OFFSET_MAX))
    want = offset + limit                                # the pages are of results, not of passages (B29): the copies
    rows = corpus.execute(
        "SELECT p.doc, p.page, p.text, snippet(passages_fts, 0, '«', '»', ' … ', 24) AS snip, bm25(passages_fts) AS score "
        "FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid WHERE passages_fts MATCH ? "
        "ORDER BY score LIMIT ?", (q, want * 3)).fetchall()             # of page 1 never come back on page 3
    out, kept = [], []
    for r in rows:
        words = _words(r["text"])
        twin = next((h for h, w in kept if (h["doc"], h["page"]) == (r["doc"], r["page"]) or _same(w, words)), None)
        if twin is not None:                       # a second passage of the same page, or the same text again
            if (twin["doc"], twin["page"]) != (r["doc"], r["page"]):
                twin["copies"].append(cite(r["doc"], r["page"]))
            else:                                  # said, not dropped in silence (B18): the page has it more than once
                twin["passages"] = twin.get("passages", 1) + 1
            continue
        if len(out) == want:
            continue
        hit = {"doc": r["doc"], "page": r["page"], "snippet": r["snip"], "cite": cite(r["doc"], r["page"]), "copies": []}
        kept.append((hit, words))
        out.append(hit)
    return out[offset:]


OFFSET_MAX = 1000    # the results a client may page through: (1000 + 50) × 3 passages read at most


COPY = 0.8     # two passages sharing 80 % of their words are one text read twice (the e-mail of 9 Feb 2015 in two
#                releases: 0.84; two different e-mails on the same aircraft: 0.08 — measured 10 Nov)


def _words(text: str) -> frozenset[str]:
    """A passage's words without the numbers a release stamps on it (ABC0001234, ABC_R1_0005678)."""
    t = re.sub(r"\b[A-Z][A-Z0-9_-]*\d{5,}\b", " ", text or "")
    return frozenset(w for w in re.findall(r"\w+", t.casefold()) if len(w) > 2)


def _numbers(words: frozenset) -> frozenset:
    return frozenset(w for w in words if any(c.isdigit() for c in w))


def _same(a: frozenset, b: frozenset) -> bool:
    """One text read twice: most words shared AND the very same numbers (audit E3, B18: two payment notices on the
    same form, same payee, another amount, shared 80 % of their words and one of them vanished from the search)."""
    return bool(a and b) and _numbers(a) == _numbers(b) and len(a & b) / len(a | b) >= COPY


def cite(doc_key: str, page: int | None = None) -> str:
    collection, number = doc_key.split(":", 1)
    return docids.cite(docids.DocId(collection, number), page)


def page(corpus, doc_key: str, n: int) -> dict | None:
    r = corpus.execute("SELECT text, chars, source FROM pages WHERE doc = ? AND page = ?", (doc_key, int(n))).fetchone()
    return None if r is None else {"doc": doc_key, "page": int(n), "text": r["text"], "source": r["source"],
                                   "cite": cite(doc_key, int(n))}


def document(corpus, doc_key: str) -> dict | None:
    r = corpus.execute("SELECT doc, collection, number, pages, kind, official_url, status FROM documents WHERE doc = ?",
                       (doc_key,)).fetchone()
    return None if r is None else dict(r)


def same_identifier(findings, kind: str, value: str, limit: int = 100) -> list[dict]:
    """Where else the very same identifier appears (a strong link only when it passed its check)."""
    rows = findings.execute("SELECT doc, page, valid FROM identifiers WHERE kind = ? AND value = ? LIMIT ?",
                            (kind, value, max(1, min(int(limit), 500)))).fetchall()
    return [dict(r) | {"cite": cite(r["doc"], r["page"])} for r in rows]
