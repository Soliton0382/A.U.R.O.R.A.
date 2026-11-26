#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Give every document the key its file name means today (docids.parse), without reading it again: after a change of
the naming rules (I1d: «ABC…_dup_N» is the only copy of ABC…, not another document). Refuses if two files would get
the same key. Run with the services stopped (one writer)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, docids, store  # noqa: E402

if __name__ == "__main__":
    data = config.load().path("EVD_DATA_DIR")
    corpus, findings = store.connect(data, "corpus.db"), store.connect(data, "findings.db")
    rows = corpus.execute("SELECT doc, path FROM documents").fetchall()
    new = {r["doc"]: docids.parse(r["path"]) for r in rows}
    keys = [d.key for d in new.values()]
    if len(set(keys)) != len(keys):
        raise SystemExit("refused: two files would get the same key")
    moved = 0
    for old, d in new.items():
        if old == d.key:
            continue
        corpus.execute("UPDATE documents SET doc=?, collection=?, number=? WHERE doc=?", (d.key, d.collection, d.number, old))
        for t in ("pages", "passages"):
            corpus.execute(f"UPDATE {t} SET doc=? WHERE doc=?", (d.key, old))
        findings.execute("UPDATE identifiers SET doc=? WHERE doc=?", (d.key, old))
        moved += 1
    corpus.commit()
    findings.commit()
    print(f"{moved} documents given their key")
