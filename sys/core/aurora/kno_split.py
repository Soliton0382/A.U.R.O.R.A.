# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A case told as a story, searched as the questions it holds (C183).

7 October: the owner told a real case — a private legal matter with four problems — and Aurora abstained four
times. Searched whole,
the story found nearby laws with low scores (the re-ranker's best 0.18) and the gate closed; the civil code's
articles on the matter never came up. The same vault, asked short questions on each subject, gives them at
0.97-0.99.

So a long message gets two helps: the provisions a lawyer would read, named by the local model and fetched by
their number (kno_cites), first; and a split by the local model into at most 4 short searches, one per problem, worded like the heading
of a law's index (the subject and the key facts, never the people); each is searched, and the passages each one
found best come first, then the rest by score. The gate and the extraction see the searches too, so a passage that
answers one part of the case counts. Short questions are searched as before.
"""
from __future__ import annotations

import re

SYS_SPLIT = ("The user tells a situation with one or more problems. Write the questions someone would look up in a "
             "reference book to help: one for EACH distinct problem, at most 4. Each is a short, plain question in "
             "natural language (at most 15 words) about the general rule or fact, as a manual, an encyclopedia or, "
             "only when the message is about a right, a duty, a contract, a dispute or a fine, a code of law would "
             "answer it — e.g. «Why does bread go stale faster in the fridge?», «How often should a cactus be "
             "watered?», «Must a shop refund a faulty product?», «Can a neighbour cut branches that cross the "
             "fence?». No people's names, no feelings, no story. {lang} One per line, nothing else.")
# C694: the prompt asked for «the questions a lawyer would look up» with two tenancy examples in Italian, and wrote
# the searches in Italian from the English pivot — in Italian they found Normattiva (a phone getting hot became four
# questions on the legal guarantee). Neutral now, examples of both kinds, in the pivot's language when it is used.
SAME_LANGUAGE, IN_ENGLISH = "Same language as the message.", "Write them in English."
MARK = "THE PROBLEMS IT HOLDS"
SYS_CASE = ("\nTHIS QUESTION IS A CASE told by the owner, with the problems it holds listed after it. For EACH problem, "
            "in its own short paragraph, say what the extracted provisions establish that applies to it (the rule, who "
            "decides, with which majority, who answers for what), each sentence with its citation [n] and worded as the "
            "provision says it. Use only provisions that apply to this kind of building and of people: a law on public "
            "or social housing (edilizia popolare ed economica) or on another sector does not apply to private homes "
            "— leave it out. Do not decide the case and do not write that nothing applies when provisions are "
            "extracted; say only which point the extractions do not cover.")
CASE_NOTE = {"it": "⚖️ Sono le norme che il mio vault contiene su questi punti, non un parere legale: per il vostro caso "
                   "(e per rispondere alle lettere dell'avvocato) serve un avvocato o l'amministratore.",
             "en": "⚖️ These are the provisions my vault holds on these points, not legal advice: your case needs a lawyer."}


EXTRACT_CASE = (" THIS QUESTION IS A CASE: leave out every passage from an act that does not apply to this kind of "
                "building and of people — e.g. the law on public or social housing (edilizia popolare ed economica) for "
                "private homes or villas — even if its words match. A provision that GOVERNS the situation of the case "
                "(common parts, works on one's own unit or on common installations, who decides and with which majority, "
                "the owners' duties and costs) is relevant even when it never names the object of the case: extract "
                "what it says and whom it binds, so that the answer can apply it.")


def is_case(question: str) -> bool:
    return MARK in question


def wanted(question: str, min_chars: int) -> bool:
    """A message long enough to hold more than one problem (0 = never split)."""
    return bool(min_chars) and len(question) >= min_chars


def split(model, question: str, english: bool = False, language: str = "") -> list[str]:
    """At most 4 short searches; in English when the search works on the English pivot (C694), in `language` when
    one is named."""
    out = []
    system = SYS_SPLIT.format(lang=IN_ENGLISH if english else f"Write them in {language}." if language else SAME_LANGUAGE)
    for line in model.complete(system, question, 240).answer.splitlines():
        s = re.sub(r"^[\s\-•*\d.)]+", "", line).strip().strip('"«»')
        if 3 <= len(s) <= 160 and s.lower() not in (x.lower() for x in out):
            out.append(s)
    return out[:4]


def _norm(t: str) -> str:
    return " ".join(re.findall(r"\w+", t.lower()))


def same_message(hit, question: str) -> bool:
    """The owner's own earlier message, the same as this one (asked again): not a source of anything (C183: four
    copies of the case came back as passages at 1.0 and pushed the laws down)."""
    s = hit.soliton
    if s.kind != "conversation" or s.extra.get("role") != "user":
        return False
    a, b = _norm(s.text), _norm(question)
    return bool(a) and (a == b or (len(b) > 60 and (a.startswith(b[:120]) or b.startswith(a[:120]))))


def merge(base: list, found: list[list], top_k: int, first: int = 3) -> list:
    """The best `first` passages of each search, then everything else by the re-ranker's score; each passage once."""
    out, seen = [], set()
    for hits in found:
        for h in hits[:first]:
            if h.sid not in seen:
                seen.add(h.sid)
                out.append(h)
    rest = sorted((h for hits in [base, *found] for h in hits), key=lambda h: -h.rerank)
    for h in rest:
        if h.sid not in seen:
            seen.add(h.sid)
            out.append(h)
    return out[:top_k + len(found)]                   # one more passage per search: the whole's best still fit


def search(pipeline, question: str, whole, ev, run_id: str | None = None, legal: bool = True,
           lang: str = "") -> tuple[list, list[str]]:
    """(hits, problems): a long message searched by its problems and its provisions; `whole()` searches the message
    itself — for a short one, or when the others find nothing (the story whole cost 10 s and found least: M128).
    `legal`: kno_lawgate's answer — False, no provision is named or fetched (C694). `lang`: the language the user
    wrote in."""
    cfg = pipeline.cfg
    if not wanted(question, int(cfg["AURORA_PIPELINE_SPLIT_CHARS"] or 0)):
        return whole(), []
    from . import kno_cites
    from .kno_stages import SYS_TRANSLATE, as_text, untag       # here: kno_stages imports this module (C320)
    cited = kno_cites.hits(pipeline, question, ev) if legal else []    # the provisions a lawyer would read
    # the question is the English pivot: so are its searches — unless the law may answer: a statute is found by its own
    # words (M318: English searches dropped the cases' best law re-rank, e.g. 0.98 → 0.10), so a legal case is split
    # in the user's language and each search translated, as before; the law gate keeps that from everyday stories
    from .kno_stages import LANGS
    pivot = bool(getattr(pipeline, "_pivot", False))
    native = LANGS.get(lang, "") if legal and lang and lang != "en" else ""
    english = pivot and not native
    subs = split(pipeline._for("translate"), question, english, native if pivot else "")
    found = []
    for s in (subs if len(subs) >= 2 else []):
        tr = None if english else untag(pipeline._for("translate").complete(SYS_TRANSLATE, as_text(s), 120).answer)
        found.append(pipeline.search.search(s, tr, candidates=80, run_id=run_id))   # M128: same best as 150, 4.7 s each
    if not cited and not found:
        return whole(), []
    merged = merge([], found, int(cfg["AURORA_SEARCH_TOPK"]))
    top = cited[:6]                                      # the named provisions first: they are what was asked for
    merged = top + [h for h in merged if h.sid not in {c.sid for c in top}]
    ev("retrieval.split", {"searches": subs if found else [], "best": [round(f[0].rerank, 3) if f else None for f in found],
                           "cited": len(top)})
    problems = subs if found else ["the provisions named for the case"]     # still a case: the case's synthesis
    return merged[:int(cfg["AURORA_SEARCH_TOPK"]) + len(found) + len(top)], problems


def with_searches(question: str, subs: list[str]) -> str:
    """The question as the gate and the extraction read it: the story, then the problems it holds."""
    if not subs:
        return question
    return question + f"\n\n{MARK} (a passage that answers any of them, or a provision that governs it, counts):\n" + \
        "\n".join(f"- {s}" for s in subs)
