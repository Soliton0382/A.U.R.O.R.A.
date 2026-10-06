# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Language of a text, for choosing the query language per passage.

A stop-word vote between Italian and English: the only two languages the vault
distinguishes today. Measured on the previous store: 3,882 English and 118
Italian chunks out of 4,000 (M7). Anything else counts as English.
"""
from __future__ import annotations

import re

_IT = set("il lo la gli le un una di del della dei delle che è non per con sono come anche più questo questa "
          "quale quali perché perche cosa quando dove se ma nel nella sul sulla al alla da dal si mi ti ci "
          # the words of a chat (C156: «brava aurora hai descritto davvero la foto…» was read as English)
          "ho hai ha abbiamo avete hanno sei siamo era fa fai fare puoi può posso voglio vorrei dimmi spiegami "
          "grazie ciao brava bravo molto tutto tutti sempre ancora oggi ieri domani adesso allora io tu lui lei noi "
          "voi loro mio mia tuo tua suo sua miei tuoi davvero modo cos quanto quanta quante quanti due tre farà "
          "c'è po ai dei negli nelle sugli tra fra".split())
_EN = set("the of and to is that for with as are this by be which from on an it was were what how why "
          "when where who does do not you your my i have has had can could would will there they we he she "
          "about thank thanks please hi hello".split())
_WORD = re.compile(r"[a-zàèéìòù']+")


def detect(text: str) -> str:
    """"it" or "en". On a tie, the share of words ending in a vowel decides: Italian words almost all do (measured on
    the owner's 108 messages and 900 English arXiv passages, M115)."""
    words = [w.strip("'") for w in _WORD.findall(text.lower()[:2000])]
    it = sum(w in _IT for w in words)
    en = sum(w in _EN for w in words)
    if it != en:
        return "it" if it > en else "en"
    long = [w for w in words if len(w) > 2]
    return "it" if long and sum(w[-1] in "aeiouàèéìòù" for w in long) / len(long) >= 0.7 else "en"
