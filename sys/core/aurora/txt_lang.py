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
          "quale quali perché cosa quando dove se ma nel nella sul sulla al alla da dal si mi ti ci".split())
_EN = set("the of and to in is that for with as are this by be which from on an it was were what how why "
          "when where who does do not".split())
_WORD = re.compile(r"[a-zàèéìòù]+")


def detect(text: str) -> str:
    words = _WORD.findall(text.lower()[:2000])
    it = sum(w in _IT for w in words)
    en = sum(w in _EN for w in words)
    return "it" if it > en else "en"
