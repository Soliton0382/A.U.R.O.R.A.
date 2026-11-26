# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's own tests (sys/evidentia/tests), run with Aurora's: the add-on is code Aurora publishes (27 Nov)."""
import os
import subprocess
import sys
from pathlib import Path

EVD = Path(__file__).resolve().parents[2] / "evidentia"


def test_evidentia_s_own_suite_passes():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EVD_", "AURORA_"))}
    env["EVD_ENV_FILE"] = "/nonexistent"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=EVD, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
