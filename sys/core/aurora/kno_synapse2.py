# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Synapses of synapses (owner, 2026-10-05: "small batteries on the links already made, so the links go up a level").

Two steps on the links of kno_synapse, run when AURORA_SYNAPSE_L2_EVERY new links have grown since the last time
(night rounds, questions and the harvester all add links):
- triads: A↔B and B↔C, A and C of different domains and not linked: a link of level 2 when A and C are themselves
  similar enough (AURORA_SYNAPSE_L2_MIN, 0.60). Measured on the first graph: the A–C similarities fall in two groups,
  0.23-0.31 (two passages that only share a bridge) and 0.60-0.76 (really related): the threshold sits in the gap;
- concepts: groups of passages held together by strong links (w ≥ 0.6, at least 3, across domains) become a
  concept, named by the LOCAL model from its passages' titles — what the links say Aurora has understood as one idea.
"""
from __future__ import annotations

import itertools
import json
import time
from collections import defaultdict
from contextlib import closing

import numpy as np

from . import kno_synapse as S
from . import sys_config

NAME = ("These passages of different fields are linked because they are about one idea. Give that idea a short name "
        "in Italian (2-5 words), nothing else.")


def _graph(cfg: sys_config.Config, min_w: float = 0.0):
    adj, dom, have = defaultdict(set), {}, set()
    with closing(S._db(cfg)) as con:
        for a, b, da, db, w in con.execute("SELECT a, b, da, db, w FROM links WHERE active = 1"):
            if w >= min_w:
                adj[a].add(b)
                adj[b].add(a)
            dom[a], dom[b] = da, db
            have.add((a, b))
    return adj, dom, have


def triads(cfg: sys_config.Config, reader, embedder, limit: int = 200) -> dict:
    """Level-2 links from the triads A↔B↔C whose ends are similar themselves."""
    adj, dom, have = _graph(cfg)
    cands = []
    for b, ns in adj.items():
        for a, c in itertools.combinations(sorted(ns), 2):
            if dom[a] != dom[c] and (a, c) not in have:
                cands.append((a, c))
    cands = list(dict.fromkeys(cands))[:limit]
    if not cands:
        return {"candidates": 0, "made": 0}
    sids = sorted({x for p in cands for x in p})
    sols = reader.get_many({s: 0 for s in sids})
    sids = [s for s in sids if s in sols]
    v = np.asarray(embedder.encode_queries([sols[s].text[:1500] for s in sids]), dtype=float)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    ix, made = {s: i for i, s in enumerate(sids)}, 0
    for a, c in cands:
        if a in ix and c in ix and not S.same_source(sols[a], sols[c]):
            sim = float(v[ix[a]] @ v[ix[c]])
            if sim >= cfg["AURORA_SYNAPSE_L2_MIN"]:
                S.link(cfg, (a, dom[a]), (c, dom[c]), sim, kind="triad")
                with closing(S._db(cfg)) as con, con:
                    con.execute("UPDATE links SET level = 2 WHERE a = ? AND b = ?", S._pair(a, c))
                made += 1
    return {"candidates": len(cands), "made": made}


def concepts(cfg: sys_config.Config, reader, llm=None, min_w: float = 0.6) -> dict:
    """Groups held by strong links across domains, named by the local model; the table is rebuilt each time."""
    adj, dom, _ = _graph(cfg, min_w)
    seen, groups = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack += [y for y in adj[x] if y not in comp]
        seen |= comp
        if len(comp) >= 3 and len({dom[x] for x in comp}) >= 2:
            groups.append(sorted(comp))
    rows = []
    for g in groups:
        sols = reader.get_many({s: 0 for s in g})
        titles = [f"[{sols[s].domain}] {sols[s].title or sols[s].text[:80]}" for s in g if s in sols][:12]
        name = ""
        if llm is not None:
            try:
                name = llm.complete(NAME, "\n".join(titles), 40).answer.strip().strip('"«»').split("\n")[0][:80]
            except Exception:                         # noqa: BLE001 — a concept without a name is still a concept
                name = ""
        rows.append((json.dumps(g), json.dumps(sorted({dom[x] for x in g})), name, time.time()))
    with S._lock, closing(S._db(cfg)) as con, con:
        con.execute("DELETE FROM concepts")
        con.executemany("INSERT INTO concepts (members, domains, name, made) VALUES (?, ?, ?, ?)", rows)
    return {"concepts": len(rows)}


def due(cfg: sys_config.Config) -> bool:
    """Enough new links since the last level-2 round (AURORA_SYNAPSE_L2_EVERY)."""
    with closing(S._db(cfg)) as con:
        n = con.execute("SELECT count(*) FROM links WHERE active = 1").fetchone()[0]
        last = con.execute("SELECT value FROM meta WHERE key = 'l2_links'").fetchone()
    return n - int(last[0] if last else 0) >= int(cfg["AURORA_SYNAPSE_L2_EVERY"])


def round_(cfg: sys_config.Config, reader, embedder, llm=None) -> dict:
    t0 = time.time()
    out = {**triads(cfg, reader, embedder), **concepts(cfg, reader, llm)}
    with S._lock, closing(S._db(cfg)) as con, con:
        n = con.execute("SELECT count(*) FROM links WHERE active = 1").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO meta VALUES ('l2_links', ?)", (str(n),))
    return {**out, "seconds": round(time.time() - t0, 1)}


def list_concepts(cfg: sys_config.Config) -> list[dict]:
    with closing(S._db(cfg)) as con:
        rows = con.execute("SELECT id, members, domains, name, made FROM concepts ORDER BY id").fetchall()
    return [{"id": i, "members": json.loads(m), "domains": json.loads(d), "name": n, "made": t} for i, m, d, n, t in rows]
