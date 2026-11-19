# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Projects page's order (owner, 17 Nov 2026: «per nome, per data di creazione o di ultima modifica»): each project
says when it was created (its first commit) and last modified (its last commit, or a file changed since)."""
import os
import subprocess
import time

from aurora import prj_browse


def _git(p, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(p), *a], check=True, capture_output=True)


def test_created_and_modified(cfg):
    p = prj_browse.base(cfg) / "demo"
    p.mkdir(parents=True)
    (p / "a.txt").write_text("one")
    _git(p, "init", "-q", "-b", "main")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "first")
    s = prj_browse.summary(cfg, p)
    assert s["created"] and s["modified"] == s["last_commit"]["date"]
    (p / "a.txt").write_text("changed, not committed")
    later = time.time() + 3600
    os.utime(p / "a.txt", (later, later))
    s2 = prj_browse.summary(cfg, p)
    assert s2["modified"] > s["modified"] and s2["created"] == s["created"]
