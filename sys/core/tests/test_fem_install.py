# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N155: FEniCSx is installed pinned — micromamba by version and SHA-256 written in the script, every package of the
environment by URL and MD5 from the lock — and only under sys/runtime (nothing in apt, nothing in the system)."""
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
SCRIPT = (CORE / "script" / "sys_fem_install.sh").read_text(encoding="utf-8")
LOCK = (CORE / "config" / "fenicsx.lock").read_text(encoding="utf-8")


def test_micromamba_is_pinned_by_version_and_sha256():
    assert re.search(r"^MM_VERSION=\d+\.\d+\.\d+-\d+$", SCRIPT, re.M)
    assert re.search(r"^MM_SHA256=[0-9a-f]{64}$", SCRIPT, re.M)
    assert "sha256sum -c" in SCRIPT and "latest" not in SCRIPT


def test_the_environment_comes_from_the_lock_only_under_sys_runtime():
    assert '--file "$LOCK"' in SCRIPT and "D=sys/runtime/fenicsx" in SCRIPT
    code = "\n".join(r for r in SCRIPT.splitlines() if not r.lstrip().startswith("#"))
    assert not re.search(r"\b(apt|apt-get|sudo|pip install)\b", code)


def test_every_locked_package_has_a_conda_forge_url_and_an_md5():
    rows = [r for r in LOCK.splitlines() if r and not r.startswith(("#", "@"))]
    assert "@EXPLICIT" in LOCK and len(rows) > 100
    assert all(r.startswith("https://conda.anaconda.org/conda-forge/") and re.search(r"#[0-9a-f]{32}$", r) for r in rows)
    assert any("/fenics-dolfinx-0.9." in r for r in rows)
