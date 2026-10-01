# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run Aurora's test suite with her own environment, on the live code or on a sandbox copy."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path


def run_suite(base: Path, select: str = "", timeout: int = 1800) -> dict:
    """pytest on <base>/sys/core/tests without the GPU tests. {"ok", "passed", "failed", "summary", "output"}."""
    core = base / "sys" / "core"
    expr = "not gpu" + (f" and ({select})" if select else "")
    env = dict(os.environ, PYTHONPATH=f"{core}:{core / 'tests'}", PYTHONDONTWRITEBYTECODE="1")
    env.pop("AURORA_ENV_FILE", None)                 # tests build their own .env: never the real one
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rfE", "-k", expr, str(core / "tests")],
                       cwd=base, env=env, capture_output=True, text=True, timeout=timeout)
    out = r.stdout + r.stderr
    last = out.strip().splitlines()[-1] if out.strip() else ""
    num = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", last)) else 0
    return {"ok": r.returncode == 0, "passed": num("passed"), "failed": num("failed") + num("error"),
            "summary": last, "seconds": round(time.time() - t0, 1), "output": out[-6000:]}
