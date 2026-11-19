# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Whether a question asks for the law, decided before the search's legal passages reach the gate (C694, M315).

Italian statutes are 18 % of the vault (law_it): a long everyday question split into searches, or a short one with a
word like «regole» or «diritti», brought civil-code passages to the gate, and only the gate stopped them. Measured on
invented questions (M315): the English pivot's similarity to law_it's centroid minus its similarity to the closest
other domain's centroid tells the legal questions apart (margin > −0.01: 2 false positives of 70, none of 25 legal
missed); the untranslated text does not (12 of 70), so the pivot is what is read.

Below the threshold law_it's passages and the provisions kno_cites would name stay out; above it they come in as
before. Near the threshold (the band), or for a true follow-up (kno_followup.leans_on_before), the local model,
already loaded, breaks the tie with one token, reading the conversation's last turns — only then (C706: outside the
band a question of the session is decided by its margin, and earlier text cannot steer it). The model absent or past
TIE_TIMEOUT_S (the HTTP call itself bounded): the margin decides, said «uncertain». The model unsure in the band: the
law stays out and the event says so («uncertain»: where a legal mode can be offered); unsure on a follow-up outside
the band: the margin. A question with an attached file, with an
explicit article or act («art. 2043 c.c.», «d.lgs. 30/2005»), or a follow-up on legal sources, stays legal.

The centroids are computed from the passages already indexed (a fixed sample per domain, the knowledge's memmaps,
read only): 0.13 s for 33 domains, measured on the page cache; kept in memory, the counts read at most every
COUNTS_S, computed again when they changed (at most every REFRESH_S) or as soon as a domain lost passages (a
realignment moved them, C695).
"""
from __future__ import annotations

import re
import threading
import time
import zlib

import numpy as np

LEGAL_PREFIX = "law_"          # law_it today; another country's statutes would be law_xx
MIN_PASSAGES = 200             # a domain this small has no stable centroid (patents: 27 passages)
SAMPLE, SAMPLE_LEGAL = 1500, 6000   # M315's sample sizes; the full mean differs by cos 0.9992 (measured, law_it)
REFRESH_S = 600
TIE_TIMEOUT_S = 8.0
UNSURE = 0.15                  # P(LAW) within 0.5 ± this: the model unsure
COUNTS_S = 60                  # the manifests read again at most this often

SYS_TIE = ("Does answering this question need the text of a country's laws: a right, a duty, a contract, a lease, "
           "an inheritance, a dispute, a fine, an offence, a court or a legal procedure? Rules of a game, laws of "
           "nature, school, health, cooking, technology and everyday life are not. The earlier turns, when given, "
           "only tell what a short follow-up refers to: a new subject is judged on its own. Reply LAW or OTHER.")

_ACT = re.compile(r"(?i)\b(?:art(?:icolo|icle|ículo|\.)\s*\d+|codice\s+(?:civile|penale|di\s+procedura)|c\.\s?c\.|"
                  r"c\.\s?p\.(?:\s?[cp]\.)?|(?:d\.\s?lgs|d\.\s?l|d\.\s?p\.\s?r|decreto\s+legislativo|legge|l)\.?\s*"
                  r"(?:n\.?\s*)?\d+\s*/\s*\d{2,4})")

_lock = threading.Lock()
_cache: dict = {}


def cites_an_act(text: str) -> bool:
    """An explicit article or act named in the question: legal whatever the margin."""
    return bool(_ACT.search(text or ""))


def is_legal_domain(domain: str) -> bool:
    return str(domain or "").startswith(LEGAL_PREFIX)


def legal_hit(h) -> bool:
    return is_legal_domain(getattr(h.soliton, "domain", "")) or getattr(h, "query_used", "") == "cited"


def _counts(cfg) -> dict:
    from . import sol_index
    out = {}
    for section, domain, f in sol_index._index_dirs(cfg, None):
        if section == "knowledge":
            m = f.read_manifest()
            if m and m["count"] >= MIN_PASSAGES:
                out[domain] = (f, m)
    return out


def _compute(cfg, found: dict) -> tuple[list[str], np.ndarray]:
    from . import sol_index
    names, rows = [], []
    for domain, (f, m) in sorted(found.items()):
        v = sol_index._vectors(cfg, f, m)
        n = m["count"]
        rng = np.random.default_rng(zlib.crc32(domain.encode()))          # the same sample every time
        take = np.sort(rng.choice(n, size=min(n, SAMPLE_LEGAL if is_legal_domain(domain) else SAMPLE), replace=False))
        x = np.asarray(v[take], dtype=np.float32)
        x /= np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)
        c = x.mean(0)
        names.append(domain)
        rows.append(c / max(float(np.linalg.norm(c)), 1e-9))
    return names, np.stack(rows) if rows else np.zeros((0, 0), np.float32)


def centroids(cfg) -> tuple[list[str], np.ndarray]:
    """(domain names, unit centroids), from the cache when the indexed counts have not moved."""
    with _lock:
        if _cache.get("counts") is not None and time.time() - _cache.get("checked", 0) < COUNTS_S:
            return _cache["names"], _cache["C"]
    found = _counts(cfg)
    counts = {d: m["count"] for d, (f, m) in found.items()}
    with _lock:
        _cache["checked"] = time.time()
        old = _cache.get("counts")
        fresh = old is not None and set(old) == set(counts) and (
            counts == old or (time.time() - _cache["at"] < REFRESH_S and all(counts[d] >= old[d] for d in counts)))
        if not fresh:
            t0 = time.time()
            names, c = _compute(cfg, found)
            _cache.update(counts=counts, names=names, C=c, at=time.time(), seconds=round(time.time() - t0, 3))
        return _cache["names"], _cache["C"]


def forget() -> None:
    with _lock:
        _cache.clear()


def margin(cfg, embedder, text: str) -> float | None:
    """Similarity to the closest legal centroid minus the closest other one; None without a legal domain."""
    names, c = centroids(cfg)
    legal = [i for i, d in enumerate(names) if is_legal_domain(d)]
    other = [i for i, d in enumerate(names) if not is_legal_domain(d)]
    if not legal or not other:
        return None
    q = np.asarray(embedder.encode_queries([text]), dtype=np.float32)[0]
    q /= max(float(np.linalg.norm(q)), 1e-9)
    s = c @ q
    return float(s[legal].max() - s[other].max())


def tie(model, text: str, context: str = "") -> tuple[bool | None, float | None]:
    """The local model's one-token answer, LAW or OTHER, within TIE_TIMEOUT_S: (its answer or None, P(LAW) or None).
    `context`: the conversation's last turns, so that «e per mia sorella?» is read after what came before. C706: the
    call itself is bounded (decide's timeout: the HTTP request closed, the swap's wait cut), so no thread is left
    holding the model; a model with no decide, or one that names no option, is no answer (no unbounded word asked)."""
    out: dict = {}
    user = (f"EARLIER TURNS:\n{context}\n\n" if context else "") + f"QUESTION: {text[:2000]}"
    dec = getattr(model, "decide", None)
    if dec is None:
        return None, None

    def ask():
        try:
            try:
                sure = dec(SYS_TIE, user, ["LAW", "OTHER"], timeout=TIE_TIMEOUT_S)
            except TypeError:                         # a decide with no timeout (a test's stand-in): the join bounds it
                sure = dec(SYS_TIE, user, ["LAW", "OTHER"])
            if sure:
                out["v"], out["p"] = sure["LAW"] > 0.5, float(sure["LAW"])
        except Exception:                             # noqa: BLE001 — no answer: the margin decides
            pass
    t = threading.Thread(target=ask, name="law-tie", daemon=True)
    t.start()
    t.join(TIE_TIMEOUT_S + 0.5)
    return out.get("v"), out.get("p")


def setting(cfg, key: str, default: float) -> float:
    try:
        v = cfg[key]
    except (KeyError, TypeError):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def context_of(pipeline, recent: list | None) -> str:
    """The conversation's last two turns, clipped, when they are of this session (as kno_followup.standalone reads
    them); empty otherwise."""
    if not recent:
        return ""
    try:
        from datetime import datetime
        from . import sns_clock
        last = datetime.fromisoformat(recent[-1].created_at)
        if (sns_clock.now(pipeline.cfg) - last).total_seconds() > pipeline.cfg["AURORA_REM_SESSION_GAP_MIN"] * 60:
            return ""
        return pipeline._turns(recent, 2, 400)
    except Exception:                                 # noqa: BLE001 — no context: the question alone
        return ""


def legal(pipeline, question: str, ev, native: str = "", attached: bool = False, focus: list | None = None,
          recent: list | None = None, followup: bool = False) -> bool:
    """True when law_it's passages and the named provisions may enter this question's search (see the module).
    `question`: the standalone pivot (a follow-up already rewritten with the turns before it); `recent`: those turns,
    read by the tie-break only for a true follow-up (`followup`: kno_followup.leans_on_before, C706). The model
    unsure in the band: the law stays OUT and the event says «uncertain» — a legal mode can be offered then, instead
    of statutes slipped in unasked (owner, 20 Nov); the model absent or late: the margin, «uncertain»."""
    cfg = pipeline.cfg
    threshold = setting(cfg, "AURORA_PIPELINE_LAW_GATE", -1.0)
    band = setting(cfg, "AURORA_PIPELINE_LAW_GATE_BAND", 0.0)
    if threshold <= -1.0:
        return True                                   # off: every question as before
    why = ("attachment" if attached else "act named" if cites_an_act(native) or cites_an_act(question)
           else "follow-up on legal sources" if any(is_legal_domain(f.get("domain", "")) for f in (focus or []))
           else "")
    if why:
        ev("law.gate", {"legal": True, "uncertain": False, "why": why})
        return True
    t0 = time.time()
    try:
        m = margin(cfg, pipeline.search.embedder, question)
    except Exception as e:                            # noqa: BLE001 — not measured: uncertain, the law out
        ev("law.gate", {"legal": False, "uncertain": True, "why": f"not measured: {type(e).__name__}"})
        return False
    if m is None:
        return True                                   # no legal domain indexed: nothing to keep out
    out, why, unsure, p = m > threshold, "margin", False, None
    inside = band > 0 and abs(m - threshold) <= band
    # a true follow-up is read with its turns: «e quanto tempo ho?» has the margin of no subject (M318: 3 of 6 legal
    # follow-ups were 0.03-0.06 below the threshold, the model with the turns got 12 of 12); any other question of
    # the session is decided by its margin outside the band, and the turns are never given to the model (C706)
    context = context_of(pipeline, recent) if band > 0 and followup else ""
    if inside or context:
        said, p = tie(getattr(pipeline, "llm", None) or pipeline._for("route"), question, context)
        if said is None:
            why, unsure = "the model did not answer: the margin", True
        elif p is not None and abs(p - 0.5) < UNSURE:
            if inside:
                out, why, unsure = False, "the model unsure", True
            else:
                why, unsure = "the model unsure: the margin", True
        else:
            out, why = said, "model" + (" with the turns before" if context else "")
    ev("law.gate", {"legal": out, "uncertain": unsure, "why": why, "margin": round(m, 4), "threshold": threshold,
                    **({"band": band} if band else {}), **({"p_law": round(p, 3)} if p is not None else {}),
                    "seconds": round(time.time() - t0, 3)})
    return out
