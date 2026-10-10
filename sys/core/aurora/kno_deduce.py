# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Deductions (roadmap 77; owner, 10 Oct: «le deduzioni devono essere come un colpo di genio… una correlazione forte e
verificata su quel tipo di conoscenza… il classico lampo di genio, il guardare le cose da un'altra prospettiva»).

A deduction is not a summary. It is a bridge between two distant pieces of knowledge, and it must be:
  far        the same structure in two distant fields: a passage's principle stated without its field's words and
             searched in the other fields (far_pairs) — and the strongest synapses between two fields, level 2 first;
             one subject under two labels is not a pair (title cosine ≥ 0.70, then a judge);
  grounded   the fact taken from each side stated by that side's own passage (the verifier, YES/NO);
  sound      the deduction following from the two facts, with at most one reasonable step (the verifier again);
  new        none of the three nearest passages of other works already stating it (a judge reads them);
  a view     said as the other perspective it opens, and how one could test it.
One at a time at night (aurora-rem, after the training), AURORA_DEDUCE_PER_NIGHT; each pair looked at once. The ones
that pass wait for the owner's judgement («💡 lampo» or «✗ no»): that is the measure. A PDF on request (doc_pdf).
Worked out in English (the pivot, M176), the texts the owner reads translated back into Italian.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import closing

from . import sys_config

BRIDGE = (
    "You read two passages from different fields of knowledge. Look for a DEDUCTION: a non-obvious consequence that "
    "follows from putting them together — a principle, method or structure of one that, carried over to the other, "
    "says something the other passage does not say by itself. Not a summary, not a loose analogy ('both are about "
    "complexity'), not a restatement of either passage. Most pairs have none: then reply exactly NONE. Otherwise "
    "reply ONLY with JSON: {\"a_fact\": \"one factual sentence taken from the FIRST passage, close to its words — "
    "the fact itself, never 'the paper argues'\", \"b_fact\": \"the same for the SECOND passage\", \"deduction\": \"the new statement that follows from both, one or two sentences\", "
    "\"perspective\": \"what it lets one see differently, one sentence\", \"test\": \"how one could check it, one "
    "sentence\"}")
FOLLOWS = ("You check reasoning. Reply with exactly one word: YES if the CONCLUSION follows from the two FACTS with at "
           "most one reasonable step and adds something neither fact says alone, NO otherwise.")
SAME = ("Two passages. Reply with exactly one word: YES if they are about the same subject, entity, work, place or "
        "event (also in different languages, or one a part of the other), NO if their subjects are different.")
TITLE_SAME = 0.70     # title cosine (the embedder, multilingual): same subject 0.72-0.87, different ≤ 0.67 (M178, 40 pairs)
SKIP_KINDS = ("conversation", "reflection")
# a paper's service sections (the checklists conferences ask for): two of them look alike in any two fields (M178:
# «no high-risk assets released» bridged economics and biomedicine)
BOILER = re.compile(r"(?i)\bsafeguards?\b|checklist|broader impact|justification:|\[(yes|no|n/a|na)\]|"
                    r"answer:\s*\[|guidelines:|licen[cs]e[sd]? (for|of) (existing )?assets|crowdsourcing|irb approval")


def _db(cfg: sys_config.Config) -> sqlite3.Connection:
    f = (cfg.base or cfg).path("AURORA_STATUS_DIR") / "deductions.db"
    f.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS looked (a TEXT, b TEXT, at REAL, outcome TEXT, PRIMARY KEY (a, b))")
    con.execute("CREATE TABLE IF NOT EXISTS deductions (id INTEGER PRIMARY KEY, a TEXT, b TEXT, da TEXT, db TEXT, "
                "w REAL, level INTEGER, text TEXT, perspective TEXT, test TEXT, a_fact TEXT, b_fact TEXT, "
                "known REAL, score REAL, made REAL, verdict TEXT DEFAULT '', note TEXT DEFAULT '', en TEXT)")
    return con


def candidates(cfg: sys_config.Config, limit: int) -> list[dict]:
    """Synapses between two fields not looked at yet: level 2 first, then the strongest."""
    from . import kno_synapse as S
    with closing(S._db(cfg)) as con, closing(_db(cfg)) as dcon:
        seen = {(a, b) for a, b in dcon.execute("SELECT a, b FROM looked")}
        rows = con.execute("SELECT a, b, da, db, w, level FROM links WHERE active = 1 AND da != db "
                           "ORDER BY level DESC, w DESC LIMIT ?", (limit * 20 + len(seen),)).fetchall()
    out = [{"a": a, "b": b, "da": da, "db": db, "w": float(w), "level": int(lv or 1)}
           for a, b, da, db, w, lv in rows if (a, b) not in seen]
    return out[:limit]


def _words(s) -> set[str]:
    t = f"{s.title or ''} {s.source_id or ''}".lower()
    return {w for w in re.findall(r"[a-zà-ÿ0-9]{4,}", t)} - {"legacy", "arxiv", "wikipedia", "done", "paper", "with",
                                                               "from", "this", "that", "their"}


def same_subject(A, B) -> bool:
    """The same work, or two passages whose titles share half their words: one subject, two labels (the first look,
    M178: the Guru Granth Sahib under religion and philosophy, Euclid under literature and general)."""
    if A.source_id and A.source_id == B.source_id:
        return True
    wa, wb = _words(A), _words(B)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.5


def _title_cos(p, A, B) -> float:
    import numpy as np
    ta, tb = (A.title or A.source_id or ""), (B.title or B.source_id or "")
    v = np.array(p.search.embedder.encode_queries([ta, tb]), dtype=float)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return float(v[0] @ v[1])


ABSTRACT = ("State the general principle, mechanism or structure the passage describes in one or two sentences "
            "WITHOUT any word of its field (no domain terms, names, places): as a pattern that could hold in very "
            "different fields. If the passage holds no such principle (a list, a biography, a date), reply NONE.")


def far_pairs(p, cfg: sys_config.Config, passages: list, per: int = 2) -> list[dict]:
    """The other way to a deduction (M178: the synapses join SIMILAR passages, so they find one subject twice): a
    passage's principle without its field's words, searched in the OTHER fields — the same structure far away."""
    out = []
    for s in passages:
        principle = p._for("service").complete(ABSTRACT, f"{s.title or ''}\n{s.text[:1800]}", 120).answer.strip()
        if not principle or principle.upper().startswith("NONE"):
            continue
        for h in p.search.search(principle)[:12]:
            o = h.soliton
            if o.domain == s.domain or o.kind in SKIP_KINDS or same_subject(s, o):
                continue
            out.append({"a": s.sid, "b": h.sid, "da": s.domain, "db": o.domain, "w": float(h.rerank), "level": 0,
                        "principle": principle})
            if sum(1 for x in out if x["a"] == s.sid) >= per:
                break
    return out


def _json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    keys = ("a_fact", "b_fact", "deduction", "perspective", "test")
    return d if all(isinstance(d.get(k), str) and d[k].strip() for k in keys) else None


def _yes(llm, system: str, text: str) -> bool:
    return llm.complete(system, text, 4).answer.strip().upper().startswith("YES")


SAID = ("You compare a CONCLUSION with passages. Reply with exactly one word: YES if one of the passages already states "
        "the conclusion (the same claim, in any words), NO if none does — being on the same topic is not stating it.")


def _known(p, text: str, leave: set[str]) -> tuple[float, bool]:
    """(the re-ranker's best score of another work's passage, whether one of the three nearest already STATES it).
    The two works of the pair are left out whole (M178: their other chunks made a new deduction look known). The
    score alone measured being on the topic — the Cubism ↔ synergy deduction scored 0.909 — so a judge reads the
    three nearest passages."""
    hits = [h for h in p.search.search(text) if h.sid not in leave and h.soliton.source_id not in leave][:3]
    if not hits:
        return 0.0, False
    ctx = "\n\n".join(f"[{i}] {h.soliton.text[:900]}" for i, h in enumerate(hits, 1))
    return max(float(h.rerank) for h in hits), _yes(p._for("verify"), SAID, f"PASSAGES:\n{ctx}\n\nCONCLUSION: {text}")


def examine(p, cfg: sys_config.Config, cand: dict, emit=lambda e, d: None) -> dict:
    """One pair through the five tests; the outcome, and the deduction when it passes."""
    from .kno_stages import SYS_VERIFY
    got = p.reader.get_many({cand["a"]: 0, cand["b"]: 0})
    A, B = got.get(cand["a"]), got.get(cand["b"])
    if A is None or B is None or A.kind in SKIP_KINDS or B.kind in SKIP_KINDS:
        return {"outcome": "not knowledge"}
    if BOILER.search(A.text) or BOILER.search(B.text):
        return {"outcome": "service text"}
    if same_subject(A, B) or _title_cos(p, A, B) >= TITLE_SAME:     # one subject under two fields' labels (M178)
        return {"outcome": "same subject"}
    if _yes(p._for("verify"), SAME, f"FIRST: {A.title or ''}\n{A.text[:700]}\n\nSECOND: {B.title or ''}\n{B.text[:700]}"):
        return {"outcome": "same subject (judged)"}
    llm, judge = p._for("synthesis"), p._for("verify")
    text = (f"FIRST PASSAGE ({A.domain}: {A.title or A.source_id}):\n{A.text[:1800]}\n\n"
            f"SECOND PASSAGE ({B.domain}: {B.title or B.source_id}):\n{B.text[:1800]}")
    out = llm.complete(BRIDGE, text, 500).answer
    d = None if out.strip().upper().startswith("NONE") else _json(out)
    if d is None:
        return {"outcome": "no bridge"}
    if not _yes(judge, SYS_VERIFY, f"PASSAGES:\n{A.text[:2500]}\n\nSENTENCE: {d['a_fact']}"):
        return {"outcome": "first fact not in its passage", **d}
    if not _yes(judge, SYS_VERIFY, f"PASSAGES:\n{B.text[:2500]}\n\nSENTENCE: {d['b_fact']}"):
        return {"outcome": "second fact not in its passage", **d}
    if not _yes(judge, FOLLOWS, f"FACT 1: {d['a_fact']}\nFACT 2: {d['b_fact']}\nCONCLUSION: {d['deduction']}"):
        return {"outcome": "does not follow", **d}
    known, said = _known(p, d["deduction"], {cand["a"], cand["b"], A.source_id, B.source_id})
    if said:
        return {"outcome": "already in the vault", "known": known, **d}
    score = round(cand["w"] * (1.2 if cand["level"] > 1 else 1.0), 3)   # the link's strength; novelty is a yes/no
    emit("deduce.found", {"deduction": d["deduction"][:300], "score": score})
    return {"outcome": "deduction", "known": known, "score": score, **d}


def _italian(p, text: str) -> str:
    from .kno_stages import SYS_BACK
    out = p._for("translate").complete(SYS_BACK.format(lang="Italian"), text, max(300, len(text))).answer.strip()
    return out or text


def round_(p, cfg: sys_config.Config, emit, n: int, seed: int | None = None) -> dict:
    """A night's look: n passages of the vault taken to their principle and searched far away (far_pairs), and the
    strongest synapses between two fields not looked at yet; the deductions kept, in Italian, for the owner."""
    import random
    from . import kno_train
    with closing(_db(cfg)) as con:
        seen = {(a, b) for a, b in con.execute("SELECT a, b FROM looked")}
    far = [c for c in far_pairs(p, cfg, kno_train.documents(p.reader, n, random.Random(seed)))
           if (c["a"], c["b"]) not in seen]
    found, outcomes = 0, {}
    for cand in far + candidates(cfg, n * 10):
        try:
            r = examine(p, cfg, cand, emit)
        except Exception as e:  # noqa: BLE001 — one pair less tonight
            r = {"outcome": f"error: {type(e).__name__}"}
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        with closing(_db(cfg)) as con:
            con.execute("INSERT OR REPLACE INTO looked VALUES (?, ?, ?, ?)", (cand["a"], cand["b"], time.time(),
                                                                             r["outcome"]))
            if r["outcome"] == "deduction":
                found += 1
                con.execute("INSERT INTO deductions (a, b, da, db, w, level, text, perspective, test, a_fact, b_fact, "
                            "known, score, made, en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (cand["a"], cand["b"], cand["da"], cand["db"], cand["w"], cand["level"],
                             _italian(p, r["deduction"]), _italian(p, r["perspective"]), _italian(p, r["test"]),
                             r["a_fact"], r["b_fact"], r["known"], r["score"], time.time(), json.dumps(r)))
            con.commit()
    with closing(_db(cfg)) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('last_round', ?)", (str(time.time()),))
        con.commit()
    return {"looked": sum(outcomes.values()), "deductions": found, "outcomes": outcomes}


def deduced_tonight(cfg: sys_config.Config) -> bool:
    from . import kno_study
    with closing(_db(cfg)) as con:
        row = con.execute("SELECT value FROM meta WHERE key = 'last_round'").fetchone()
    return bool(row) and float(row[0]) >= kno_study.window_start(cfg).timestamp()


def listing(cfg: sys_config.Config, limit: int = 50) -> list[dict]:
    with closing(_db(cfg)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM deductions ORDER BY (verdict = '') DESC, score DESC, made DESC LIMIT ?",
                           (limit,)).fetchall()
    return [{k: r[k] for k in r.keys() if k != "en"} for r in rows]


def judge(cfg: sys_config.Config, did: int, verdict: str, note: str = "") -> dict:
    """The owner's judgement: «flash» (💡 a real one), «no», or '' (not judged)."""
    if verdict not in ("flash", "no", ""):
        raise ValueError("verdict: flash, no or ''")
    with closing(_db(cfg)) as con:
        n = con.execute("UPDATE deductions SET verdict = ?, note = ? WHERE id = ?", (verdict, note[:500], did)).rowcount
        con.commit()
    if not n:
        raise KeyError(did)
    return {"id": did, "verdict": verdict}


def as_markdown(p, d: dict) -> str:
    """A deduction as a document: the bridge, the two sides with their sources, the perspective, the test."""
    got = p.reader.get_many({d["a"]: 0, d["b"]: 0})

    def src(s):
        return f"{s.title or s.source_id} ({s.domain}; {s.source_id})" if s else "—"
    return (f"# 💡 {d['text']}\n\n**Da un'altra prospettiva.** {d['perspective']}\n\n**Come verificarla.** {d['test']}\n\n"
            f"## Il ponte\n\n- **{d['da']}**: {d['a_fact']}  \n  Fonte: {src(got.get(d['a']))}\n"
            f"- **{d['db']}**: {d['b_fact']}  \n  Fonte: {src(got.get(d['b']))}\n\n"
            f"Forza del legame {d['w']:.2f}; nessuno dei tre passaggi più vicini del vault la dice già (il più vicino "
            f"in tema: {d['known']:.2f}); punteggio {d['score']:.2f}.\n\n"
            f"_Deduzione di Aurora: i due fatti sono verificati sulle loro fonti, il passaggio fra loro no — è "
            f"un'ipotesi da controllare._")
