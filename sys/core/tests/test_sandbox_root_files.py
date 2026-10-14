# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C312: two tests read files of the repository's root (the installer, the workflows); a repair sandbox had only
sys/core and sys/plugins, so the suite was never green there and no repair could be proposed. Every root file the
tests read is copied into a sandbox, by the self plugin and by bench_repair alike."""
import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[1]


def _self_root_files() -> tuple:
    tree = ast.parse((ROOT / "sys" / "plugins" / "self" / "server.py").read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ROOT_FILES" for t in n.targets):
            return ast.literal_eval(n.value)
    return ()


def test_every_root_file_the_tests_read_goes_into_a_sandbox():
    copied = set(_self_root_files())
    read = set()
    for f in (CORE / "tests").glob("test_*.py"):
        for name in re.findall(r'["\'](install\.sh|uninstall\.sh|\.github|CHANGELOG\.md|README(?:\.en)?\.md|\.env\.example)["\']',
                               f.read_text(encoding="utf-8")):
            read.add(name)
    assert read and read <= copied, f"read by the tests, not copied into a sandbox: {read - copied}"
    bench = (CORE / "script" / "bench_repair.py").read_text()
    assert all(f'"{n}"' in bench for n in copied)
