# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How much to think for a question (owner, 2026-10-07: «modalità di pensiero… leggera, media, profonda e auto»;
«semplifichiamo»; M130).

Each question goes the way of its kind (kno_read.kind: FACT, EXPLAIN, CASE), from the source that fits it, and the
answer is read from that source with where it was read; when no source says it, the model's own answer marked ⚠️.

    vault    the vault pipeline only (gate, extraction, synthesis with thinking, verification): as before
    light    FACT → the web's snippets; EXPLAIN and CASE → the vault's passages; then the web; then memory ⚠️
    medium   light, and when the snippets are too short the best pages are opened and read
    auto     medium, and a CASE goes to the deep pipeline first (a story split in its problems, provisions by number)
    deep     the deep pipeline first for every question, then the web, then memory ⚠️
The way taken is said in the chat (event «think»: asked, used, why). The memory, the REM and the routines never change.
"""
from __future__ import annotations

from . import kno_grid, kno_read

MODES = ("vault", "light", "medium", "deep", "auto")
VAULT_FIRST = 0.6       # the best vault passage's re-rank that sends a FACT to the vault before the web (M194)
KIND_IT = {"fact": "un fatto da cercare", "explain": "una spiegazione", "case": "un caso", "solve": "un problema da risolvere",
           "write": "un testo da scrivere"}


def mode_of(cfg, asked: str | None) -> str:
    m = (asked or str(cfg["AURORA_ANSWER_MODE"] or "vault")).strip().lower()
    return m if m in MODES else "vault"


def answer(p, question: str, translation: str | None, mode: str, retrieve, classic, ev, focused: bool = False) -> tuple:
    """(read | None, classic answer | None, hits, subs). `retrieve(recall)` → (hits, subs); `classic(hits, subs)` →
    the vault pipeline's (text, sources, dropped) or None. `read` is kno_read's {"text", "sources", "dropped"}."""
    got: dict = {}

    def hits():
        if "hits" not in got:
            got["hits"], got["subs"] = retrieve(None)
        return got["hits"], got["subs"]

    def say(used, why=""):
        ev("think", {"asked": mode, "used": used, "why": why})

    if mode == "vault":
        say("vault")
        return None, classic(*hits()), *hits()
    try:
        kind = kno_read.kind(p, question)
    except Exception as e:  # noqa: BLE001 — the routing model down: the vault first, then the web, then memory
        ev("read.failed", {"where": "kind", "error": f"{type(e).__name__}: {e}"[:200]})
        kind = "explain"
    deep = mode == "deep" or (mode == "auto" and kind == "case")
    open_pages = mode != "light"
    steps = []
    if kind == "solve":                               # an exercise: reasoned first, then the web, then memory (C272)
        if kno_grid.puzzle(question) and kno_grid.worth(p):   # a grid puzzle: its rule as a program (ROADMAP 105)
            steps.append(("grid", lambda: ("read", kno_grid.solve(p, question, ev))))
        steps.append(("reason", lambda: ("read", kno_read.from_reasoning(p, question, ev))))
        steps.append(("web", lambda: ("read", kno_read.from_web(p, question, ev, "explain", open_pages, translation))))
    elif kind == "write":                             # a text to compose: no source to look for, its form kept (C355)
        steps.append(("write", lambda: ("read", kno_read.from_writing(p, question, ev))))
    elif focused and not deep:                        # a follow-up: the sources of the answer before come first
        steps.append(("vault", lambda: ("read", kno_read.from_vault(p, question, hits()[0], "fact" if kind == "fact" else "explain"))))
        steps.append(("web", lambda: ("read", kno_read.from_web(p, question, ev, "fact" if kind == "fact" else "explain",
                                                                 open_pages, translation))))
    elif kind == "fact" and not deep:
        # the vault first when it is sure (the CRAG way): its best passage's re-rank ≥ VAULT_FIRST. Measured (M194):
        # at 0.6 61 of 64 questions whose source is first in the vault read it first; 7 of 60 SimpleQA facts (not in
        # the vault) pay one vault reading before the web. Otherwise the web first, as before (owner, 13 Oct: «prima
        # vault e poi ricerca web… in base al contesto, se no le query diventano lunghe minuti»)
        try:
            best = hits()[0]
            score = float(getattr(best[0], "rerank", 0.0)) if best else None
        except Exception as e:  # noqa: BLE001 — the search down: the web first, as before
            ev("read.failed", {"where": "vault_first", "error": f"{type(e).__name__}: {e}"[:200]})
            score = None
        sure = score is not None and score >= VAULT_FIRST
        ev("think.vault_first", {"rerank": None if score is None else round(score, 3), "vault_first": sure})
        web = ("web", lambda: ("read", kno_read.from_web(p, question, ev, "fact", open_pages, translation)))
        vault = ("vault", lambda: ("read", kno_read.from_vault(p, question, hits()[0], "fact")))
        steps += [vault, web] if sure else [web, vault]
    else:
        if deep:
            steps.append(("deep", lambda: ("classic", classic(*hits()))))
        else:
            steps.append(("vault", lambda: ("read", kno_read.from_vault(p, question, hits()[0], "explain"))))
        steps.append(("web", lambda: ("read", kno_read.from_web(p, question, ev, "explain" if kind != "fact" else "fact",
                                                                 open_pages, translation))))
    steps.append(("memory", lambda: ("read", kno_read.from_memory(p, question, ev))))
    for where, step in steps:
        try:
            what, out = step()
        except Exception as e:  # noqa: BLE001 — a source that breaks is a source that did not answer (M130)
            ev("read.failed", {"where": where, "error": f"{type(e).__name__}: {e}"[:200]})
            p_log = getattr(p, "log", None)
            if p_log:
                p_log.warning("answer: the %s step failed: %s", where, e)
            continue
        if out:
            say(mode, f"{KIND_IT[kind]} → {where}")
            if what == "classic":
                return None, out, *hits()
            out = {**out, "came_from": where, "learn": kind not in ("fact", "solve", "write") and where in ("web", "memory")}
            return out, None, *(got.get("hits", []), got.get("subs", []))
    say(mode, f"{KIND_IT[kind]} → nessuna fonte")
    return None, None, *(got.get("hits", []), got.get("subs", []))
