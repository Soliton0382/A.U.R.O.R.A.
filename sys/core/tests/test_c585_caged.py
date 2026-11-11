# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C585: the suite passes inside the cage the sandbox stage of a change runs it in — what a cage takes away on purpose
skips its test with the reason, the rest runs."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import conftest

ROOT = Path(__file__).resolve().parents[3]


def test_the_host_is_not_a_user_namespace_and_a_cage_is():
    if conftest.in_a_user_namespace():
        pytest.skip("this run is itself caged")
    if not shutil.which("bwrap"):
        pytest.skip("no bubblewrap")
    from aurora import sys_tests
    probe = f"{sys.executable} -c 'import sys; sys.path[:0] = [\"{ROOT / 'sys/core'}\", \"{ROOT / 'sys/core/tests'}\"]; " \
            "import conftest; print(conftest.in_a_user_namespace())'"
    scratch = Path(tempfile.mkdtemp())
    try:
        r = subprocess.run(sys_tests.live_cage(ROOT, probe, scratch), capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if r.returncode and "bwrap" in r.stderr:
        pytest.skip(f"bubblewrap cannot start here: {r.stderr[:120]}")
    assert r.stdout.strip().endswith("True"), r.stderr[-400:]


def test_every_caged_skip_names_a_test_that_exists():
    tests = Path(__file__).parent
    for key in conftest.CAGED:
        file, _, name = key.partition("::")
        found = list(tests.rglob(Path(file).name))
        if not found and Path(file).name.startswith("test_evd"):
            continue                                   # this installation's own tests: absent from a clone
        assert found, key
        assert not name or f"def {name}(" in found[0].read_text(), key
