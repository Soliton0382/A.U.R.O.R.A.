# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📚 The sources a question is answered from, chosen in the chat (owner, 20 Nov: «invece che creare chat dedicate,
potremmo mettere dei bottoni come quella sulla profondità di ragionamento... che fanno prendere il retrieval nel vault
verso domini specifici o in modalità automatica»).

    auto      nothing chosen: every domain, the law let in by kno_lawgate — as before, unchanged
    legal     only the statutes (law_*): kno_cites also on a short question, CASE_NOTE always, no web (mode «vault»)
    a group   only its domains of the vault (GROUPS: the real taxonomy's ids, every knowledge domain in exactly one)

Several may be chosen together (their domains joined). A domain id of the taxonomy is accepted as well; anything else
is refused (the API answers 422). The choice only narrows: the search reads the same indexes with the same rules
(whose memory, what is private), and keeps fewer of them — it can never bring in what the search would not.
The memory (the conversations) is no source under a choice; the attached files of the question stay first.
"""
from __future__ import annotations

from . import kno_lawgate
from .sol_schema import load_taxonomy

AUTO = "auto"
LEGAL = "legal"
# the groups of the menu, in its order: (icon, domains). The domains are the taxonomy's (config/taxonomy.json), each
# knowledge domain in exactly one group (tests/test_scope.py); «legal» is every law_* domain the taxonomy holds
GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    LEGAL: ("⚖️", ()),
    "medicine": ("🩺", ("medicine", "biomedicine", "genomics", "psychology")),
    "science": ("🔬", ("mathematics", "statistics", "physics", "quantum_physics", "particle_physics", "condensed_matter",
                      "astrophysics", "relativity", "mathematical_physics", "nonlinear_science", "chemistry",
                      "materials", "earth_science")),
    "technology": ("💻", ("artificial_intelligence", "computer_science", "network_security", "cyber_security",
                         "programming", "information_theory", "engineering", "robotics", "patents")),
    "humanities": ("📜", ("history", "society", "philosophy", "religion", "literature")),
    "economics": ("💰", ("economics",)),
    "general": ("📖", ("general",)),
}
NAMES = {"it": {LEGAL: "Legale", "medicine": "Medicina", "science": "Scienze", "technology": "Tecnologia",
                "humanities": "Storia e società", "economics": "Economia", "general": "Cultura generale"},
         "en": {LEGAL: "Legal", "medicine": "Medicine", "science": "Science", "technology": "Technology",
                "humanities": "History and society", "economics": "Economics", "general": "General knowledge"}}
LINE = {"it": ("📚 Ho cercato solo in: {where}", "fonti citate: {used}", "nessuna fonte citata"),
        "en": ("📚 Searched only in: {where}", "sources cited: {used}", "no source cited")}


def knowledge(taxonomy: dict | None = None) -> dict[str, dict]:
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    return {k: v for k, v in tax.items() if not v.get("memory")}


def domains_of(item: str, taxonomy: dict | None = None) -> tuple[str, ...]:
    """The vault's domains of a group or of a domain id; () when it is neither (or a memory domain)."""
    tax = knowledge(taxonomy)
    if item == LEGAL:
        return tuple(sorted(d for d in tax if kno_lawgate.is_legal_domain(d)))
    if item in GROUPS:
        return tuple(d for d in GROUPS[item][1] if d in tax)
    return (item,) if item in tax else ()


def parse(raw, taxonomy: dict | None = None) -> dict | None:
    """The request's «sources» (a list, or a comma-separated text) as {"chosen", "domains", "legal"}; None for auto
    (nothing, or «auto» alone). ValueError on anything that is not a group or a knowledge domain of the taxonomy."""
    if raw is None or raw == "" or raw == []:
        return None
    items = raw.split(",") if isinstance(raw, str) else raw
    if not isinstance(items, list) or len(items) > 40:
        raise ValueError("sources: a list of groups or domains")
    chosen, bad = [], []
    for x in items:
        k = str(x or "").strip().lower() if isinstance(x, str) else None
        if k == AUTO or k == "":
            continue
        if k is None or not domains_of(k, taxonomy):
            bad.append(str(x)[:40])
        elif k not in chosen:
            chosen.append(k)
    if bad:
        raise ValueError(f"sources: unknown {', '.join(bad)} (one of auto, {', '.join(GROUPS)}, or a domain of the vault)")
    if not chosen:
        return None
    doms = sorted({d for k in chosen for d in domains_of(k, taxonomy)})
    return {"chosen": chosen, "domains": doms, "legal": any(kno_lawgate.is_legal_domain(d) for d in doms)}


def allowed(hit, choice: dict | None) -> bool:
    """A passage the choice keeps: one of its domains, or a file attached to this question."""
    if choice is None:
        return True
    return getattr(hit, "query_used", "") == "attachment" or getattr(hit.soliton, "domain", "") in choice["domains"]


def restrict(hits: list, choice: dict | None, ev) -> list:
    """The passages outside the chosen domains left out (a provision named by kno_cites is a law_* passage too)."""
    if choice is None:
        return hits
    out = [h for h in hits if not allowed(h, choice)]
    if out:
        ev("retrieval.filter", {"outside_sources": len(out)})
    return [h for h in hits if allowed(h, choice)]


def used(sources: list[dict]) -> dict[str, int]:
    """How many cited sources came from each domain (a web page has none: «web»)."""
    out: dict[str, int] = {}
    for s in sources or []:
        d = s.get("domain") or "web"
        out[d] = out.get(d, 0) + 1
    return out


def label(item: str, lang: str, taxonomy: dict | None = None) -> str:
    lang = "it" if lang == "it" else "en"
    if item in GROUPS:
        return f"{GROUPS[item][0]} {NAMES[lang][item]}"
    d = knowledge(taxonomy).get(item, {})
    return d.get(lang) or d.get("en") or item


def line(choice: dict, cited: dict[str, int], lang: str) -> str:
    """The answer's last line: where she searched, and where the cited sources came from."""
    lang = "it" if lang == "it" else "en"
    where, has, none = LINE[lang]
    what = has.format(used=", ".join(f"{d} ({n})" for d, n in sorted(cited.items(), key=lambda x: -x[1]))) if cited else none
    return where.format(where=", ".join(label(k, lang) for k in choice["chosen"])) + f" · {what}."


def event(choice: dict, cited: dict[str, int]) -> dict:
    return {"chosen": choice["chosen"], "searched": choice["domains"], "legal": choice["legal"], "used": cited}
