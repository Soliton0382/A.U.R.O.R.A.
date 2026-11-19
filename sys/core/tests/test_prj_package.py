# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📦 N148, C675: the package button — commit + aurora.bundle in the project's cage, then the download — and the
user's git in the terminal on a project that already has a repository. Invented projects in tmp_path."""
import os
import shutil
import subprocess

import pytest

from aurora import prj_package, prj_run

pytestmark = pytest.mark.skipif(not (shutil.which("bwrap") and shutil.which("git")), reason="bwrap and git")


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    (p / "src").mkdir(parents=True)
    (p / "src" / "main.py").write_text("print(1)\n")
    r = subprocess.run(prj_run.cage(cfg, p, "true"), capture_output=True, text=True)
    if r.returncode:
        pytest.skip(f"cage not available here: {r.stderr[-120:]}")
    return p


def _clone(bundle, dest):
    subprocess.run(["git", "clone", "-q", "-b", "main", str(bundle), str(dest)], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(dest), "log", "--format=%an <%ae>|%s"], capture_output=True,
                          text=True, check=True).stdout.split("\n")


def test_first_package_makes_the_repository_and_the_bundle(cfg, proj, tmp_path):
    out = prj_package.prepare(cfg, "demo", "anna", "First version", "Anna Rossi", "anna@example.org")
    assert out["committed"] and out["repo"] and out["bundle"]["size"] > 0
    assert out["name"] == "Anna Rossi" and out["dirty"] == 0
    log = _clone(proj / "aurora.bundle", tmp_path / "copy")
    assert log[0] == "Anna Rossi <anna@example.org>|First version"
    files = set(subprocess.run(["git", "-C", str(tmp_path / "copy"), "ls-files"], capture_output=True, text=True)
                .stdout.split())
    assert "src/main.py" in files and "aurora.bundle" not in files and "aurora-git.md" not in files


def test_c675_a_second_package_commits_on_an_existing_repository(cfg, proj, tmp_path):
    prj_package.prepare(cfg, "demo", "anna", "one")
    (proj / "src" / "more.py").write_text("x = 2\n")
    out = prj_package.prepare(cfg, "demo", "anna", "two")
    assert out["committed"], "the cage had .git read only: the commit failed (C675)"
    assert [l.split("|")[1] for l in _clone(proj / "aurora.bundle", tmp_path / "c") if l] == ["two", "one"]
    again = prj_package.prepare(cfg, "demo", "anna", "three")
    assert not again["committed"] and again["bundle"]


def test_default_author_when_none_given(cfg, proj, tmp_path):
    prj_package.prepare(cfg, "demo", "bob", "start")
    assert _clone(proj / "aurora.bundle", tmp_path / "c")[0] == "bob <bob@users.aurora.invalid>|start"


def test_the_terminal_cage_lets_the_user_commit(cfg, proj):
    from aurora import prj_term
    prj_package.prepare(cfg, "demo", "anna", "one", bundle=False)
    (proj / "b.txt").write_text("b\n")
    args = prj_term._cage(cfg, proj)[:-3] + ["bash", "-c", "git add -A && git -c user.name=t -c user.email=t@t "
                                                         "commit -qm term && echo OK"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "OK", r.stderr
    assert not (proj / "aurora.bundle").exists()             # bundle=False: the page's «Salva»


def test_agents_runs_keep_git_read_only(cfg, proj):
    prj_package.prepare(cfg, "demo", "anna", "one")
    r = subprocess.run(prj_run.cage(cfg, proj, "touch .git/planted"), capture_output=True, text=True)
    assert r.returncode != 0 and not (proj / ".git" / "planted").exists()


@pytest.mark.parametrize("msg,author,email", [("", "", ""), ("x" * 501, "", ""), ("ok", "a\nb", ""),
                                              ("ok", "", "no-at"), ("ok", "<a>", "")])
def test_bad_input(cfg, proj, msg, author, email):
    with pytest.raises(ValueError):
        prj_package.prepare(cfg, "demo", "anna", msg, author, email)


def test_the_download_never_follows_a_link(cfg, proj, tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("not the project's")
    (proj / "aurora.bundle").symlink_to(secret)
    with pytest.raises(FileNotFoundError):
        prj_package.open_bundle(cfg, "demo")
    assert prj_package.status(cfg, "demo")["bundle"] is None


def test_the_download_reads_the_bundle(cfg, proj):
    prj_package.prepare(cfg, "demo", "anna", "one")
    fd, size = prj_package.open_bundle(cfg, "demo")
    with os.fdopen(fd, "rb") as f:
        assert f.read(16) == b"# v2 git bundle\n" and size == (proj / "aurora.bundle").stat().st_size
