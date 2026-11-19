# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📐 The Lean mathematician in the chat (ROADMAP N144): which messages go to kno_prove, and the answer's badge.

Detected conservatively:
  explicit  «/lean …», «dimostra in Lean: …», «verifica con Lean …», «prove in Lean: …» — always the mathematician;
  implicit  «è vero che …», «dimostra che …», «prove that …», «is it true that …» AND a mathematical sign in the rest
            (a formula, a symbol, a strong word: primo, irrazionale, divisibile, intero, theorem…), at most IMPLICIT_CHARS.
            A claim the model calls not mathematics goes back to the ordinary answer (None).
Never in the anonymous chat, never with an attachment, never with AURORA_PROVE_ENABLED off. The answer carries the
badge — «📐 Verificato in Lean (kernel), enunciato confermato» only for status proved — and the Lean source folded
(a ```lean fold block: md.js draws it collapsed).
"""
from __future__ import annotations

import re
import time

from . import kno_prove, sys_context, txt_lang

IMPLICIT_CHARS = 300
EXPLICIT = re.compile(r"^\s*(?:/lean\b|(?:dimostr(?:a|ami|are)|verific(?:a|ami|are)|prov(?:a|ami|are))\s+(?:in|con)\s+"
                      r"lean\b|(?:prove|check|verify)\s+(?:it\s+)?(?:in|with)\s+lean\b)\s*[:,.\-–]?\s*", re.I)
IMPLICIT = re.compile(r"^\s*(?:(?:ma\s+)?(?:è|e'|é)\s+vero\s+(?:o\s+falso\s+)?che|dimostr(?:a|ami|are)\s+che|"
                      r"prova\s+che|is\s+it\s+true\s+that|prove\s+that|show\s+that|true\s+or\s+false\s*:?)\s+(.+)$",
                      re.I | re.S)
SIGN = re.compile(r"\d\s*[+\-*/^=<>≤≥·×]|[=<>≤≥∀∃√∑∏∫∣≠²³]|\b(?:prim[oi]|irrazional[ei]|razional[ei]|divisibil[ei]|"
                  r"divid[eo]|inter[oi]|natural[ei]|polinomi[oi]?|teorema|congettura|fattoriale|multipl[oi]|"
                  r"primes?|irrational|rational|divisible|divides|integers?|naturals?|polynomials?|theorem|"
                  r"factorial|multiples?)\b", re.I)
PARITY = re.compile(r"\b(?:pari|dispari|even|odd)\b", re.I)


def claim_of(question: str) -> tuple[str, bool] | None:
    """(the claim, explicit) when the message asks for a proof of a mathematical statement, else None."""
    q = str(question or "")
    m = EXPLICIT.match(q)
    if m:
        rest = q[m.end():].strip()
        return (rest, True) if rest else None
    m = IMPLICIT.match(q)
    if not m or len(q) > IMPLICIT_CHARS:
        return None
    rest = m.group(1).strip().rstrip("?").strip()
    if SIGN.search(rest) or (PARITY.search(rest) and re.search(r"\d|\bnumer", rest, re.I)):
        return rest, False
    return None


def wanted(cfg, question: str, attached=None) -> tuple[str, bool] | None:
    if attached or sys_context.anonymous_now() or not kno_prove.enabled(cfg):
        return None
    return claim_of(question)


SAY = {"it": {
    "proved": "📐 **Verificato in Lean (kernel), enunciato confermato.**",
    "not": "📐 **Non verificato in Lean**", "says": "Cosa dice l'enunciato in Lean", "axioms": "Assiomi",
    "tries": "tentativi", "source": "Sorgente Lean",
    "why": {"not_proved": "il kernel di Lean non ha accettato nessuna dimostrazione",
            "refused": "le dimostrazioni proposte usavano costrutti vietati (sorry, axiom…)",
            "unformalised": "non l'ho potuta formalizzare", "error": "errore"},
    "false": "secondo il modello l'affermazione è falsa — opinione del modello, NON verificata in Lean",
    "other": "Lean ha dimostrato un enunciato DIVERSO", "nothing": "Non dico che sia vera né che sia falsa."},
    "en": {
    "proved": "📐 **Verified in Lean (kernel), statement confirmed.**",
    "not": "📐 **Not verified in Lean**", "says": "What the Lean statement says", "axioms": "Axioms",
    "tries": "attempts", "source": "Lean source",
    "why": {"not_proved": "Lean's kernel accepted no proof", "refused": "the proofs offered used forbidden constructs "
            "(sorry, axiom…)", "unformalised": "I could not formalise it", "error": "error"},
    "false": "the model believes the claim false — the model's opinion, NOT verified in Lean",
    "other": "Lean proved a DIFFERENT statement", "nothing": "I am not saying it is true, nor false."}}


def badge(r: dict, lang: str = "it") -> str:
    """The answer's text: the badge first, what backs it, the Lean source folded."""
    s = SAY["en" if lang == "en" else "it"]
    n = f"{len(r['attempts'])} {s['tries']}, {r['seconds']} s"
    if r["status"] == "proved":
        out = [s["proved"], "", r["claim"], "", f"{s['says']}: {r.get('says') or '—'}",
               f"{s['axioms']}: {', '.join(r.get('axioms') or []) or '—'} ({n})."]
    else:
        why = s["false"] if r.get("believed_false") else s["why"][r["status"]]
        detail = f": {r['reason']}" if r.get("reason") else ""
        out = [f"{s['not']} — {why}{detail} ({n}).", "", r["claim"]]
        if r.get("kernel_proved"):
            k = r["kernel_proved"]
            out += ["", f"{s['other']}: {k.get('says') or '—'} ({k.get('why', '')})."]
        out += ["", s["nothing"]]
    src = r.get("lean_source") or ""
    if src:
        out += ["", f"{s['source']}:", "```lean fold", src.rstrip("\n").replace("```", "`` `"), "```"]
    return "\n".join(out)


def answer(p, cfg, question: str, emit, run_id: str, remember: bool = True, attached=None):
    """The chat's answer when the message asks for a proof (None: the ordinary path answers)."""
    hit = wanted(cfg, question, attached)
    if hit is None:
        return None
    claim, explicit = hit
    from .kno_trail import Answer, Trail
    from .sol_schema import now_iso
    asked, t0 = now_iso(), time.time()
    emit("route", {"mode": "prove", "explicit": explicit})
    r = kno_prove.prove(cfg, claim, local=getattr(p, "llm", None), emit=emit)
    if not explicit and r["status"] == "unformalised":
        return None                                       # not mathematics after all: the ordinary answer
    lang = "en" if txt_lang.detect(question) == "en" else "it"
    ans = Answer(run_id, question, badge(r, lang), False, [], [], round(time.time() - t0, 2), mode="prove")
    emit("answer.final", {"text": ans.text, "abstained": False, "sources": [], "dropped": [], "mode": "prove",
                          "seconds": ans.seconds, "prove": {k: r[k] for k in ("status", "claim", "axioms", "says",
                                                                              "reason", "seconds", "cost",
                                                                              "believed_false")}
                          | {"attempts": len(r["attempts"]), "fidelity": r.get("fidelity"),
                             "kernel_proved": bool(r.get("kernel_proved"))}})
    if remember:
        p.remember(question, ans, run_id, emit, Trail(), asked)
    emit("run.end", {"seconds": ans.seconds})
    return ans
