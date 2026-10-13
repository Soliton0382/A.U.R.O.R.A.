# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Lessons from her own mistakes (owner, 2026-10-13: «questa per aurora è esperienza… non per barare le prossime volte
che faremo i test, ma per aiutarla a fare associazioni e a migliorare ogni volta: più la si usa e più impara»).

A wrong answer of a benchmark (or any graded run) becomes ONE lesson of method — when a question looks like this, do
that — written by the model that reviews it, never its answer: a lesson that holds a number or a word of the expected
answer that the question itself did not hold is refused (_leaks). The lessons live apart from the vault and from the
shadow (which keep facts and answers): <STATUS>/lessons.jsonl, each with the situation it is for («when»), what to do
(«do»), where it came from and how many times it was learned again.
At an answer, the lessons that fit the question (at most two, picked by the route model reading them) are added
to the reading prompts (kno_read) as her experience — only for a run asked with "lessons": true: the trial of 13 Oct
(M191: the same questions 82 → 83 of 98, new ones 92 → 91 of 108, the questions that got a lesson 27 → 27) measured
no effect, so they are off by default; the code stays for a better idea of how to use them.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from . import sys_config, sys_log

MIN_COS = 0.45          # 13 Oct, 33 lessons: best cosine per question p50 0.33, p90 0.51-0.55; at 0.45 16 of 98
                        # questions of the sample they came from get one, 13 of 98 new ones (seed 8): a kind, not an item
TOP = 2
PICK_FROM = 40       # at most this many situations shown to the model (the closest by the encoder first)
_lock = threading.Lock()
_cache: dict = {"mtime": None, "rows": [], "vecs": None}

SYS_LESSON = (
    "You are Aurora reviewing one of your own wrong answers, to do better next time on questions OF THE SAME KIND — "
    "not on this one. What you are (never contradict it): you answer from your own vault of sourced texts, from the "
    "web and from tools on the owner's services, and you know today's date and the time. A grader's key written for "
    "a bare language model — that an AI cannot know the time, that it answers only from its training, that it has no "
    "memory or tools — does not apply to you: when your answer was wrong only against such a key, reply NONE. "
    "not on this one. You get the QUESTION, what was EXPECTED, YOUR ANSWER and the GRADER's reason. Write ONE lesson "
    "of method: «when» — the situation, described in general terms anyone could recognise in a new question (its form, "
    "its kind, a trap it holds), never its topic's facts; «do» — what to do differently, a concrete step of method "
    "(what to check, which source, how to read, when to say you cannot know). FORBIDDEN: the expected answer, any of "
    "its numbers, names or facts, anything specific to this question, and any example or quoted word (no «es.», no "
    "«e.g.», no quotation marks); a lesson that only works for this question "
    "is useless. If the mistake was the grader's or a matter of chance, or no general lesson exists, reply exactly NONE. "
    "Write in Italian. Output only JSON: {\"when\": \"…\", \"do\": \"…\", \"kind\": \"one or two words\"}")

EXAMPLE = re.compile(r"\(\s*(?:es\.|ad es|e\.g\.|eg\b|for example|per esempio)|(?:^|[\s(\[:])['\"«“‘]\w", re.I)
SELF_DENIAL = re.compile(r"(?i)\b(?:not|non|cannot|can't|no)\b[^.]{0,60}\b(?:real[- ]time|current time|clock|orologio|"
                         r"ora attuale|ora corrente)|training (?:data|dataset)|static dataset|persona|addestrament|"
                         r"language models? (?:generate|of base)|modell[oi] linguistic|inability to provide|real-time answer")


def sound(lesson: dict) -> bool:
    """A lesson of method: no example lifted from its question, nothing false of what Aurora is."""
    text = f"{lesson.get('when', '')} {lesson.get('do', '')}"
    return not EXAMPLE.search(text) and not SELF_DENIAL.search(text)
STOP = set("della delle degli dello nella nelle negli sono come anche questo questa quello quella perché quando "
           "about there their which would could should with from that this have been were what your answer".split())


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "lessons.jsonl"


def load(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(f)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ÿ]+", text.lower()) if (len(w) >= 4 or w.isdigit()) and w not in STOP}


def _leaks(lesson: str, question: str, expected: str) -> list[str]:
    """What in the lesson belongs to this question and not to a method: a word or number of the expected answer the
    question did not hold, or a name or number of the question itself («rispondi Carla» is no lesson)."""
    secret = _words(expected) - _words(question)
    names = {w.lower() for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-ZÀ-Ý][\wà-ÿ]{2,}", question)}
    numbers = set(re.findall(r"\d+", question)) | set(re.findall(r"\d+", expected))
    found = _words(lesson)
    return sorted((secret & found) | (names & found) | (numbers & set(re.findall(r"\d+", lesson))))


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def write_lesson(llm, question: str, expected: str, answer: str, why: str) -> dict | None:
    """One lesson from one wrong answer, or None (no general lesson, or one that gives the answer away)."""
    out = llm.complete(SYS_LESSON, f"QUESTION: {question[:2000]}\n\nEXPECTED: {expected[:1200]}\n\nYOUR ANSWER: "
                                   f"{answer[:2000]}\n\nGRADER: {why[:500]}", 300).answer.strip()
    if out.upper().startswith("NONE"):
        return None
    m = re.search(r"\{.*\}", out, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    when, do = str(d.get("when", "")).strip(), str(d.get("do", "")).strip()
    if not when or not do or len(when) + len(do) > 700:
        return None
    if not sound({"when": when, "do": do}):           # an example (the answer in disguise), or a bare model's key
        sys_log.trace("lessons", "lesson.refused", {"why": "example or denies what Aurora is"})
        return None
    leak = _leaks(f"{when} {do}", question, expected)
    if leak:
        sys_log.trace("lessons", "lesson.refused", {"leaks": leak[:10]})
        return None
    return {"when": when, "do": do, "kind": str(d.get("kind", ""))[:40]}


def learn(cfg: sys_config.Config, llm, embedder, rows: list[dict], origin: str, same: float = 0.9) -> dict:
    """Lessons from graded rows [{question, expected, answer, right, why}]: the wrong ones only; one too close to a
    lesson already kept (cosine ≥ `same` between their situations) counts that one again instead of a new one."""
    with _lock:
        kept = load(cfg)
        vecs = _unit(embedder.encode_documents([k["when"] for k in kept])) if kept else np.zeros((0, 1), np.float32)
        made = again = refused = 0
        for r in rows:
            if r.get("right") or not r.get("question"):
                continue
            les = write_lesson(llm, r["question"], str(r.get("expected", "")), str(r.get("answer", "")), str(r.get("why", "")))
            if les is None:
                refused += 1
                continue
            v = _unit(embedder.encode_documents([les["when"]]))[0]
            if len(kept) and vecs.shape[1] == v.shape[0]:
                cos = vecs @ v
                i = int(np.argmax(cos))
                if cos[i] >= same:
                    kept[i]["seen"] = kept[i].get("seen", 1) + 1
                    kept[i]["origins"] = sorted({*kept[i].get("origins", []), origin})[-20:]
                    again += 1
                    continue
            kept.append({"id": uuid.uuid4().hex[:10], **les, "origins": [origin], "made": time.time(), "seen": 1})
            vecs = np.vstack([vecs, v[None, :]]) if len(vecs) and vecs.shape[1] == v.shape[0] else v[None, :]
            made += 1
        _save(cfg, kept)
    sys_log.trace("lessons", "lessons.learned", {"origin": origin, "new": made, "again": again, "none": refused})
    return {"new": made, "again": again, "none": refused, "total": len(kept)}


SYS_PICK = ("Below are numbered LESSONS from your past mistakes — the situation, then what to do — and a new QUESTION. "
            "Pick a lesson only if this question is truly in its situation AND doing what it says would be right for "
            "this question (a forecast, a schedule or the weather can be known: they are not events nobody can know). "
            "At most two, the best first. Most questions need none. Reply with the numbers separated by commas, or "
            "exactly NONE.")


def for_question(cfg: sys_config.Config, embedder, question: str, llm=None, top: int = TOP,
                 min_cos: float = MIN_COS) -> list[dict]:
    """The lessons whose situation fits the question, best first (each use is in the run's trace: event «lessons»).
    With a model (`llm`, the route role) it reads the situations and picks (13 Oct: on the encoder an abstract «when»
    and a concrete question stay far apart — the right lesson at cosine 0.32 — and what passed a threshold did by
    topic, the way to memorising); the encoder alone (`min_cos`) only without a model, or to shorten a long list."""
    f = _file(cfg)
    if not f.exists():
        return []
    with _lock:
        mtime = f.stat().st_mtime
        if _cache["mtime"] != mtime:
            rows = load(cfg)
            _cache.update(mtime=mtime, rows=rows,
                          vecs=_unit(embedder.encode_documents([r["when"] for r in rows])) if rows else None)
        rows, vecs = _cache["rows"], _cache["vecs"]
    if not rows or vecs is None:
        return []
    q = _unit(embedder.encode_queries([question])[0])
    cos = vecs @ q
    if llm is None:
        pick = [int(i) for i in np.argsort(-cos)[:top] if cos[int(i)] >= min_cos]
        return [{**rows[i], "cos": round(float(cos[i]), 3)} for i in pick]
    shown = [int(i) for i in np.argsort(-cos)[:PICK_FROM]]           # a long list: the closest by meaning first
    listing = "\n".join(f"{n}. {rows[i]['when']} → {rows[i]['do'][:220]}" for n, i in enumerate(shown, 1))
    try:
        said = llm.complete(SYS_PICK, f"SITUATIONS:\n{listing}\n\nQUESTION: {question[:1500]}", 12).answer.upper()
    except Exception:                                 # noqa: BLE001 — no lesson rather than a failed answer
        return []
    if "NONE" in said:
        return []
    out = []
    for n in re.findall(r"\d+", said):
        k = int(n) - 1
        if 0 <= k < len(shown) and shown[k] not in [x["_i"] for x in out]:
            out.append({**rows[shown[k]], "cos": round(float(cos[shown[k]]), 3), "_i": shown[k]})
        if len(out) >= top:
            break
    return [{k: v for k, v in x.items() if k != "_i"} for x in out]


def block(lessons: list[dict]) -> str:
    """The lessons as a paragraph for a system prompt ("" when none)."""
    if not lessons:
        return ""
    lines = "\n".join(f"- Quando {x['when'].rstrip('.')}: {x['do']}" for x in lessons)
    return ("\n\nYOUR EXPERIENCE — lessons you drew from your own past mistakes on questions like this one. Apply them "
            "only where they fit; they are method, not facts:\n" + lines)
