# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C463 (ROADMAP N69 c, d): the benchmark's login sealed in its file; the push key the service's alone."""
import importlib.util
import json
import os
from pathlib import Path

from aurora import sys_push
from conftest import private

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "bench_memory_days.py"


def _bench():
    spec = importlib.util.spec_from_file_location("bench_memory_days", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_benchmarks_login_is_sealed_and_read_back(cfg):
    b = _bench()
    d = {"name": "test", "password": "Pw-Zanzibar-1", "totp": "JBSWY3DPEHPK3PXP", "cookie": {"aurora_device": "abc"}}
    sealed = b._sealed_login(cfg, d)
    raw = json.dumps(sealed)
    assert "Zanzibar" not in raw and "JBSWY3" not in raw and "abc" not in raw and sealed["name"] == "test"
    assert b._opened_login(cfg, sealed) == d
    assert b._opened_login(cfg, d) == d                        # a file from before: read as it is


def test_the_push_key_found_open_is_closed_again(cfg):
    pem = sys_push._vapid_pem(cfg)
    os.chmod(pem, 0o660)
    assert sys_push._vapid_pem(cfg) == pem and private(pem)
