#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""B2, B3: the identifiers of the pages already read, found again with today's rules (identifiers.find) — only the
pages that hold the kinds asked, only those kinds replaced, in one transaction. CPU only.

    .venv/bin/python sys/evidentia/script/evd_reidentify.py              # IBAN and tail numbers (the rules of 12 Nov)
    .venv/bin/python sys/evidentia/script/evd_reidentify.py --dry-run    # only the counts, nothing written
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, identifiers, store  # noqa: E402

KINDS = ("iban", "tail")


def again(corpus, findings, kinds=KINDS, dry: bool = False) -> dict:
    marks = ",".join("?" * len(kinds))
    pages = findings.execute(f"SELECT DISTINCT doc, page FROM identifiers WHERE kind IN ({marks})", kinds).fetchall()
    before = Counter(dict(findings.execute(f"SELECT kind, COUNT(*) FROM identifiers WHERE kind IN ({marks}) "
                                           "GROUP BY kind", kinds).fetchall()))
    rows = []
    for doc, page in pages:
        t = corpus.execute("SELECT text FROM pages WHERE doc = ? AND page = ?", (doc, page)).fetchone()
        for h in identifiers.find(t[0] if t else ""):
            if h.kind in kinds:
                rows.append((h.kind, h.value, int(h.valid), doc, page, h.start, h.end))
    after = Counter(r[0] for r in rows)
    if not dry:
        with findings:                                    # one transaction: all of it or none
            findings.executemany(f"DELETE FROM identifiers WHERE doc = ? AND page = ? AND kind IN ({marks})",
                                 [(d, p, *kinds) for d, p in pages])
            findings.executemany("INSERT INTO identifiers(kind, value, valid, doc, page, start, end) "
                                 "VALUES (?,?,?,?,?,?,?)", rows)
    return {"pages": len(pages), "before": dict(before), "after": dict(after), "written": not dry}


def main(argv: list[str]) -> int:
    data = config.load().path("EVD_DATA_DIR")
    findings = sqlite3.connect(data / "findings.db", timeout=60)
    findings.execute("PRAGMA journal_mode=WAL")
    corpus = store.connect(data, "corpus.db", readonly=True)
    print(again(corpus, findings, dry="--dry-run" in argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
