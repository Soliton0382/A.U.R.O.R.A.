# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The work on a project is interaction too (owner, 21 Oct): its last move, the steps saved and the open items reach
her emotions (kno_mood_work)."""
import subprocess
import time

from aurora import kno_mood_work as W


def _project(base, name, commits, open_items):
    p = base / name
    (p / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    (p / "docs" / "DA_FARE.md").write_text("# Da fare\n" + "- [ ] una cosa\n" * open_items + "- [x] fatta\n")
    for i in range(commits):
        (p / f"f{i}.txt").write_text(str(i))
        subprocess.run(["git", "-C", str(p), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(p), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", f"s{i}"], check=True)
    return p


def test_the_projects_moves_steps_and_open_items_are_read(cfg, monkeypatch):
    W._cache.clear()
    base = cfg.path("AURORA_PROJECTS_DIR")
    _project(base, "motore", 3, 2)
    _project(base, "idea", 0, 1)
    (base / "not-a-project").mkdir()
    r = W.read(cfg)
    assert r["steps_24h"] == 3 and r["open"] == 3 and set(r["by"]) == {"motore", "idea"}
    assert r["last_s"] is not None and r["last_s"] < 120
    assert W.read(cfg, now=time.time() + 10) is r                  # read again only after a few minutes


def test_no_projects_no_signal(cfg):
    W._cache.clear()
    r = W.read(cfg)
    assert r["last_s"] is None and r["steps_24h"] == 0 and r["open"] == 0
