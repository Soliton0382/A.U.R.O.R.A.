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


def _tree():
    """The self plugin's copy, alone: its module starts a server."""
    import os
    import shutil
    tree = ast.parse((ROOT / "sys" / "plugins" / "self" / "server.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_tree")
    ns = {"os": os, "shutil": shutil, "Path": Path}
    exec(compile(ast.Module([fn], []), "server.py", "exec"), ns)
    return ns["_tree"], shutil


def test_a_sandbox_copy_never_sets_a_folders_bits_again_and_keeps_a_dead_link(tmp_path, monkeypatch):
    tree, shutil = _tree()
    src = tmp_path / "src"
    (src / "sub" / "__pycache__").mkdir(parents=True)
    (src / "sub" / "a.py").write_text("x")
    (src / "sub" / "__pycache__" / "a.pyc").write_text("x")
    (src / "dead").symlink_to("../nowhere")
    real = shutil.copystat

    def refused_on_a_folder(a, b, **kw):                  # what RestrictSUIDSGID does to a setgid folder (C504)
        if Path(b).is_dir():
            raise PermissionError(1, "Operation not permitted", str(b))
        return real(a, b, **kw)
    monkeypatch.setattr(shutil, "copystat", refused_on_a_folder)
    tree(src, tmp_path / "box" / "core", shutil.ignore_patterns("__pycache__"))
    assert (tmp_path / "box" / "core" / "sub" / "a.py").read_text() == "x"
    assert not (tmp_path / "box" / "core" / "sub" / "__pycache__").exists()
    assert (tmp_path / "box" / "core" / "dead").is_symlink()


def test_a_problem_that_keeps_coming_is_not_gone_with_a_restart(cfg, monkeypatch):
    from aurora import sys_logread as L
    monkeypatch.setattr(L, "_signed_at", lambda c: "2026-01-02T00:00:00")
    kinds = {"many": {"count": 14, "first": "2026-01-02T12:00:00", "last": "2026-01-02T18:00:00"},
             "few": {"count": 1, "first": "2026-01-02T12:00:00", "last": "2026-01-02T12:00:00"},
             "fixed": {"count": 14, "first": "2026-01-01T12:00:00", "last": "2026-01-01T18:00:00"}}
    monkeypatch.setattr(L, "inventory", lambda c, h: {"components": {"api": {
        "kinds": kinds, "lifecycle": ["2026-01-02T21:00:00 started"]}}})
    got = {e["kind"]: e for e in L.problem_evidence(cfg)}
    assert not got["many"]["seen_after_last_start"] and got["many"]["unfixed"]
    assert not got["few"]["unfixed"] and not got["fixed"]["unfixed"]               # signed after it: the fix had its turn

