# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import subprocess

from aurora import sys_ethics, sys_update


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def setup(tmp_path):
    """origin (bare) <- here (the installation) and there (where the update is written)."""
    origin, here, there = tmp_path / "origin.git", tmp_path / "here", tmp_path / "there"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(there)], check=True, capture_output=True)
    for c in (there,):
        git(c, "config", "user.email", "t@t"); git(c, "config", "user.name", "t")
    (there / "a.txt").write_text("1\n")
    git(there, "add", "."); git(there, "commit", "-qm", "first"); git(there, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(here)], check=True, capture_output=True)
    return here, there


def commit(repo, path, text, msg):
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    git(repo, "add", "."); git(repo, "commit", "-qm", msg); git(repo, "push", "-q", "origin", "main")


def test_a_safe_update_is_listed_and_applied(cfg, tmp_path):
    here, there = setup(tmp_path)
    commit(there, "a.txt", "2\n", "Nuova funzione: sogni a colori")
    info = sys_update.check(cfg, here)
    assert info["behind"] == 1 and info["safe"] and info["commits"][0]["subject"] == "Nuova funzione: sogni a colori"
    assert "sogni a colori" in sys_update.changelog(info)
    out = sys_update.apply(cfg, root=here, run_tests=lambda: {"ok": True, "passed": 3})
    assert out["applied"] and (here / "a.txt").read_text() == "2\n"


def test_failing_tests_roll_the_update_back(cfg, tmp_path):
    here, there = setup(tmp_path)
    before = git(here, "rev-parse", "HEAD").strip()
    commit(there, "a.txt", "broken\n", "Rompe tutto")
    out = sys_update.apply(cfg, root=here, run_tests=lambda: {"ok": False, "summary": "1 failed"})
    assert not out["applied"] and out["rolled_back"]
    assert git(here, "rev-parse", "HEAD").strip() == before and (here / "a.txt").read_text() == "1\n"


def test_protected_files_and_local_work_are_never_updated_here(cfg, tmp_path):
    here, there = setup(tmp_path)
    commit(there, sys_ethics.PROTECTED[0], "new rules\n", "Cambia le regole")
    info = sys_update.check(cfg, here)
    assert info["protected"] == [sys_ethics.PROTECTED[0]] and not info["safe"]
    assert "protected" in sys_update.apply(cfg, root=here, run_tests=lambda: {"ok": True})["reason"]
    here2, there2 = setup(tmp_path / "b")
    commit(there2, "a.txt", "2\n", "ok")
    (here2 / "a.txt").write_text("my local change\n")
    assert "local changes" in sys_update.apply(cfg, root=here2, run_tests=lambda: {"ok": True})["reason"]
