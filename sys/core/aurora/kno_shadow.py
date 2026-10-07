# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The shadow of an answer (owner, 2026-10-05: "a question and its answer cast a shadow; a similar question falling in
it gets the answer at once, and Aurora works in the background to complete it").

A knowledge answer, verified and with sources, is kept with its question's vector. A new question falls in its shadow
when BOTH hold:
- its vector is close to the old question's: cosine ≥ AURORA_SHADOW_COS (0.90);
- the re-ranker reads the old answer as an answer to the new question: ≥ AURORA_SHADOW_ANSWER (0.5).
Measured before choosing (M111), on the 23 answered questions of pool30: their paraphrases 0.78-1.00 (median 0.945),
the other questions ≤ 0.56, and — the hard case — another question on the same subject 0.49-1.00: the re-ranker alone
let 7 of 9 such questions through with 0.51-0.99 (a topic in common is not an answer), all at cosine 0.72-0.86; at
0.90 none of the 46 got through, 18 of 23 paraphrases did. The answer from a shadow says which question it was given
for and when, and the whole pipeline checks it again at once in the background: a different answer replaces it in the
shadow and is shown in the chat. The shadow lives in the user's state folder (shadow.db), at most 2,000 answers.

A seed (owner, 2026-10-05): script/shadow_seed.py asks many questions on purpose (origin "seed", never the owner's
own); export_seed() writes those whose every source is public (an arXiv, Wikipedia, Normattiva... identity) to a file
published with the code, import_seed() lets a new installation start with them — rechecked like any other.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing

import numpy as np

from . import sys_config

MAX_ROWS = 2000
OVERLAP = 5                                       # the nearest shadows the re-ranker chooses among
# sources a seed may cite: public identities only — never a document of the owner's (legacy:arxiv_ is the arXiv
# imported by the first installation)
PUBLIC = ("arxiv:", "legacy:arxiv_", "wikipedia:", "normattiva:", "europepmc:", "pmc", "biorxiv:", "medrxiv:", "github:",
          "docs:", "doi:")
_lock = threading.Lock()


def _db(cfg: sys_config.Config) -> sqlite3.Connection:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(d / "shadow.db", timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS shadows (id INTEGER PRIMARY KEY, question TEXT, vec BLOB, answer TEXT,"
                " sources TEXT, made REAL, used INTEGER DEFAULT 0, last REAL)")
    if "origin" not in {r[1] for r in con.execute("PRAGMA table_info(shadows)")}:
        con.execute("ALTER TABLE shadows ADD COLUMN origin TEXT DEFAULT 'chat'")
    if "follow" not in {r[1] for r in con.execute("PRAGMA table_info(shadows)")}:
        con.execute("ALTER TABLE shadows ADD COLUMN follow TEXT")       # the answer's follow-up questions
    if "expires" not in {r[1] for r in con.execute("PRAGMA table_info(shadows)")}:
        con.execute("ALTER TABLE shadows ADD COLUMN expires REAL")      # a web answer's end (facts change); NULL: never
    return con


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / (np.linalg.norm(v) + 1e-12)


def add(cfg: sys_config.Config, embedder, question: str, text: str, sources: list[dict], origin: str = "chat",
        made: float | None = None, follow: list | None = None) -> None:
    """A verified knowledge answer casts its shadow (an older one of the same question is replaced). An answer read
    from the web (a source with a «url») is kept AURORA_SHADOW_WEB_DAYS, then searched again (M130)."""
    if not text or not sources:
        return
    web = any(s.get("url") for s in sources)
    origin = "web" if web and origin == "chat" else origin
    expires = time.time() + float(cfg["AURORA_SHADOW_WEB_DAYS"]) * 86400 if web else None
    vec = _unit(embedder.encode_queries([question])[0])
    with _lock, closing(_db(cfg)) as con, con:
        con.execute("DELETE FROM shadows WHERE question = ?", (question,))
        con.execute("INSERT INTO shadows (question, vec, answer, sources, made, last, origin, follow, expires)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (question, vec.tobytes(), text, json.dumps(sources, ensure_ascii=False), made or time.time(),
                     time.time(), origin, json.dumps(follow or [], ensure_ascii=False), expires))
        n = con.execute("SELECT count(*) FROM shadows").fetchone()[0]
        if n > MAX_ROWS:                               # the least used and oldest go first
            con.execute("DELETE FROM shadows WHERE id IN (SELECT id FROM shadows ORDER BY used, last LIMIT ?)",
                        (n - MAX_ROWS,))


def _shared(cfg: sys_config.Config):
    """The admin's shadow file when the asking user is someone else: its seed answers are knowledge, not memories, and
    serve every user (2026-10-06: a user's «Cos'è la decoerenza quantistica?» went through the whole search)."""
    from . import sys_users_layout
    m = sys_users_layout.migrated(cfg)
    admin = (m or {}).get("admin")
    if not admin or (cfg.user or admin) == admin:
        return None
    f = sys_users_layout.place(cfg, "state", admin) / "shadow.db"
    return f if f.is_file() else None


def find(cfg: sys_config.Config, embedder, reranker, question: str) -> dict | None:
    """The answer whose shadow this question falls in, or None."""
    with closing(_db(cfg)) as con:
        rows = [(*r, False) for r in con.execute("SELECT id, question, vec, answer, sources, made, follow FROM shadows "
                                                  "WHERE expires IS NULL OR expires > ?", (time.time(),)).fetchall()]
    seed = _shared(cfg)
    if seed is not None:
        with closing(sqlite3.connect(f"file:{seed}?mode=ro", uri=True, timeout=30)) as con:
            rows += [(*r, True) for r in con.execute("SELECT id, question, vec, answer, sources, made, follow FROM shadows "
                                                      "WHERE origin IN ('seed', 'train')").fetchall()]
    if not rows:
        return None
    q = _unit(embedder.encode_queries([question])[0])
    mat = np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows])
    cos = mat @ q
    near = [int(i) for i in np.argsort(-cos)[:OVERLAP] if float(cos[i]) >= float(cfg["AURORA_SHADOW_COS"])]
    if not near:
        return None
    # shadows that overlap: the re-ranker chooses the answer that answers this question best (the nearest on a tie)
    scores = [float(x) for x in reranker.score([(question, rows[i][3][:3000]) for i in near])]
    k = max(range(len(near)), key=lambda j: (scores[j], float(cos[near[j]])))
    best, score = near[k], scores[k]
    if score < float(cfg["AURORA_SHADOW_ANSWER"]):
        return None
    rid, old_q, _, text, sources, made, follow, shared = rows[best]
    if not shared:                                     # the admin's seed is read only for the other users
        with _lock, closing(_db(cfg)) as con, con:
            con.execute("UPDATE shadows SET used = used + 1, last = ? WHERE id = ?", (time.time(), rid))
    return {"question": old_q, "text": text, "sources": json.loads(sources), "made": made, "follow": json.loads(follow or "[]"),
            "cos": round(float(cos[best]), 3), "score": round(score, 3), "overlap": len(near),
            "sure": float(cos[best]) >= float(cfg["AURORA_SHADOW_SURE"])}


SYS_ADAPT = ("You answer the NEW QUESTION from an answer Aurora already gave and verified for an EARLIER QUESTION very "
             "close to it, and from the PASSAGES that answer cited. Answer the new question directly, in its language, "
             "as a fresh answer: not a copy, and never mentioning the earlier question. Use only what the passages and "
             "the earlier answer say; every sentence ends with the citation [n] of the passage that supports it, with "
             "the same numbers. If the new question asks something they do not cover, say so in one sentence.")


def adapt(p, question: str, hit: dict, emit) -> str:
    """The shadow's answer written again for this question (owner, 2026-10-06: "not a copy in 3 ms: Aurora takes the
    answer and the question and adapts it"), from the same passages, streamed like any answer and verified sentence by
    sentence like any answer. "" when its passages are not in this vault (a seed on a new installation): nothing to
    verify against, the answer is given as it was."""
    from types import SimpleNamespace
    srcs = [s for s in hit["sources"] if s.get("sid") and s.get("n")]
    found = p.reader.get_many([s["sid"] for s in srcs])
    if not srcs or any(s["sid"] not in found for s in srcs):
        return ""
    hits = [SimpleNamespace(soliton=SimpleNamespace(text="")) for _ in range(max(int(s["n"]) for s in srcs))]
    for s in srcs:
        hits[int(s["n"]) - 1] = SimpleNamespace(soliton=found[s["sid"]])
    passages = "\n\n".join(f"[{s['n']}] {found[s['sid']].text}" for s in srcs)
    user = (f"PASSAGES:\n{passages}\n\nEARLIER QUESTION: {hit['question']}\nEARLIER ANSWER (verified):\n{hit['text']}"
            f"\n\nNEW QUESTION: {question}")
    model, parts = p._for("synthesis"), []
    for kind, piece in model.stream(SYS_ADAPT, user, p.cfg["AURORA_PIPELINE_THINK_TOKENS"], think=False):
        if kind == "answer":
            parts.append(piece)
        if p.cfg["AURORA_CHAT_STREAMING"]:
            emit("synthesis.delta", {"kind": kind, "text": piece})
    text = "".join(parts).strip()
    if text and p.cfg["AURORA_PIPELINE_VERIFY"]:
        text, _ = p._verify(text, hits, emit)
    return text


def stats(cfg: sys_config.Config) -> dict:
    with closing(_db(cfg)) as con:
        n, used = con.execute("SELECT count(*), coalesce(sum(used), 0) FROM shadows").fetchone()
        seeds = con.execute("SELECT count(*) FROM shadows WHERE origin = 'seed'").fetchone()[0]
    return {"answers": n, "served": used, "seed": seeds}


def public(sources: list[dict]) -> bool:
    """Every source has a public identity: its id, or the origin its passage was imported with ("arxiv:2609.25188")."""
    return bool(sources) and all(str(s.get("source", "")).lower().startswith(PUBLIC)
                                 or str(s.get("origin") or "").lower().startswith(PUBLIC) or s.get("origin") == "arxiv"
                                 for s in sources)


def export_seed(cfg: sys_config.Config, reader=None) -> list[dict]:
    """The seed's answers that may leave this machine: asked by the seed script, every source public. With the vault's
    reader each source carries the origin, address and licence its passage was imported with (the attribution)."""
    with closing(_db(cfg)) as con:
        rows = con.execute("SELECT question, answer, sources, made, follow FROM shadows WHERE origin IN ('seed', 'train') "
                           "ORDER BY id").fetchall()
    found = reader.get_many([s.get("sid") for r in rows for s in json.loads(r[2]) if s.get("sid")]) if reader else {}
    out = []
    for q, text, sources, made, follow in rows:
        src = []
        for s in json.loads(sources):
            extra = (found[s["sid"]].extra or {}) if s.get("sid") in found else {}
            src.append({**{k: s.get(k) for k in ("n", "sid", "title", "source", "domain")},
                        **{k: extra[k] for k in ("origin", "url", "licence") if extra.get(k)}})
        if public(src):
            out.append({"question": q, "answer": text, "made": round(made), "sources": src,
                        "follow": json.loads(follow or "[]")})
    return out


def import_seed(cfg: sys_config.Config, embedder, rows: list[dict]) -> dict:
    """A published seed into this installation's shadow; questions already there are left as they are."""
    with closing(_db(cfg)) as con:
        have = {r[0] for r in con.execute("SELECT question FROM shadows")}
    added = skipped = 0
    for r in rows:
        if r.get("question") in have or not public(r.get("sources") or []) or not r.get("answer"):
            skipped += 1
            continue
        add(cfg, embedder, r["question"], r["answer"], r["sources"], origin="seed", made=r.get("made"),
            follow=r.get("follow"))
        added += 1
    return {"added": added, "skipped": skipped}
