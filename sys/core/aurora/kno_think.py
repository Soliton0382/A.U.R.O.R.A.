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

from . import kno_read

MODES = ("vault", "light", "medium", "deep", "auto")
KIND_IT = {"fact": "un fatto da cercare", "explain": "una spiegazione", "case": "un caso"}


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
    if deep:
        steps.append(("deep", lambda: ("classic", classic(*hits()))))
    if focused and not deep:                          # a follow-up: the sources of the answer before come first
        steps.append(("vault", lambda: ("read", kno_read.from_vault(p, question, hits()[0], "fact" if kind == "fact" else "explain"))))
        steps.append(("web", lambda: ("read", kno_read.from_web(p, question, ev, "fact" if kind == "fact" else "explain",
                                                                 open_pages, translation))))
    elif kind == "fact" and not deep:
        steps.append(("web", lambda: ("read", kno_read.from_web(p, question, ev, "fact", open_pages, translation))))
        steps.append(("vault", lambda: ("read", kno_read.from_vault(p, question, hits()[0], "fact"))))
    else:
        if not deep:
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
            out = {**out, "came_from": where, "learn": kind != "fact" and where in ("web", "memory")}
            return out, None, *(got.get("hits", []), got.get("subs", []))
    say(mode, f"{KIND_IT[kind]} → nessuna fonte")
    return None, None, *(got.get("hits", []), got.get("subs", []))
