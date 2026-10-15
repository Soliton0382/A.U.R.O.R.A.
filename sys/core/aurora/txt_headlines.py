# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The news plugin's rows read back as headlines (☀️ Oggi's strip, api/today): «- [dd/mm HH:MM] title — source»,
then the summary and the link, each on its own line."""
from __future__ import annotations

import re

ROW = re.compile(r"^- \[(?P<when>[^\]]*)\] (?P<title>.+?) — (?P<source>[^\n]+)\n\s+(?P<summary>[^\n]*)\n\s+(?P<link>\S+)", re.M)


def headlines(text: str) -> list[dict]:
    return [m.groupdict() for m in ROW.finditer(text)]


def key(title: str) -> str:
    """The same story told by two feeds: one headline."""
    return re.sub(r"\W+", "", title.lower())[:60]
