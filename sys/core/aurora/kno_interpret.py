# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The interpreter (ROADMAP N44, owner 24 Oct: «mentre parlo le introduce simultaneamente quello che dico in una lingua
che voglio e viceversa»): a sentence heard in one language, written and said in the other. The sentence is cut by the
pause that ends it (the page's vad.js), heard by Whisper in the speaker's own language, translated by the model the
owner gave to «translate» (the local one by default: 0.3 s a sentence, M256), with the last lines of the conversation
for context. Nothing is kept: no memory, no conversation, only an audit line without the words."""
from __future__ import annotations

from .kno_stages import LANGS, as_text, untag

CONTEXT = 4                                          # lines of the conversation so far given with each sentence

SYS = ("You are a simultaneous interpreter between two people. Translate the {src} sentence inside <text> into {dst}, "
       "as a person would say it aloud: the same meaning and register, names and numbers kept. Lines before it, if any, "
       "are the conversation so far, only for context: never translate them again. Output only the {dst} sentence.")


def check(src: str, dst: str) -> tuple[str, str]:
    """The two languages as codes Whisper and the voices know, or ValueError."""
    src, dst = str(src or "").lower()[:2], str(dst or "").lower()[:2]
    for code in (src, dst):
        if code not in LANGS:
            raise ValueError(f"unknown language «{code}»: one of {', '.join(sorted(LANGS))}")
    if src == dst:
        raise ValueError("the two languages are the same")
    return src, dst


def prompt(text: str, before: list[str] | tuple = ()) -> str:
    lines = [str(x).strip()[:400] for x in list(before)[-CONTEXT:] if str(x).strip()]
    return ("Conversation so far:\n" + "\n".join(lines) + "\n\n" if lines else "") + as_text(text)


def translate(llm, text: str, src: str, dst: str, before: list[str] | tuple = ()) -> str:
    """The sentence in `dst`; empty for an empty sentence."""
    text = str(text or "").strip()
    if not text:
        return ""
    out = llm.complete(SYS.format(src=LANGS[src], dst=LANGS[dst]), prompt(text, before),
                       max(64, len(text) * 2), think=False)
    return untag(str(getattr(out, "answer", out)))
