# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ The fifth independent review of the projects' git (20 Nov 2026): every attack it reproduced, kept as a test
(C670–C673). Each plants what a caged command could leave and asserts that nothing ran on the host (a marker file the
planted command would have made). Invented projects in tmp_path; the caged ones need bwrap."""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import plg_sandbox, prj_browse, prj_gitsafe, prj_run

ROOT = Path(__file__).resolve().parents[3]
needs_bwrap = pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git")


def _env(p: Path) -> dict:
    return prj_gitsafe.env(p.parent, {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                                      "GIT_COMMITTER_EMAIL": "t@t"})


def _g(p: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(p), *a], env=_env(p), check=True, capture_output=True)


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    p.mkdir(parents=True)
    (p / "a.txt").write_text("hi\n")
    return p


@pytest.fixture
def srv(cfg, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.delenv("AURORA_GITHUB_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location("projects_server_t5", ROOT / "sys/plugins/projects/server.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setattr("aurora.sys_config.get", lambda *a, **k: cfg)
    spec.loader.exec_module(mod)
    mod.BASE = cfg.path("AURORA_PROJECTS_DIR")
    return mod


def _filter(p: Path, gitdir_cfg: Path, marker: Path) -> None:
    """A filter whose clean command leaves `marker`, asked for every file by .gitattributes."""
    subprocess.run(["git", "config", "--file", str(gitdir_cfg), "filter.x.clean", f"touch {marker}; cat"], check=True)
    (p / ".gitattributes").write_text("* filter=x\n")


def _all_refuse(srv, p: Path, marker: Path) -> None:
    from mcp.server.mcpserver.exceptions import ToolError
    for a in (("add", "-A"), ("status", "--porcelain"), ("commit", "-m", "x")):
        with pytest.raises((ToolError, ValueError)):
            srv._git(p, *a)
    with pytest.raises(ValueError):
        prj_gitsafe.run(p, "status")
    prj_browse.git_read(p, "status", "--porcelain")      # caged, or refused where no cage starts
    assert not marker.exists()


# ---- C670: the five ways around C658's list -----------------------------------------------------------------------
def test_c670_a_bare_repository_at_the_project_root_is_never_used(srv, proj, tmp_path):
    marker = tmp_path / "HOST_RAN_BARE"
    _g(proj, "init", "-q", "--bare", ".")
    _g(proj, "config", "core.bare", "false")
    _g(proj, "config", "core.worktree", str(proj))
    _filter(proj, proj / "config", marker)
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError):                       # GIT_DIR named: <project>/.git does not exist
        srv._git(proj, "add", "-A")
    prj_browse.git_read(proj, "status", "--porcelain")
    assert not marker.exists()


def test_c670_config_worktree_is_refused(srv, proj, tmp_path):
    marker = tmp_path / "HOST_RAN_WT"
    _g(proj, "init", "-q")
    _g(proj, "config", "extensions.worktreeConfig", "true")
    _filter(proj, proj / ".git" / "config.worktree", marker)
    assert "config.worktree" in prj_gitsafe.refusal(proj)
    _all_refuse(srv, proj, marker)


def test_c670_commondir_is_refused(srv, proj, tmp_path):
    marker = tmp_path / "HOST_RAN_COMMON"
    other = proj / "elsewhere"
    _g(proj.parent, "init", "-q", "--bare", str(other))
    _filter(proj, other / "config", marker)
    _g(proj, "init", "-q")
    (proj / ".git" / "config").unlink()
    (proj / ".git" / "commondir").write_text(str(other) + "\n")
    assert "commondir" in prj_gitsafe.refusal(proj)
    _all_refuse(srv, proj, marker)


def test_c670_a_signing_command_no_list_named_is_refused(srv, proj, tmp_path):
    marker = tmp_path / "HOST_RAN_SIGN"
    _g(proj, "init", "-q")
    for k, v in (("commit.gpgsign", "true"), ("gpg.format", "ssh"), ("gpg.ssh.defaultKeyCommand", f"touch {marker}")):
        _g(proj, "config", k, v)
    assert "gpg.ssh.defaultkeycommand" in prj_gitsafe.refusal(proj)
    _all_refuse(srv, proj, marker)


def test_c670_a_nested_repository_with_a_filter_is_refused(srv, proj, tmp_path):
    marker = tmp_path / "HOST_RAN_NESTED"
    _g(proj, "init", "-q")
    sub = proj / "sub"
    sub.mkdir()
    _g(sub, "init", "-q")
    _filter(sub, sub / ".git" / "config", marker)
    (sub / "f.txt").write_text("x")
    assert prj_gitsafe.refusal(proj) == "" and "nested" in prj_gitsafe.refusal(proj, deep=True)
    from mcp.server.mcpserver.exceptions import ToolError
    for a in (("add", "-A"), ("status", "--porcelain"), ("commit", "-m", "x")):
        with pytest.raises(ToolError, match="nested"):
            srv._git(proj, *a)
    assert not marker.exists()


def test_c670_git_lfs_is_refused_with_a_clear_word(srv, proj):
    _g(proj, "init", "-q")
    (proj / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="Git LFS"):
        srv._git(proj, "add", "-A")


def test_c670_a_repository_made_by_git_init_and_remote_add_is_accepted(proj):
    _g(proj, "init", "-q", "-b", "main")
    _g(proj, "remote", "add", "origin", "https://github.com/someone/demo.git")
    _g(proj, "config", "branch.main.remote", "origin")
    _g(proj, "config", "branch.main.merge", "refs/heads/main")
    _g(proj, "config", "user.name", "Someone")
    assert prj_gitsafe.refusal(proj, deep=True) == ""


# ---- C671: the clone's token, never on a command line ---------------------------------------------------------------
def test_c671_the_clone_puts_the_token_in_the_environment_only(tmp_path):
    clone_command = prj_gitsafe.clone_command
    import base64
    cmd, env = clone_command("someone/demo", tmp_path / "demo", "tok-123")
    enc = base64.b64encode(b"x-access-token:tok-123").decode()
    assert not any("tok-123" in a or enc in a for a in cmd)
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader" and enc in env["GIT_CONFIG_VALUE_0"]
    assert "--no-recurse-submodules" in cmd and "protocol.allow=never" in cmd and "AURORA_GITHUB_TOKEN" not in env


# ---- C672: a plugin's secrets in no environment inside its cage -----------------------------------------------------
@needs_bwrap
def test_c672_the_cage_holds_the_secret_in_no_environment(cfg, tmp_path):
    """The real launch path: plg_sandbox.wrap, then plg_launch replacing itself with bubblewrap. Inside, neither
    bubblewrap (/proc/1/environ) nor the plugin (/proc/self/environ) holds the value; the plugin reads it once from
    the file, which is then empty."""
    folder = tmp_path / "plug"
    folder.mkdir()
    probe = folder / "probe.py"
    probe.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'sys/core')!r})\n"
        "from aurora import sys_config\n"
        "envs = [open(f'/proc/{p}/environ', 'rb').read() for p in ('1', 'self')]\n"
        "path = os.environ.get('AURORA_PLUGIN_SECRETS_FILE')\n"
        "got = sys_config.plugin_secret('AURORA_GITHUB_TOKEN')\n"
        "left = open(path).read() if path else 'nofile'\n"
        "print('ENV', any(b'secret-in-cage' in e for e in envs), 'GOT', got, 'LEFT', repr(left))\n")
    filtered = tmp_path / "filtered.env"
    filtered.write_text("AURORA_GITHUB_TOKEN=aurenv:AURORA_GITHUB_TOKEN\n")
    m = {"name": "zz", "sandbox": {}}
    cmd = plg_sandbox.wrap([sys.executable, str(probe)], folder, m, filtered, cfg)
    i = len(cmd) - 1 - cmd[::-1].index("--chdir")         # the tests' Aurora lives in tmp: the real code shown again
    cmd = cmd[:i] + ["--ro-bind", str(ROOT), str(ROOT)] + cmd[i:]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "AURORA_PLUGIN": "zz",
           "AURORA_PLUGIN_SECRET_AURORA_GITHUB_TOKEN": "secret-in-cage"}
    out = subprocess.run([sys.executable, "-I", str(ROOT / "sys/core/aurora/plg_launch.py"), "--at", str(len(cmd) - 3),
                          *cmd], env=env,
                         capture_output=True, text=True, timeout=60)
    assert "ENV False GOT secret-in-cage LEFT ''" in out.stdout, out.stderr[-1500:]


def test_c672_the_host_never_names_a_secret_in_the_plugins_environment(cfg, tmp_path, monkeypatch):
    from aurora import plg_deps, plg_host
    monkeypatch.setattr(plg_deps, "verify", lambda *a, **k: None)
    monkeypatch.setattr(plg_sandbox, "bwrap", lambda: "/usr/bin/bwrap")
    cfg.values["AURORA_GITHUB_TOKEN"] = "tok-xyz"
    cfg.raw["AURORA_GITHUB_TOKEN"] = "tok-xyz"
    m = {"name": "projects", "command": ["{python}", "server.py"], "env": ["AURORA_GITHUB_TOKEN"],
         "sandbox": {"network": True, "write": ["AURORA_PROJECTS_DIR"]}}
    params = plg_host.PluginHost(cfg)._params(plg_host.Plugin("projects", tmp_path, m))
    assert "AURORA_GITHUB_TOKEN" not in params.env                     # never by its own name
    assert params.args[1].endswith("plg_launch.py")                    # the launcher takes the prefixed one out
    assert not any("tok-xyz" in a for a in params.args)                # nor on a command line


# ---- C673: a command that takes the write permission off the project ------------------------------------------------
@needs_bwrap
def test_c673_chmod_555_does_not_keep_a_planted_git(cfg, proj, tmp_path):
    out = prj_run.run(cfg, "demo", "mkdir .git && chmod 555 .")
    assert not (proj / ".git").exists() and any(x.name.startswith(".git.set-aside-") for x in proj.iterdir())
    assert out["exit"] == 0
