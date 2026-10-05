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
_lock = threading.Lock()


def _db(cfg: sys_config.Config) -> sqlite3.Connection:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(d / "shadow.db", timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS shadows (id INTEGER PRIMARY KEY, question TEXT, vec BLOB, answer TEXT,"
                " sources TEXT, made REAL, used INTEGER DEFAULT 0, last REAL)")
    return con


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / (np.linalg.norm(v) + 1e-12)


def add(cfg: sys_config.Config, embedder, question: str, text: str, sources: list[dict]) -> None:
    """A verified knowledge answer casts its shadow (an older one of the same question is replaced)."""
    if not text or not sources:
        return
    vec = _unit(embedder.encode_queries([question])[0])
    with _lock, closing(_db(cfg)) as con, con:
        con.execute("DELETE FROM shadows WHERE question = ?", (question,))
        con.execute("INSERT INTO shadows (question, vec, answer, sources, made, last) VALUES (?, ?, ?, ?, ?, ?)",
                    (question, vec.tobytes(), text, json.dumps(sources, ensure_ascii=False), time.time(), time.time()))
        n = con.execute("SELECT count(*) FROM shadows").fetchone()[0]
        if n > MAX_ROWS:                               # the least used and oldest go first
            con.execute("DELETE FROM shadows WHERE id IN (SELECT id FROM shadows ORDER BY used, last LIMIT ?)",
                        (n - MAX_ROWS,))


def find(cfg: sys_config.Config, embedder, reranker, question: str) -> dict | None:
    """The answer whose shadow this question falls in, or None."""
    with closing(_db(cfg)) as con:
        rows = con.execute("SELECT id, question, vec, answer, sources, made FROM shadows").fetchall()
    if not rows:
        return None
    q = _unit(embedder.encode_queries([question])[0])
    mat = np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows])
    cos = mat @ q
    best = int(np.argmax(cos))
    if float(cos[best]) < float(cfg["AURORA_SHADOW_COS"]):
        return None
    rid, old_q, _, text, sources, made = rows[best]
    score = float(reranker.score([(question, text[:3000])])[0])
    if score < float(cfg["AURORA_SHADOW_ANSWER"]):
        return None
    with _lock, closing(_db(cfg)) as con, con:
        con.execute("UPDATE shadows SET used = used + 1, last = ? WHERE id = ?", (time.time(), rid))
    return {"question": old_q, "text": text, "sources": json.loads(sources), "made": made,
            "cos": round(float(cos[best]), 3), "score": round(score, 3)}


def stats(cfg: sys_config.Config) -> dict:
    with closing(_db(cfg)) as con:
        n, used = con.execute("SELECT count(*), coalesce(sum(used), 0) FROM shadows").fetchone()
    return {"answers": n, "served": used}
