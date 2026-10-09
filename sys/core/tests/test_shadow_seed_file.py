# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The seed published with the code (config/shadow_seed.json): every new installation's users start with it (owner,
9 Oct: «i git clone partano già con un set di ombre già presenti»). It leaves this machine: only answers whose every
source is public, none twice, none empty."""
import json
from pathlib import Path

from aurora import kno_shadow

SEED = Path(__file__).resolve().parents[1] / "config" / "shadow_seed.json"


def test_the_published_seed_cites_only_public_sources_once_each():
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    assert len(rows) >= 100
    questions = [r["question"] for r in rows]
    assert len(set(questions)) == len(questions)
    for r in rows:
        assert r["answer"].strip() and kno_shadow.public(r["sources"]), r["question"]
