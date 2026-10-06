# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A backup stays restorable after an update (owner, 2026-10-06): every format step has its migration."""
from aurora import sys_formats as F


def test_every_step_of_every_format_has_a_migration():
    for k, v in F.FORMATS.items():
        for n in range(1, v):
            assert (k, n) in F.MIGRATIONS and (k, n) in F.MIGRATE, f"{k}: no migration {n}→{n + 1}"


def test_the_verdicts():
    assert F.compare(dict(F.FORMATS))["verdict"] == "same"
    assert F.compare(None)["verdict"] == "unknown"
    newer = {**F.FORMATS, "soliton": F.FORMATS["soliton"] + 1}
    assert F.compare(newer)["verdict"] == "newer" and "update Aurora" in F.compare(newer)["why"]
    older = {**F.FORMATS, "layout": 0}
    assert F.compare(older)["verdict"] == "newer"                          # 0→1 has no migration: refused, never guessed
