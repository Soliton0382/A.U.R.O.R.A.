# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔌 C674: Aurora runs no git on an existing project. The projects plugin has no status/commit/publish/push tool and
no token, reads a project's files without git, and every project gets the guide to commit and publish by hand
(prj_gitguide). Invented projects in tmp_path."""
import asyncio
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from aurora import prj_gitguide, prj_run

ROOT = Path(__file__).resolve().parents[3]
GIT_TOOLS = {"project_status", "project_commit", "project_publish", "project_push"}


def _load(cfg, monkeypatch, name):
    pytest.importorskip("mcp")
    spec = importlib.util.spec_from_file_location(name, ROOT / "sys/plugins/projects/server.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setattr("aurora.sys_config.get", lambda *a, **k: cfg)
    spec.loader.exec_module(mod)
    mod.BASE = cfg.path("AURORA_PROJECTS_DIR")
    return mod


def test_no_switch_and_no_token_in_the_plugin():
    schema = json.loads((ROOT / "sys/core/config/settings_schema.json").read_text())
    rows = schema if isinstance(schema, list) else schema.get("settings", [])
    assert not any(isinstance(r, dict) and r.get("key") == "AURORA_PROJECTS_GIT" for r in rows)
    manifest = json.loads((ROOT / "sys/plugins/projects/plugin.json").read_text())
    assert "AURORA_GITHUB_TOKEN" not in manifest.get("env", []) and not GIT_TOOLS & set(manifest["effects"])
    src = (ROOT / "sys/plugins/projects/server.py").read_text()
    assert "TOKEN" not in src and "def _push" not in src


def test_git_tools_not_offered(cfg, monkeypatch):
    mod = _load(cfg, monkeypatch, "projects_server_nogit")
    offered = {t.name for t in asyncio.run(mod.server.list_tools())}
    assert not GIT_TOOLS & offered and not any(hasattr(mod, f) for f in GIT_TOOLS)
    assert {"project_list", "project_tree", "project_create", "project_write_file"} <= offered


def test_tree_and_list_without_git(cfg, monkeypatch, tmp_path):
    mod = _load(cfg, monkeypatch, "projects_server_tree")
    p = mod.BASE / "demo"
    (p / ".git").mkdir(parents=True)
    (p / ".git" / "config").write_text("[core]\n\tfsmonitor = touch " + str(tmp_path / "RAN") + "\n")
    (p / "src").mkdir()
    (p / "src" / "a.py").write_text("x = 1\n")
    (p / "link").symlink_to(tmp_path)
    assert mod.project_tree("demo").split("\n") == ["link", "src/a.py"]
    assert mod.project_list() == "demo"
    assert not (tmp_path / "RAN").exists()                    # git never ran on the planted .git


def test_guide_written_once_and_kept_out_of_commits(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    (p / ".gitignore").write_text("*.pyc")                    # no final newline
    assert prj_gitguide.ensure(p) is True
    assert prj_gitguide.ensure(p) is False
    assert (p / ".gitignore").read_text().split("\n")[:3] == ["*.pyc", prj_gitguide.NAME, prj_gitguide.BUNDLE]
    text = (p / prj_gitguide.NAME).read_text()
    assert "git bundle create aurora.bundle main" in text and "Pubblica" in text and "English" in text


def test_guide_never_through_a_link(tmp_path):
    p, outside = tmp_path / "proj", tmp_path / "outside.md"
    p.mkdir()
    (p / prj_gitguide.NAME).symlink_to(outside)
    with pytest.raises((OSError, ValueError)):
        prj_gitguide.ensure(p)
    assert not outside.exists()


@pytest.mark.skipif(not (shutil.which("bwrap") and shutil.which("git")), reason="bwrap and git")
def test_guide_steps_work_in_the_terminals_cage(cfg, tmp_path):
    """The guide's steps, run as the terminal runs them (.git writable, C675): commit and bundle, then clone."""
    p = tmp_path / "proj"
    p.mkdir()
    (p / "main.py").write_text("print(1)\n")
    prj_gitguide.ensure(p)
    subprocess.run(["git", "init", "-q", "-b", "main", str(p)], check=True)   # a repository that already exists
    cmd = ("git config user.name T && git config user.email t@example.org && git add -A && "
           "git commit -qm first && git bundle create aurora.bundle main && git ls-files")
    r = subprocess.run(prj_run.cage(cfg, p, "x", git_writable=True)[:-1] + [cmd], capture_output=True, text=True,
                       timeout=120)
    if r.returncode and "bwrap" in r.stderr:
        pytest.skip(f"cage not available here: {r.stderr[-120:]}")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [".gitignore", "main.py"]
    subprocess.run(["git", "clone", "-q", "-b", "main", str(p / "aurora.bundle"), str(tmp_path / "copy")], check=True)
    assert (tmp_path / "copy" / "main.py").read_text() == "print(1)\n"
