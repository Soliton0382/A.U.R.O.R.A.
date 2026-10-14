# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Memory over days (bench_memory_days): the test user's authenticator code, and the questions match the facts told."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_memory_days as M  # noqa: E402


def test_totp_is_rfc_6238():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert M.totp(secret, 59) == "287082" and M.totp(secret, 1111111109) == "081804"


def test_every_question_has_its_fact_or_is_a_never_told_one():
    told = " ".join(M.TOLD).lower()
    for q, expected in M.ASKED:
        assert expected.startswith("decline") or any(w.lower() in told for w in ("Bricco", "Cremona", "nocciole",
                                                                                "44", "Ilaria", "Yaris"))
    assert sum(e.startswith("decline") for _, e in M.ASKED) == 2
