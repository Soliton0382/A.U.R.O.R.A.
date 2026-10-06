# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C158: a test wrote the installation's real .env (15 settings reset, restored from the copy the code had made). The
real .env is looked at when the tests are collected, before any runs; this file runs last and fails if it changed."""
import hashlib
from pathlib import Path

REAL = Path(__file__).resolve().parents[3] / ".env"
BEFORE = hashlib.sha256(REAL.read_bytes()).hexdigest() if REAL.is_file() else None


def test_no_test_changed_the_real_env():
    now = hashlib.sha256(REAL.read_bytes()).hexdigest() if REAL.is_file() else None
    assert now == BEFORE, "a test changed the installation's real .env"
