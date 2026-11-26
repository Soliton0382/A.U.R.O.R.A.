# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F5's guard in the code, not only in the prompts (audit, 11 Nov, B24): the names on the protected list (victims,
names the documents redact; the owner's list, network_protected) are masked in every text that leaves the server —
passages, pages, quotes, subjects — and in every text it keeps (questions, answers, notes, leads, the export). In
what is kept as an answer the sensitive identifiers are masked too (accounts and IBANs by their last four: the
owner's rule, «risposte mascherate, fonti in chiaro»). The sources stay as they are: a citation is never masked.

A name is caught in the forms the documents write it: «First Last», «First A. Last», «Last, First», «Ms. Last»,
«F. Last» — the surname alone is not (it would mask every namesake): a guard, not a victim detector."""
from __future__ import annotations

import re
from functools import lru_cache

from . import identifiers

MASK = "[protected]"
TITLES = r"(?:ms|mrs|miss|mr|dr|mx)\.?"


def keys(findings) -> tuple[str, ...]:
    """The protected names' keys (network.key form: «first last»), or none when the network is not built yet."""
    if findings is None:
        return ()
    try:
        return tuple(sorted(r[0] for r in findings.execute("SELECT key FROM network_protected")))
    except Exception:  # noqa: BLE001 — no table yet: nothing protected to mask
        return ()


def _forms(key: str) -> list[str]:
    words = [re.escape(w) for w in key.split()]
    if len(words) < 2:
        return []
    first, last, middle = words[0], words[-1], words[1:-1]
    between = "|".join([r"[a-z]\.?", *middle])
    return [rf"\b{first}\b(?:[\s.]+(?:{between}))*[\s.]+{last}\b",           # First Last, First A. Last
            rf"\b{last}\s*,\s*{first}\b(?:[\s.]+[a-z]\b\.?)?",                 # Last, First (A.)
            rf"\b{TITLES}\s+{last}\b",                                          # Ms. Last
            rf"\b{first[0]}\.\s*{last}\b"]                                      # F. Last


@lru_cache(maxsize=8)
def _rx(ks: tuple[str, ...]):
    forms = [f for k in ks for f in _forms(k)]
    return re.compile("|".join(f"(?:{f})" for f in forms), re.I) if forms else None


def names(text: str, ks: tuple[str, ...]) -> str:
    """The text with every protected name masked."""
    rx = _rx(ks)
    return rx.sub(MASK, text) if rx is not None and text else text


def ids(text: str) -> str:
    """The text with its accounts and IBANs masked to their last four characters (identifiers.masked)."""
    if not text:
        return text
    spans, end = [], -1
    for h in sorted((h for h in identifiers.find(text) if h.kind in ("iban", "account")), key=lambda h: h.start):
        if h.start >= end:                                # an IBAN is also an «account»: one mask, never two
            spans.append(h)
            end = h.end
    for h in reversed(spans):
        text = text[:h.start] + identifiers.masked(h) + text[h.end:]
    return text


def answer(text: str, ks: tuple[str, ...]) -> str:
    """What is kept or shown as an answer: names and identifiers masked."""
    return ids(names(text, ks))
