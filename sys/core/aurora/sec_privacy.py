# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What a public text (a social post, a bug report) would give away, and a proposed safer text (owner, 2026-10-05:
Aurora's posts drawn from her reflections sometimes named him or his daughter).

findings(text) lists every piece found, each with a proposed replacement:
- everything the cloud masking finds (sec_mask: e-mails, phones, addresses, tax codes, IBANs, IPs, keys, the
  owner's words: name, place, AURORA_CLOUD_MASK_WORDS);
- the people this installation knows: every user's login name and the name the assistant calls them;
- other proper names: read by the LOCAL model (private person, public figure or place: a private person is replaced,
  a place proposed, a famous name left); without the model, by a rule (a capitalised word that is not an ordinary
  word of the dictionary), marked "possible": shown, the owner chooses.
propose(text, picked) applies the chosen replacements. Nothing is sent anywhere: a pure function on the text.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from . import sec_mask, sys_config

REPLACE = {   # what a public text says instead
    "it": {"PERSON": "una persona a me cara", "PLACE": "la mia città", "OTHER": "[omesso]"},
    "en": {"PERSON": "someone dear to me", "PLACE": "my town", "OTHER": "[omitted]"},
}
PEOPLE = {    # the 1st, 2nd, then every other person, so that two people do not become the same words
    "it": ("una persona a me cara", "un'altra persona cara", "qualcuno"),
    "en": ("someone dear to me", "another dear person", "someone"),
}


def _distinct(found: list[dict], lang: str) -> list[dict]:
    names = PEOPLE.get(lang[:2], PEOPLE["en"])
    n = 0
    for f in found:
        if f["kind"] in ("PERSON", "NAME?"):
            f["replacement"] = names[min(n, 2)]
            n += 1
    return found
WORD = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ'’]{2,}\b")
SENTENCE_START = re.compile(r"(^|[.!?…:\n]\s*|[\"«“(]\s*)$")
DICTS = ("/usr/share/dict/words", "/usr/share/dict/italian", "/usr/share/dict/american-english",
         "/usr/share/dict/british-english")


@functools.lru_cache(maxsize=1)
def _dictionary() -> tuple[frozenset, frozenset]:
    """(ordinary words in lower case, proper nouns as the dictionaries write them)."""
    lower, proper = set(), set()
    for f in DICTS:
        if Path(f).is_file():
            for w in Path(f).read_text(encoding="utf-8", errors="ignore").split():
                w = w.split("'")[0]
                (proper if w[:1].isupper() else lower).add(w if w[:1].isupper() else w.lower())
    return frozenset(lower), frozenset(proper)


def _people(cfg: sys_config.Config) -> list[str]:
    """Names of the people this installation knows: users and the names the assistant calls them."""
    names = {str(cfg.values.get("AURORA_OWNER_NAME") or "")}
    try:
        from . import sys_user_config, sys_users, sys_users_layout
        base = cfg.base or cfg
        if sys_users_layout.migrated(base):
            for u in sys_users.Users(base).list():
                names.add(u["name"])
                names.add(str(sys_user_config.for_user(base, u["name"]).values.get("AURORA_OWNER_NAME") or ""))
    except Exception:                                  # noqa: BLE001 — a single-user install has no users store
        pass
    return sorted({n for n in names if len(n) >= 3}, key=len, reverse=True)


NAMES_PROMPT = ("You find people's and places' names in a text that is about to be published. List every proper "
                "name in it, each once, as JSON: [{\"name\": \"...\", \"type\": \"private\" | \"public\" | "
                "\"place\"}]. private = a real person who is not famous (a relative, a friend, the author, a user); "
                "public = a famous person or a character everyone knows (a scientist, a writer, a god); place = a "
                "city, a street, a region (not the Moon or the planets). Answer with the JSON only, [] when none.")


def _llm_names(text: str, llm) -> list[dict] | None:
    """The local model's reading of the names (None when it cannot answer: then the rule decides)."""
    import json
    try:
        out = llm.complete(NAMES_PROMPT, text[:4000], 400).answer
        m = re.search(r"\[.*\]", out, re.S)
        rows = json.loads(m.group(0)) if m else []
        return [r for r in rows if isinstance(r, dict) and isinstance(r.get("name"), str)]
    except Exception:                                  # noqa: BLE001 — the model down or a malformed answer
        return None


def findings(text: str, cfg: sys_config.Config | None = None, lang: str = "it", llm=None) -> list[dict]:
    """[{"kind", "value", "replacement", "sure"}] in the order they appear, each value once. `llm`: the LOCAL model
    (the text may hold private data: it never goes to a cloud model for this)."""
    cfg = cfg or sys_config.get()
    rep = REPLACE.get(lang[:2], REPLACE["en"])
    out: dict[str, dict] = {}
    place = str(cfg.values.get("AURORA_WEATHER_PLACE") or "")
    assistant = {str(cfg.values.get("AURORA_ASSISTANT_NAME") or "Aurora"), "Aurora"}

    def add(kind, value, sure=True):
        if value and value not in out and value not in assistant:
            kind_rep = "PERSON" if kind in ("PERSON", "NAME?") else "PLACE" if kind == "PLACE" else "OTHER"
            out[value] = {"kind": kind, "value": value, "replacement": rep[kind_rep], "sure": sure,
                          "at": text.find(value)}

    for n in _people(cfg):
        for m in re.finditer(rf"\b{re.escape(n)}\b", text, re.I):
            add("PERSON", m.group(0))
    p = sec_mask.Pseudonymizer(cfg)
    p.mask(text)
    for value, ph in p.to_ph.items():
        kind = ph.strip("[]").rsplit("_", 1)[0]
        add("PLACE" if value == place else "PERSON" if kind == "PRIVATE" else kind, value)
    names = _llm_names(text, llm) if llm is not None else None
    if names is not None:                              # the model read the names: private people and places
        for r in names:
            if r["name"] in text and r.get("type") == "private":
                add("PERSON", r["name"])
            elif r["name"] in text and r.get("type") == "place":
                add("PLACE", r["name"], sure=False)
        return _distinct(sorted(out.values(), key=lambda f: f["at"]), lang)
    lower, proper = _dictionary()
    for m in WORD.finditer(text):
        w = m.group(0)
        start = bool(SENTENCE_START.search(text[:m.start()]))
        if w.lower() in lower and (start or w not in proper):
            continue                                   # an ordinary word (capitalised to open a sentence)
        if start and w not in proper:
            continue                                   # opens a sentence and is in no dictionary: too unsure
        add("NAME?", w, sure=False)
    return _distinct(sorted(out.values(), key=lambda f: f["at"]), lang)


def propose(text: str, picked: list[dict]) -> str:
    """The text with the chosen findings replaced, the longest first (a full name before its first name)."""
    for f in sorted(picked, key=lambda f: len(f["value"]), reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(f['value'])}(?!\w)", f["replacement"], text)
    return text
