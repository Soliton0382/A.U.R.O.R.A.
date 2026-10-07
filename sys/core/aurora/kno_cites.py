# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The provisions a lawyer would read, fetched by their number (C183).

A case told in everyday words («allacci ai box», «contalitri») does not sound like the law that governs it, and the
search never brought the civil code's condominium articles to the owner's real case. The local model knows which
provisions to read (it named art. 1117, 1123, 1136, 1138 c.c.); it is used only as a pointer: each provision is
looked up by its number in the vault's Normattiva passages (an indexed lookup, ~5 ms) and its TEXT is what the gate,
the extraction and the verification read — never the model's memory of it. A provision not in the vault is dropped.
"""
from __future__ import annotations

import re
import sqlite3

SYS_CITES = ("List the legal provisions a lawyer would read first for this situation: at most 6, the most relevant, "
             "each as «art. N <act>» with the act's usual name (codice civile, codice penale, codice di procedura "
             "civile, d.lgs. N/YYYY, d.P.R. N/YYYY, legge N/YYYY, d.l. N/YYYY). Only provisions you are sure exist. One "
             "per line, nothing else.")

# the codes by name; the other acts by their kind, number and year (Normattiva's URN)
CODES = {
    "codice civile": "normattiva:urn:nir:stato:regio.decreto:1942-03-16;262", "c.c.": "normattiva:urn:nir:stato:regio.decreto:1942-03-16;262",
    "codice penale": "normattiva:urn:nir:stato:regio.decreto:1930-10-19;1398", "c.p.": "normattiva:urn:nir:stato:regio.decreto:1930-10-19;1398",
    "codice di procedura civile": "normattiva:urn:nir:stato:regio.decreto:1940-10-28;1443",
    "c.p.c.": "normattiva:urn:nir:stato:regio.decreto:1940-10-28;1443",
    "codice di procedura penale": "normattiva:urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447",
    "c.p.p.": "normattiva:urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447",
}
KINDS = [(r"d\.?\s*lgs\.?|decreto legislativo", "decreto.legislativo"),
         (r"d\.?\s*p\.?\s*r\.?|decreto del presidente della repubblica", "decreto.del.presidente.della.repubblica"),
         (r"d\.?\s*l\.?|decreto[- ]legge", "decreto.legge"),
         (r"r\.?\s*d\.?|regio decreto", "regio.decreto"),
         (r"l\.?|legge", "legge")]
_ART = re.compile(r"(?i)^\s*art(?:icolo|\.)?\s*(\d+(?:\s*-?\s*(?:bis|ter|quater|quinquies|sexies|septies|octies))?)\s*,?\s*(?:del(?:la|l')?\s+)?(.+?)\s*$")


def parse(line: str) -> tuple[str, str] | None:
    """«art. 1117-bis c.c.» → ("1117-bis", source pattern); None when the act is not recognised."""
    m = _ART.match(line.strip(" -•*«»\"'"))
    if not m:
        return None
    n = re.sub(r"\s*-?\s*(bis|ter|quater|quinquies|sexies|septies|octies)$", r"-\1", m.group(1).lower().replace(" ", ""))
    act = m.group(2).lower().strip(" .;")
    for name, urn in sorted(CODES.items(), key=lambda kv: -len(kv[0])):
        if act == name or act.startswith(name + " ") or act == name.rstrip("."):
            return n, urn
    for rx, kind in KINDS:
        k = re.match(rf"(?:{rx})\s*(?:n\.?\s*)?(\d+)\s*/\s*(\d{{4}})", act)
        if k:
            return n, f"normattiva:urn:nir:stato:{kind}:{k.group(2)}-%;{k.group(1)}"
    return None


def lookup(reader, number: str, source: str, limit: int = 2) -> list[str]:
    """The sids of the passages that hold «Art. N.» of that act, its heading first (case-sensitive: a mention of
    «art. N» inside another article is not the article)."""
    out: list[str] = []
    for shard in reader.layout.shards("knowledge", "law_it"):
        con = sqlite3.connect(f"file:{shard}?mode=ro", uri=True)
        try:
            op = "LIKE" if "%" in source else "="
            rows = con.execute(f"SELECT sid, text FROM solitons WHERE source_id {op} ? AND text GLOB ?",
                               (source, f"*Art. {number}.*")).fetchall()
        finally:
            con.close()
        rows.sort(key=lambda r: (f"— Art. {number}." not in r[1], r[1].find(f"Art. {number}.")))
        out += [r[0] for r in rows]
    return out[:limit]


def propose(model, question: str) -> list[str]:
    return [l.strip() for l in model.complete(SYS_CITES, question, 200).answer.splitlines() if l.strip()][:6]


def hits(pipeline, question: str, ev) -> list:
    """The provisions the model names, as hits from the vault, scored by the re-ranker against the question."""
    from .sol_search import Hit
    named = propose(pipeline._for("translate"), question)
    found, missing = [], []
    for line in named:
        p = parse(line)
        sids = lookup(pipeline.reader, *p) if p else []
        (found if sids else missing).extend(sids or [line])
    sols = [s for s in (pipeline.reader.get(sid) for sid in dict.fromkeys(found)) if s is not None]
    scores = pipeline.search.reranker.score([(question, s.text) for s in sols]) if sols else []
    out = sorted((Hit(s.sid, s, 1.0, float(sc), "cited") for s, sc in zip(sols, scores)), key=lambda h: -h.rerank)
    ev("retrieval.cited", {"named": named, "found": len(out), "not_in_vault": missing})
    return out
