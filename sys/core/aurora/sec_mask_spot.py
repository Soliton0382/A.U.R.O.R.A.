# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Dynamic masking: the local model reads a text before it leaves for the cloud and names the personal data the fixed
rules of sec_mask cannot see — a person's name, a private place, an employer, a nickname (owner, 28 Oct, after the
conductor's trial sent the owner's surname as a paper's author: «gravissimo!!! privacy è default… rendiamo i
mascheramenti dinamici, se il modello si accorge maschera prima di mandare in cloud»).

What it finds is masked at once and LEARNT: kept in the user's state (mask_learned.json, 0600), so the same value is
masked next time by the fixed rules even when the local model cannot be asked; sealed with the user's key (N64: the
file is a list of the private values themselves). The local model never sees anything
that was not already on this machine; nothing of this pass goes to a cloud. Beside the model, always, two rules mask
what plainly is a person — an initial and a surname («F. Rossi»), a title and a name («Dott. Rossi», «ing. Bianchi»)
(the first live trial: the model missed an author written «F. Surname»); when the local model does not answer (the
music model holds the GPU, it is restarting) those rules and the learnt values are what is left.
Each chunk of text is asked once (its hash kept in memory): a conversation's context is not read again every turn.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict

from . import sys_config, sys_log, sys_seal
from . import sys_users_layout as L

CHUNK = 3000                    # characters asked at once
CACHE = 4000                    # chunks remembered
TIMEOUT_S = 40
MIN_LEN = 3

SPOT = """You protect the privacy of a person before a text is sent to an online AI service. Find in the text the
PRIVATE personal data that simple patterns miss, and copy each one EXACTLY as written (same letters and case).
Include: names of real private people (first names, surnames, an initial with a surname, nicknames, usernames and
handles), relatives, the person's home town or village (also multi-word: «Borgo San Lorenzo»), private places and
street names, names of a private person's employer, school or small company (also multi-word: «Officine Rossi»,
«Studio Bianchi»), and every author's name written in a document or a citation (also as an initial and a surname:
«F. Rossi», «M. Bianchi, 2026»). Read the whole text: list every one, even when there are many.
Exclude: names that are part of a theorem, method, unit, law, algorithm, equation or product (e.g. Walsh functions,
Einstein-Cartan theory, Hadamard matrix, Gauss law, Fourier), famous historical figures, big public companies and
brands, programming words, and placeholders in square brackets like [EMAIL_1].
Reply with JSON only: {"private": ["...", "..."]} — an empty list when there is nothing."""

TITLE = r"(?:Sig\.?r?a?|Sig\.ra|Dott\.?(?:ssa)?|Dr\.?|Ing\.?|Avv\.?|Prof\.?(?:ssa)?|Arch\.?|Geom\.?|Mr\.?|Mrs\.?|Ms\.?)"
LAST_RESORT = [
    re.compile(r"\b[A-Z]\.(?:\s?[A-Z]\.)?\s[A-Z][a-zà-ú]{2,}(?:[- ][A-Z][a-zà-ú]{2,})?\b"),       # F. Rossi, D. C. Coster
    re.compile(rf"(?i:\b{TITLE})\s+[A-Z][a-zà-ú]{{2,}}(?:\s[A-Z][a-zà-ú]{{2,}})?\b"),            # Dott. Rossi, ing. Bianchi
]

_seen: OrderedDict = OrderedDict()
_lock = threading.Lock()


def _file(cfg: sys_config.Config):
    return L.place(cfg, "state", cfg.user) / "mask_learned.json"


def learned(cfg: sys_config.Config) -> list[str]:
    """The values the local model found before, for this user (masked by the fixed rules from now on)."""
    try:
        return [w for w in json.loads(sys_seal.read_any(cfg, _file(cfg), cfg.user)).get("words", []) if len(w) >= MIN_LEN]
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, words: list[str]) -> None:
    sys_seal.write(cfg, _file(cfg), json.dumps({"words": words, "at": time.time()}, ensure_ascii=False).encode("utf-8"),
                   cfg.user, "state")                   # 0600, written through a temporary file


def _learn(cfg: sys_config.Config, words: list[str]) -> None:
    have = set(learned(cfg))
    new = [w for w in words if w not in have]
    if not new:
        return
    _save(cfg, sorted(have | set(new)))
    sys_log.get_logger("security").info("audit: dynamic masking learnt %d new private value(s)", len(new))


def forget(cfg: sys_config.Config, word: str) -> bool:
    """A learnt value taken back by the person (it was not private)."""
    have = learned(cfg)
    if word not in have:
        return False
    _save(cfg, [w for w in have if w != word])
    return True


def _ask(cfg: sys_config.Config, chunk: str) -> list[str] | None:
    """The local model's list for one chunk; None when it cannot be asked."""
    from .mdl_llm import LLM
    llm = LLM(cfg)
    llm.timeout = TIMEOUT_S
    try:
        raw = llm.complete(SPOT, chunk, 400).answer
    except Exception:                                    # noqa: BLE001 — down, busy, swapped out: the last resort
        return None
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        found = json.loads(m.group(0)).get("private", []) if m else []
    except (ValueError, AttributeError):
        return []
    return [w.strip() for w in found if isinstance(w, str) and len(w.strip()) >= MIN_LEN and w.strip() in chunk
            and not w.strip().startswith("[")]


def spot(cfg: sys_config.Config, text: str) -> tuple[list[str], bool]:
    """(the private values found in `text`, whether the local model answered for every chunk)."""
    if not text or not cfg["AURORA_CLOUD_MASK_DYNAMIC"]:
        return [], True
    found, told, whole = [], [], True
    for i in range(0, len(text), CHUNK):
        chunk = text[i:i + CHUNK]
        if not re.search(r"[A-Za-zÀ-ú]{3}", chunk):
            continue
        key = hashlib.sha256(chunk.encode()).hexdigest()
        with _lock:
            hit = _seen.get(key)
        if hit is None:
            hit = _ask(cfg, chunk)
            rules = [m.group(0) for rx in LAST_RESORT for m in rx.finditer(chunk)]   # always, beside the model
            if hit is None:                              # not asked: the rules alone, not remembered
                whole = False
                hit = rules
            else:
                with _lock:
                    _seen[key] = hit
                    while len(_seen) > CACHE:
                        _seen.popitem(last=False)
                told += hit                              # only what the model said is learnt
                hit = hit + rules
        found += hit
    found = sorted(set(found), key=len, reverse=True)
    if told:
        _learn(cfg, told)
    if not whole:
        sys_log.get_logger("security").warning("dynamic masking: the local model did not answer, last-resort rule used")
    return found, whole
