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


def run_suite(base: Path, select: str = "", timeout: int = 1800, caged: bool = False) -> dict:
    """pytest on <base>/sys/core/tests without the GPU tests. {"ok", "passed", "failed", "summary", "output"}.
    `caged`: a sandbox's code, written by the agent and not reviewed yet — run in the projects' cage (prj_run: no
    network, no home, no .env, no host sockets, only the sandbox writable). C420, 28 Oct: those tests ran inside
    aurora-api itself, before any approval — a test file written by a prompt-injected agent was code run as the API."""
    core = base / "sys" / "core"
    expr = "not gpu" + (f" and ({select})" if select else "")
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rfE", "-k", expr, str(core / "tests")]
    t0 = time.time()
    if caged:
        import shlex
        from . import prj_run
        run = prj_run.cage(None, base, f"PYTHONPATH={shlex.quote(f'{core}:{core / 'tests'}')} " + shlex.join(cmd))
        r = subprocess.run(run, capture_output=True, text=True, timeout=timeout)
    else:
        env = dict(os.environ, PYTHONPATH=f"{core}:{core / 'tests'}", PYTHONDONTWRITEBYTECODE="1")
        for k in ("AURORA_ENV_FILE", "AURORA_PLUGIN", "AURORA_IN_SANDBOX"):   # tests build their own .env, and are not
            env.pop(k, None)                          # a plugin: run from the self plugin's cage they failed 5 (C144)
        r = subprocess.run(cmd, cwd=base, env=env, capture_output=True, text=True, timeout=timeout)
    out = r.stdout + r.stderr
    last = out.strip().splitlines()[-1] if out.strip() else ""
    num = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", last)) else 0
    return {"ok": r.returncode == 0, "passed": num("passed"), "failed": num("failed") + num("error"),
            "summary": last, "seconds": round(time.time() - t0, 1), "output": out[-6000:]}
