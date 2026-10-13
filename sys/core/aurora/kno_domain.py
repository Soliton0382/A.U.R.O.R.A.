# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A document's domain chosen by what it says, not by the list it came from (owner, 2026-10-13: «documenti in domini
sbagliati… si allena e si sceglie un solo metodo… harvester deve essere una roccia»).

The Wikipedia harvester put an article in the domain of its LIST («Philosophy and religion» → religion: «Philosophy
of science» in religion): right 42% of the time against a reference (M195). A model that reads the title and the start
of the document, with each domain's description (taxonomy.json «about»), chooses one; an answer that is not a domain
keeps the list's. arXiv keeps its own: the paper's primary category says it."""
from __future__ import annotations

import re

from .sol_schema import load_taxonomy

SYS = ("You assign a document to ONE domain of a library, the one it is mainly about. DOMAINS (id (name: what goes "
       "there)): {domains}. «general» only when no other domain fits. Reply with the domain id only.")


def _domains() -> tuple[list[str], str]:
    tax = {k: v for k, v in load_taxonomy().items() if not v.get("memory")}
    ids = sorted(tax)
    return ids, "; ".join(f"{k} ({tax[k]['en']}: {tax[k].get('about', '')})" for k in ids)


def choose(llm, title: str, text: str, fallback: str) -> str:
    """The domain the document is about, read by `llm` (the route role's model); `fallback` when the answer is not
    a knowledge domain or the model fails."""
    ids, names = _domains()
    try:
        out = llm.complete(SYS.format(domains=names), f"TITLE: {title}\n\nSTART: {text[:900]}", 12).answer.strip().lower()
    except Exception:                                 # noqa: BLE001 — the model down: the list's domain, as before
        return fallback
    m = re.search(r"[a-z_]+", out)
    return m.group(0) if m and m.group(0) in ids else fallback
