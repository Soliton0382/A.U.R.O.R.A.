# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C591 (audit of 12 Nov, the cages): what a plugin Aurora wrote could reach from inside its cage, closed.

B1/B3 a project's .git and .venv, B2 the names env_as may set and bubblewrap by its path, B4 the certificates' account
key, B5 the sealed digest of what a plugin fetched, B6 an MCP server's readable places; and a refused plugin said once."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import agt_forge, plg_contract, plg_deps, plg_host, plg_sandbox, prj_browse, prj_live, sys_config

FORGED = {"name": "zz", "version": "1", "kind": "tool", "description": {"it": "x", "en": "x"},
          "command": ["{python}", "server.py"], "requires": [], "effects": {"*": "read"},
          "forged": {"request": "abc123", "at": "x", "need": "x"},
          "sandbox": {"network": False, "write": ["AURORA_PROJECTS_DIR"]}}
GIT = bool(shutil.which("git"))


def _cage_works() -> bool:
    return bool(shutil.which("bwrap")) and subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                          capture_output=True).returncode == 0


def _wrapped(cfg, tmp_path, manifest, cmd):
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    return plg_sandbox.wrap(list(cmd), plugin, manifest, env, cfg)


def _project(cfg, monkeypatch, name="demo") -> Path:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    proj = cfg.path("AURORA_PROJECTS_DIR") / name
    proj.mkdir(parents=True)
    g = ["git", "-c", "user.name=x", "-c", "user.email=x@example.org", "-C", str(proj)]
    subprocess.run([*g, "init", "-q", "-b", "main"], check=True)
    (proj / "a.txt").write_text("hi\n")
    subprocess.run([*g, "add", "-A"], check=True)
    subprocess.run([*g, "commit", "-qm", "first"], check=True)
    return proj


def _plant(proj: Path, marker: Path) -> None:
    """What the audit's forged plugin wrote: a filter in .git/config, switched on for every file."""
    with open(proj / ".git" / "config", "a") as f:
        f.write(f'[filter "x"]\n\tclean = "touch {marker}; cat"\n')
    (proj / ".gitattributes").write_text("* filter=x\n")
    (proj / "a.txt").write_text("changed\n")


# ---- B1, B3, B4: inside the forged plugin's cage ------------------------------------------------------------------------
@pytest.mark.skipif(not GIT or not _cage_works(), reason="git and a working bubblewrap")
def test_a_forged_cage_writes_no_git_no_venv_and_reads_no_account_key(cfg, tmp_path, monkeypatch):
    proj = _project(cfg, monkeypatch)
    (proj / ".venv" / "bin").mkdir(parents=True)
    status = cfg.path("AURORA_STATUS_DIR")
    for d in ("https/acme", "vpn"):
        (status / d).mkdir(parents=True)
    (status / "https" / "acme" / "account.key").write_text("ACME-KEY")
    (status / "vpn" / "auth.txt").write_text("VPN-PASSWORD")
    probe = ("import sys\n"
             "p, out = sys.argv[1], []\n"
             "for f, mode in ((p+'/.git/config','a'), (p+'/.venv/bin/python','w'), (p+'/b.txt','w'),"
             " (sys.argv[2],'r'), (sys.argv[3],'r')):\n"
             "    try:\n"
             "        open(f, mode).close(); out.append('ok')\n"
             "    except OSError as e:\n"
             "        out.append(type(e).__name__)\n"
             "print(' '.join(out))\n")
    r = subprocess.run(_wrapped(cfg, tmp_path, FORGED, ("/usr/bin/python3", "-c", probe, str(proj),
                                                        str(status / "https/acme/account.key"), str(status / "vpn/auth.txt"))),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    git, venv, own, acme, vpn = r.stdout.split()
    assert git != "ok" and venv != "ok"                 # the repository and the environment: read-only
    assert own == "ok"                                  # the project's files: its to write, as before
    assert acme == "FileNotFoundError" and vpn == "FileNotFoundError"
    assert not (proj / ".venv" / "bin" / "python").exists()


def test_a_repository_a_forged_plugin_leaves_behind_is_set_aside(cfg):
    base = cfg.path("AURORA_PROJECTS_DIR")
    for d in ("old/.git", "old/.venv", "swapped/.git"):
        (base / d).mkdir(parents=True)
    (base / "old" / ".git" / "config").write_text("[core]\n")
    before = plg_sandbox.repo_marks(cfg)
    assert plg_sandbox.set_aside_new(cfg, before) == []                 # nothing new: nothing touched
    (base / "new" / ".git").mkdir(parents=True)                        # a project of its own, with a repository
    (base / "new" / ".venv").mkdir()
    (base / ".git").mkdir()                                             # above every project: git looks upwards
    (base / "swapped").rename(base / "moved")                          # the folder moved away, another in its place
    (base / "swapped" / ".git").mkdir(parents=True)
    said = []
    moved = plg_sandbox.set_aside_new(cfg, before, said.append)
    assert len(moved) == 4 and len(said) == 4 and all(".set-aside-" in m.name for m in moved)
    for gone in ("new/.git", "new/.venv", ".git", "swapped/.git"):
        assert not (base / gone).exists()
    assert (base / "old" / ".git" / "config").exists() and (base / "old" / ".venv").exists()
    assert (base / "moved" / ".git").exists()                          # the one that was there, wherever it is now


def test_the_host_marks_and_sets_aside_around_a_forged_plugin_only(cfg, tmp_path, monkeypatch):
    import asyncio
    calls = []
    monkeypatch.setattr(plg_sandbox, "repo_marks", lambda c: calls.append("marks") or set())
    monkeypatch.setattr(plg_sandbox, "set_aside_new", lambda c, before, log=None: calls.append("aside") or [])
    host = plg_host.PluginHost(cfg)
    monkeypatch.setattr(host, "_params", lambda p: (_ for _ in ()).throw(RuntimeError("not started")))
    for manifest in (FORGED, {k: v for k, v in FORGED.items() if k != "forged"}):
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(host._session(plg_host.Plugin("zz", tmp_path, manifest), None))
    assert calls == ["marks", "aside"]                  # around the forged one, also when it failed; never the owner's


# ---- B1: git on the host ---------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not GIT, reason="git")
@pytest.mark.parametrize("caged", [True, False])
def test_the_host_s_git_runs_nothing_a_project_s_git_names(cfg, tmp_path, monkeypatch, caged):
    if caged and not _cage_works():
        pytest.skip("a working bubblewrap")
    proj = _project(cfg, monkeypatch)
    marker = tmp_path / "OUTSIDE_THE_CAGE"
    _plant(proj, marker)
    if not caged:                                        # a port, a container: no cage starts
        monkeypatch.setattr(prj_browse, "_git_cage", lambda proj, cfg: None)
    s = prj_browse.summary(cfg, proj)                    # what GET /v1/aurora/projects runs in the API's process
    assert not marker.exists()
    assert s["branch"] == "main" and s["last_commit"]["subject"] == "first" and s["changes"] >= 1
    assert [c["msg"] for c in prj_live._commits(proj, cfg)] == ["first"] and not marker.exists()


@pytest.mark.skipif(not GIT, reason="git")
@pytest.mark.parametrize("caged", [True, False])
def test_the_host_s_git_never_reads_a_repository_above_the_project(cfg, tmp_path, monkeypatch, caged):
    if caged and not _cage_works():
        pytest.skip("a working bubblewrap")
    base = _project(cfg, monkeypatch, name="x").parent
    shutil.move(str(base / "x" / ".git"), str(base / ".git"))           # the repository is the projects' folder's now
    if not caged:
        monkeypatch.setattr(prj_browse, "_git_cage", lambda proj, cfg: None)
    assert prj_browse._git(base / "x", "rev-parse", "--abbrev-ref", "HEAD", cfg=cfg) == ""


# ---- B2: env_as, and bubblewrap by its path --------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "HOME", "AURORA_ENV_FILE",
                                  "BASH_ENV", "GIT_SSH_COMMAND", "lower", "A=B", ""])
def test_env_as_never_names_what_the_system_or_aurora_read(cfg, tmp_path, name):
    assert not plg_contract.env_name_ok(name)
    m = {**FORGED, "env_as": {"AURORA_ZZ_WHERE": name},
         "settings_spec": [{"key": "AURORA_ZZ_WHERE", "it": "x", "en": "x"}]}
    assert any(e.startswith("env_as:") for e in plg_contract.check(m))
    assert any(e.startswith("env_as:") and "PATH" in e for e in agt_forge.check({**m, "tests": [{"tool": "t", "args": {}}]}, "", set()))
    with pytest.raises(RuntimeError, match="env_as"):
        plg_host.PluginHost(cfg)._params(plg_host.Plugin("zz", tmp_path, m))


def test_the_host_starts_bubblewrap_by_its_path_and_keeps_its_own_environment(cfg, tmp_path, monkeypatch):
    assert plg_contract.env_name_ok("GITHUB_PERSONAL_ACCESS_TOKEN")     # what the github plugin's program reads
    monkeypatch.setattr(plg_sandbox, "bwrap", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(plg_deps, "verify", lambda *a, **k: None)
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "bwrap").write_text("#!/bin/sh\n")
    (drop / "bwrap").chmod(0o755)
    monkeypatch.setenv("PATH", f"{drop}:{os.environ['PATH']}")          # even a poisoned PATH of the host's own
    m = {**FORGED, "env_as": {"AURORA_ZZ_WHERE": "ZZ_WHERE"}, "env": ["PATH", "AURORA_ENV_FILE", "AURORA_PLUGIN"],
         "forged": None}
    cfg.values["AURORA_ZZ_WHERE"] = "there"
    params = plg_host.PluginHost(cfg)._params(plg_host.Plugin("zz", tmp_path, m))
    assert params.command == "/usr/bin/bwrap" and os.path.isabs(plg_sandbox.wrap(["x"], tmp_path, m, tmp_path / "e", cfg)[0])
    assert params.env["ZZ_WHERE"] == "there" and params.env["AURORA_PLUGIN"] == "zz"
    assert params.env["AURORA_ENV_FILE"] == str(cfg.env_file) and params.env["PATH"].startswith(str(drop))


# ---- B5: what a plugin fetched ----------------------------------------------------------------------------------------------
def _fetched(tmp_path) -> tuple[Path, dict]:
    folder = tmp_path / "plug"
    (folder / ".deps").mkdir(parents=True)
    (folder / ".bin").mkdir()
    (folder / ".deps" / "lib.py").write_text("good")
    (folder / ".bin" / "tool").write_bytes(b"GOOD")
    return folder, {"install": {"python": ["x==1"], "programs": [
        {"name": "tool", "url": "https://example.org/x", "sha256": hashlib.sha256(b"GOOD").hexdigest()}]}}


def test_a_removed_seal_blesses_nothing(cfg, tmp_path):
    folder, m = _fetched(tmp_path)
    plg_deps.record(cfg, folder)
    seal = plg_deps.seal_file(cfg, folder)
    assert seal.is_relative_to(cfg.path("AURORA_STATUS_DIR")) and not seal.is_relative_to(folder)
    plg_deps.verify(cfg, folder, m)
    (folder / ".deps" / "lib.py").write_text("EVIL")
    with pytest.raises(RuntimeError, match="changed since"):
        plg_deps.verify(cfg, folder, m)
    seal.unlink()                                        # the seal removed too: said, never recorded again
    with pytest.raises(RuntimeError, match="no sealed digest"):
        plg_deps.verify(cfg, folder, m)
    assert not seal.exists()


def test_without_deps_a_swapped_program_is_still_seen(cfg, tmp_path):
    folder, m = _fetched(tmp_path)
    plg_deps.record(cfg, folder)
    shutil.rmtree(folder / ".deps")
    (folder / ".bin" / "tool").write_bytes(b"EVIL")
    plg_deps._checked.clear()
    with pytest.raises(RuntimeError, match="not the program its manifest pins"):
        plg_deps.verify(cfg, folder, m)
    (folder / ".bin" / "tool").write_bytes(b"GOOD")      # the program right, the libraries gone: not as installed
    with pytest.raises(RuntimeError, match="changed since"):
        plg_deps.verify(cfg, folder, m)
    shutil.rmtree(folder / ".bin")                       # nothing fetched at all: nothing of it can run
    plg_deps.verify(cfg, folder, m)


def test_a_file_put_back_with_its_old_time_is_hashed_again(cfg, tmp_path):
    folder, m = _fetched(tmp_path)
    plg_deps.record(cfg, folder)
    plg_deps.verify(cfg, folder, m)
    st = (folder / ".deps" / "lib.py").stat()
    (folder / ".deps" / "lib.py").write_text("evil")     # the same size, the same time
    os.utime(folder / ".deps" / "lib.py", ns=(st.st_atime_ns, st.st_mtime_ns))
    with pytest.raises(RuntimeError, match="changed since"):
        plg_deps.verify(cfg, folder, m)


def test_the_seal_of_before_is_taken_over_once_when_it_still_holds(cfg, tmp_path):
    from aurora import sys_seal
    folder, m = _fetched(tmp_path)
    old = folder / ".deps" / plg_deps.TREE               # where C579 kept it
    sys_seal.write(cfg, old, plg_deps.tree_digest(folder).encode(), None, "plugins")
    said = []
    plg_deps.verify(cfg, folder, m, log=said.append)
    assert said and plg_deps.seal_file(cfg, folder).exists() and not old.exists()
    (folder / ".deps" / "lib.py").write_text("EVIL")
    sys_seal.write(cfg, old, b"0" * 64, None, "plugins")
    with pytest.raises(RuntimeError, match="changed since"):
        plg_deps.verify(cfg, folder, m)


# ---- B6: an MCP server's readable places -------------------------------------------------------------------------------------
def test_a_readable_place_is_never_inside_aurora_nor_above_her(cfg, tmp_path_factory):
    root = cfg.root
    for d in ("usr", "sys/https/cert"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for bad in (root / "usr", root / "sys/https/cert", root / "sys", root, root.parent):
        with pytest.raises(ValueError):
            plg_sandbox.read_paths({"name": "local_x", "kind": "mcp", "sandbox": {"read": [str(bad)]}}, cfg)
    outside = tmp_path_factory.mktemp("elsewhere")       # the owner's server, living elsewhere: as before
    assert plg_sandbox.read_paths({"name": "local_x", "kind": "mcp", "sandbox": {"read": [str(outside)]}}, cfg) == [outside.resolve()]


# ---- the projects plugin: its token leaves for GitHub only ---------------------------------------------------------------------
@pytest.mark.skipif(not GIT, reason="git")
def test_the_projects_plugin_sends_its_token_to_github_only(cfg, monkeypatch):
    proj = _project(cfg, monkeypatch)
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    monkeypatch.setenv("AURORA_GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setenv("AURORA_PLUGIN_SECRET_AURORA_GITHUB_TOKEN", "not-a-real-token")
    spec = importlib.util.spec_from_file_location(
        "projects_plugin_server", Path(__file__).resolve().parents[2] / "plugins" / "projects" / "server.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    env = P._git_env()
    assert "not-a-real-token" not in env.values() and env["GIT_CEILING_DIRECTORIES"] == str(P.BASE)
    pushed = []
    monkeypatch.setattr(P, "_git", lambda p, *a, **k: pushed.append(a) or "ok")
    for url in ("https://evil.example/x/y.git", "https://github.com.evil.example/x/y", "http://github.com/x/y",
                "https://user@github.com/x/y", "ssh://github.com/x/y", "https://github.com/x"):
        with pytest.raises(P.ToolError, match="not a GitHub repository"):
            P._push(proj, url)
    subprocess.run(["git", "-C", str(proj), "config", "url.https://evil.example/.insteadOf", "https://github.com/"], check=True)
    with pytest.raises(P.ToolError, match="own git configuration"):
        P._push(proj, "https://github.com/someone/demo.git")
    assert pushed == []
    subprocess.run(["git", "-C", str(proj), "config", "--unset", "url.https://evil.example/.insteadOf"], check=True)
    assert P._push(proj, "https://github.com/someone/demo.git") == "ok" and len(pushed) == 1


# ---- a refused plugin is said once ----------------------------------------------------------------------------------------------
def test_a_plugin_not_loaded_is_said_once_not_at_every_listing(cfg, monkeypatch):
    from aurora import sys_ethics
    folder = cfg.path("AURORA_PLUGINS_DIR")
    for name in ("mine", "other"):
        (folder / name).mkdir(parents=True)
        (folder / name / "plugin.json").write_text(json.dumps({"name": name, "requires": []}))
    unsigned = {"mine", "other"}
    monkeypatch.setattr(sys_ethics, "unsigned_plugins", lambda root, *a: set(unsigned))
    monkeypatch.setattr(plg_host, "_REFUSED", set())
    host, said = plg_host.PluginHost(cfg), []
    host.log = SimpleNamespace(warning=lambda msg, *a: said.append(msg % a), info=lambda *a: None)
    for _ in range(50):
        assert [p.error != "" for p in host.plugins(with_tools=False)] == [True, True]   # still refused each time
    assert sorted(said) == ["plugin mine: not loaded, not signed and not forged",
                            "plugin other: not loaded, not signed and not forged"]
    unsigned.discard("mine")                             # signed: loaded; changed again later: said again
    assert [p.error for p in host.plugins(with_tools=False) if p.name == "mine"] == [""]
    unsigned.add("mine")
    host.plugins(with_tools=False)
    assert said.count("plugin mine: not loaded, not signed and not forged") == 2 and len(said) == 3
