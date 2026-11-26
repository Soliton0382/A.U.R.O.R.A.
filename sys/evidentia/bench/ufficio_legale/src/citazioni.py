#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The refused citations of a run, by kind: stitched with «...» (the model's words around real ones) or not on the page
at all. Evidentia's venv, EVD_ENV_FILE=../evd.env. Usage: python -I citazioni.py ../risultati/<run>.jsonl"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sys" / "core"))
from evidentia import config, leads, store  # noqa: E402

corpus = store.connect(config.load().path("EVD_DATA_DIR"), "corpus.db", readonly=True)
tot = {"citations": 0, "held": 0, "stitched_with_ellipsis": 0, "not_on_page": 0, "no_such_page": 0, "format": 0}
for line in Path(sys.argv[1]).read_text().splitlines():
    ans = json.loads(line)["run"]["answer"]
    cites = [c for c in (ans.get("citazioni") or []) if isinstance(c, dict)]
    kept, refused = leads.check(corpus, cites)
    tot["citations"] += len(cites)
    tot["held"] += len(kept)
    for r in refused:
        q = str(r.get("quote", ""))
        if r.get("why") == "the page does not say these words":
            tot["stitched_with_ellipsis" if ("..." in q or "…" in q) else "not_on_page"] += 1
        elif r.get("why") == "no such page":
            tot["no_such_page"] += 1
        else:
            tot["format"] += 1
print(json.dumps(tot))
