# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ The fourth independent review of the projects' cages (20 Nov 2026): every attack it reproduced, kept as a test
(C658–C669). Invented projects in tmp_path; the caged ones need bwrap."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import prj_browse, prj_gitsafe, prj_run

ROOT = Path(__file__).resolve().parents[3]
needs_bwrap = pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")


@pytest.fixture
def bare(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "nogit"
    p.mkdir(parents=True)
    (p / "a.txt").write_text("hi\n")
    return p


def _plant(p: Path, marker: Path) -> None:
    """What a caged command could leave: a .git whose configuration names programs."""
    env = prj_gitsafe.env(p.parent)
    subprocess.run(["git", "init", "-q", str(p)], env=env, check=True)
    for k, v in (("core.fsmonitor", f"touch {marker}; false"), ("filter.x.clean", f"touch {marker}.filter; cat")):
        subprocess.run(["git", "-C", str(p), "config", k, v], env=env, check=True)
    (p / ".gitattributes").write_text("* filter=x\n")


# ---- C658: a .git planted by a caged command ---------------------------------------------------------------------
@needs_bwrap
def test_c658_a_git_made_by_a_caged_command_is_set_aside(cfg, bare, tmp_path):
    marker = tmp_path / "HOST_RAN"
    cmd = (f"git init -q . && git config core.fsmonitor 'touch {marker}; false' && "
           f"git config filter.x.clean 'touch {marker}.filter; cat' && echo '* filter=x' > .gitattributes && echo planted")
    out = prj_run.run(cfg, "nogit", cmd)
    assert "planted" in out["output"] and "set aside" in out["output"]
    assert not (bare / ".git").exists() and list(bare.glob(".git.set-aside-*"))
    # the host's readers find no repository and run nothing
    assert prj_browse.git_read(bare, "status", "--short", cfg=cfg) == ""
    assert not marker.exists() and not Path(f"{marker}.filter").exists()


@needs_bwrap
def test_c658_with_a_cage_the_readers_read_a_planted_config_and_run_nothing_on_the_host(cfg, bare, tmp_path):
    marker = tmp_path / "HOST_RAN"
    _plant(bare, marker)
    prj_browse.git_read(bare, "status", "--short", cfg=cfg)        # caged (C591): whatever it names stays inside
    from aurora import prj_conduct, prj_referee
    prj_conduct.folder_facts(cfg, "nogit", "")
    prj_referee._git(bare, "status", "--short")
    assert not marker.exists() and not Path(f"{marker}.filter").exists()


@needs_bwrap
def test_c658_a_git_that_was_there_stays(cfg, bare):
    subprocess.run(["git", "init", "-q", str(bare)], env=prj_gitsafe.env(bare.parent), check=True)
    ino = os.lstat(bare / ".git").st_ino
    out = prj_run.run(cfg, "nogit", "echo ok")
    assert "set aside" not in out["output"] and os.lstat(bare / ".git").st_ino == ino


def test_c658_every_host_side_git_refuses_a_config_that_names_a_program(cfg, bare, tmp_path):
    marker = tmp_path / "HOST_RAN"
    _plant(bare, marker)
    assert "core.fsmonitor" in prj_gitsafe.refusal(bare) and "filter.x.clean" in prj_gitsafe.refusal(bare)
    with pytest.raises(ValueError):
        prj_gitsafe.run(bare, "status", "--short")
    from aurora import prj_browse as B                     # where no cage starts (a port, a container): refused
    monkeypatch_cage = B._git_cage
    try:
        B._git_cage = lambda *a, **k: None
        B.git_read(bare, "status", "--short", cfg=cfg)       # read with fsmonitor and the filters switched off
        from aurora import prj_conduct, prj_referee
        prj_conduct.folder_facts(cfg, "nogit", "")
        prj_referee._git(bare, "status", "--short")
        env = prj_gitsafe.env(bare.parent)
        subprocess.run(["git", "-C", str(bare), "config", "core.worktree", "/"], env=env, check=True)
        assert B.git_read(bare, "status", "--short", cfg=cfg) == ""     # a work tree elsewhere: not read
    finally:
        B._git_cage = monkeypatch_cage
    assert not marker.exists() and not Path(f"{marker}.filter").exists()


def test_c658_a_git_file_or_link_is_refused(bare, tmp_path):
    (bare / ".git").write_text(f"gitdir: {tmp_path}\n")
    assert "not a folder" in prj_gitsafe.refusal(bare)
    (bare / ".git").unlink()
    (bare / ".git").symlink_to(tmp_path)
    assert "link" in prj_gitsafe.refusal(bare)


def test_c658_a_plain_repository_is_read(bare):
    env = prj_gitsafe.env(bare.parent, {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                                        "GIT_COMMITTER_EMAIL": "t@x"})
    subprocess.run(["git", "init", "-q", "-b", "main", str(bare)], env=env, check=True)
    subprocess.run(["git", "-C", str(bare), "add", "-A"], env=env, check=True)
    subprocess.run(["git", "-C", str(bare), "commit", "-qm", "first"], env=env, check=True)
    assert prj_gitsafe.refusal(bare) == ""
    assert "first" in prj_gitsafe.run(bare, "log", "-1", "--format=%s").stdout


def test_c658_git_env_drops_the_token_and_the_inherited_git_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("AURORA_GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.fsmonitor=evil'")
    e = prj_gitsafe.env(tmp_path)
    assert "AURORA_GITHUB_TOKEN" not in e and "GIT_CONFIG_PARAMETERS" not in e
    assert e["GIT_CONFIG_NOSYSTEM"] == "1" and e["GIT_CONFIG_GLOBAL"] == os.devnull


def _load_plugin(monkeypatch, cfg, env: dict):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("projects_server_t4", ROOT / "sys/plugins/projects/server.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setattr("aurora.sys_config.get", lambda *a, **k: cfg)
    spec.loader.exec_module(mod)
    return mod


def test_c658_the_plugin_refuses_git_on_a_planted_config(cfg, bare, tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    marker = tmp_path / "HOST_RAN"
    _plant(bare, marker)
    srv = _load_plugin(monkeypatch, cfg, {})
    srv.BASE = bare.parent
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="C670"):            # C670 took C658's place: an allow-list
        srv._git(bare, "add", "-A")
    assert srv.project_list() == bare.name                  # C674: the list reads no git at all
    assert not marker.exists() and not Path(f"{marker}.filter").exists()


# ---- C659: the token in no environment the kernel keeps, never on a command line -------------------------------
# ---- C660: no discovery while a long run of the project is going or not yet registered ---------------------------
def _linear(p: Path) -> str:
    (p / "dati").mkdir(exist_ok=True)
    rows = "".join(f"{x},{2.5 * x + 1:.6f}\n" for x in range(1, 301))
    (p / "dati" / "lin.csv").write_text("x,y\n" + rows, encoding="utf-8")
    return "dati/lin.csv"


def test_c660_discovery_waits_for_a_long_run_and_flags_tables_of_an_unfinished_one(cfg, bare, monkeypatch):
    import time
    from aurora import prj_discover as D
    from aurora import prj_longrun as R
    cfg.values["AURORA_DISCOVER_ENABLED"] = True
    data = _linear(bare)
    R._save(cfg, "nogit", {"id": "001", "status": "running", "limits": {}, "t": time.time() - 60})
    out = D.discover(cfg, "nogit", data, "y", runner=lambda *a, **k: {})
    assert out["status"] == "refused" and "long run" in out["errors"][0]
    R._update(cfg, "nogit", "001", status="ended")                 # ended, outputs not hashed yet
    assert R.unfinished_since(cfg, "nogit") is not None
    os.utime(bare / data, (0, 0))                                  # its date set back: the ctime is not
    out = D.discover(cfg, "nogit", data, "y")
    # O1 of C709: a run not finished counts as going — refused; before, a caveat
    assert out["status"] != "discovered" and any("long run" in c for c in out.get("caveats", []) + out.get("errors", []))


# ---- C661: a folder or a file that cannot be looked at makes the snapshot «capped» -------------------------------
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_c661_an_unreadable_folder_caps_the_snapshot(bare, mode):
    h = bare / "h"
    h.mkdir()
    (h / "t.csv").write_text("x,y\n1,2\n")
    try:
        h.chmod(mode)
        snap, capped = prj_run.snapshot_full(bare)
    finally:
        h.chmod(0o755)
    assert capped and "h/t.csv" not in snap


# ---- C662: the disk a run takes, its r-- folders and its deleted open files counted ------------------------------
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_c662_a_folder_listed_but_not_looked_at_stops_the_measure(bare):
    from aurora import prj_longrun_cage as C
    h = bare / "h"
    h.mkdir()
    (h / "big").write_bytes(b"x" * 100_000)
    try:
        h.chmod(0o444)
        with pytest.raises(C.Unmeasurable):
            C.disk_bytes(bare)
    finally:
        h.chmod(0o755)


def test_c662_a_deleted_file_still_open_is_counted(tmp_path):
    from aurora import prj_longrun_cage as C
    f = tmp_path / "gone"
    with open(f, "wb") as fh:
        fh.write(b"y" * 2_000_000)
        fh.flush()
        f.unlink()
        assert C.deleted_open_bytes([os.getpid()]) >= 2_000_000


# ---- C663: an absolute path is the project's only inside its folder ---------------------------------------------
def test_c663_absolute_paths(tmp_path):
    from aurora import prj_safeio as S
    root = tmp_path / "p"
    root.mkdir()
    assert S.norm(str(root / "a" / "b.txt"), root) == "a/b.txt" and S.norm(str(root), root) == "."
    for bad in ("/etc/x", str(tmp_path / "pp" / "a"), str(root) + "x/a"):
        with pytest.raises(ValueError):
            S.norm(bad, root)
    with pytest.raises(ValueError):
        S.norm("/etc/x")                                           # no root given: never made relative
    S.write_text(root, str(root / "w.txt"), "ok")
    assert (root / "w.txt").read_text() == "ok" and not (root / "etc").exists()
    with pytest.raises(ValueError):
        S.write_text(root, "/etc/x", "no")


# ---- C664: project_install really installs with --target --------------------------------------------------------
def _wheel(d: Path, name: str, version: str, files: dict, script: str = "") -> Path:
    import base64
    import hashlib
    import zipfile
    info = f"{name}-{version}.dist-info"
    entries = dict(files)
    entries[f"{info}/METADATA"] = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    entries[f"{info}/WHEEL"] = "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    if script:
        entries[f"{info}/entry_points.txt"] = f"[console_scripts]\n{script} = {name}:main\n"
    rec = []
    for k, v in entries.items():
        dig = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
        rec.append(f"{k},sha256={dig},{len(v.encode())}")
    rec.append(f"{info}/RECORD,,")
    entries[f"{info}/RECORD"] = "\n".join(rec) + "\n"
    w = d / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(w, "w") as z:
        for k, v in entries.items():
            z.writestr(k, v)
    return w


def test_c664_install_upgrade_namespace_and_scripts(cfg, monkeypatch, tmp_path):
    pytest.importorskip("mcp")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    _wheel(wheels, "aurtinya", "1.0", {"aurtinya/__init__.py": "def main():\n    print('A1')\n",
                                        "aurnsx/one.py": "X = 1\n"}, script="aurtinya-hi")
    _wheel(wheels, "aurtinya", "2.0", {"aurtinya/__init__.py": "def main():\n    print('A2')\n",
                                        "aurnsx/one.py": "X = 2\n"}, script="aurtinya-hi")
    _wheel(wheels, "aurtinyb", "1.0", {"aurtinyb/__init__.py": "", "aurnsx/two.py": "Y = 1\n"})
    monkeypatch.setenv("PIP_NO_INDEX", "1")
    monkeypatch.setenv("PIP_FIND_LINKS", str(wheels))
    srv = _load_plugin(monkeypatch, cfg, {})
    srv.BASE = cfg.path("AURORA_PROJECTS_DIR")
    proj = srv.BASE / "inst"
    proj.mkdir(parents=True)
    srv.project_install("inst", ["aurtinya==1.0", "aurtinyb==1.0"])
    site = next((proj / ".venv").glob("lib/python*/site-packages"))
    py = proj / ".venv" / "bin" / "python"
    run = lambda code: subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=60).stdout.strip()  # noqa: E731
    assert run("import aurnsx.one, aurnsx.two; print(aurnsx.one.X, aurnsx.two.Y)") == "1 1"
    script = proj / ".venv" / "bin" / "aurtinya-hi"
    assert script.exists() and script.read_text().startswith(f"#!{py}")
    assert subprocess.run([str(script)], capture_output=True, text=True, timeout=60).stdout.strip() == "A1"
    srv.project_install("inst", ["aurtinya==2.0"])
    infos = sorted(p.name for p in site.glob("aurtinya-*.dist-info"))
    assert infos == ["aurtinya-2.0.dist-info"]                      # the old one gone, not two
    assert run("import aurnsx.one, aurnsx.two; print(aurnsx.one.X, aurnsx.two.Y)") == "2 1"   # namespace kept
    req = (proj / "requirements-aurora.txt").read_text()
    assert "aurtinya==2.0" in req and "aurtinya==1.0" not in req and "aurtinyb==1.0" in req


# ---- C665: the engines' own reads never block on a pipe nor follow a link ---------------------------------------
def test_c665_freeze_refuses_a_pipe_in_place_of_a_code_file(cfg, bare):
    import threading
    from aurora import prj_prereg as P
    os.mkfifo(bare / "sim.py")
    res = {}

    def go():
        try:
            P.freeze(cfg, "nogit", "t", [{"id": "P1", "text": "x"}], ["sim.py"])
            res["r"] = "frozen"
        except ValueError as e:
            res["r"] = str(e)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive() and "no such file" in res["r"]


def test_c665_freeze_writes_through_no_link(cfg, bare, tmp_path):
    from aurora import prj_prereg as P
    outside = tmp_path / "outside"
    outside.mkdir()
    (bare / "prereg").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        P.freeze(cfg, "nogit", "t", [{"id": "P1", "text": "x"}], [])
    assert not any(outside.iterdir())


# ---- C666: reserved titles and target names however they are written --------------------------------------------
@pytest.mark.parametrize("title", ["Lօng run 9", "Long-run 3", "Discovered_law", "Disсovered law", "LONGRUN 4"])
def test_c666_reserved_titles(title):
    from aurora import prj_prereg as P
    assert P.reserved(title)


@pytest.mark.parametrize("title", ["μ_n bound", "Previsioni su ε_n", "Long story", "Discovery of a bug"])
def test_c666_ordinary_titles_stay_free(title):
    from aurora import prj_prereg as P
    assert not P.reserved(title)


def test_c666_lookalike_targets_are_one():
    from aurora import prj_discover as D
    assert D.target_key("у") == D.target_key("y_") == D.target_key("Y") == "y"


# ---- C667: off means off ----------------------------------------------------------------------------------------
def test_c667_switched_off_the_tools_refuse_and_the_runs_stop(cfg, bare):
    import time
    from aurora import prj_longrun as R
    from aurora import prj_novelty as N
    from aurora import prj_discover as D
    cfg.values["AURORA_LONGRUN_ENABLED"] = True
    R._save(cfg, "nogit", {"id": "001", "status": "running", "limits": {"wall_s": 10}, "t": time.time(),
                           "attempts": 1, "used_s": 0, "outputs": [], "command": "x"})
    cfg.values["AURORA_LONGRUN_ENABLED"] = False
    assert R.busy(cfg, "nogit")                                    # the tools still wait for it
    assert R.act(cfg, "nogit", {"action": "list"}).startswith("REFUSED")
    R.sweep(cfg, "nogit")
    assert R.load(cfg, "nogit", "001")["status"] == "stopped"
    agent = type("A", (), {"cfg": cfg, "projects": set()})()
    for k in ("AURORA_NOVELTY_ENABLED", "AURORA_DISCOVER_ENABLED"):
        cfg.values[k] = False
    assert N.agent_call(agent, {"project": "nogit", "claim": "c"}).startswith("REFUSED")
    assert D.agent_call(agent, {"project": "nogit", "data": "a.csv", "target": "y"}).startswith("REFUSED")


# ---- C668: the Lean installer with a relative folder -------------------------------------------------------------
def test_c668_a_relative_lean_folder_is_made_absolute(tmp_path):
    r = subprocess.run(["bash", str(ROOT / "sys/core/script/sys_proofs_install.sh"), "--dry-run", "rel/lean"],
                       capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert r.returncode == 0 and str(tmp_path / "rel" / "lean" / "elan") in r.stdout and not (tmp_path / "rel").exists()


# ---- C669: an old recommended value moved once only ---------------------------------------------------------------
def test_c669_the_owner_s_choice_is_not_reset_at_every_update(tmp_path):
    from aurora import sys_config
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"settings": [{"key": "AURORA_X_ENABLED", "recommended": "false",
                                                "old_recommended": ["true"], "type": "bool"}]}))
    env = tmp_path / ".env"
    env.write_text("AURORA_X_ENABLED=true\n")
    assert sys_config.add_missing(env, schema) == ["AURORA_X_ENABLED"]
    assert "AURORA_X_ENABLED=false" in env.read_text()
    env.write_text("AURORA_X_ENABLED=true\n")                       # the owner turns it on again
    assert sys_config.add_missing(env, schema) == []
    assert "AURORA_X_ENABLED=true" in env.read_text()


# ---- C656 made real (MINOR 13: the old test only grepped the text): the uninstaller's Lean block, run -------------
def _lean_block(root: Path, lean_home: str) -> str:
    text = (ROOT / "uninstall.sh").read_text()
    block = text[text.index("LEAN_HOME=$(sed -n"):text.index("[ -d sys/runtime/lean ] && ok")]
    (root / ".env").write_text(f"AURORA_LEAN_HOME={lean_home}\n")
    harness = ("set -u\nok() { echo \"OK $*\"; }\nrun() { echo \"RUN $*\"; }\nt() { echo \"$2\"; }\n"
               f"ROOT={root}\ncd {root}\n" + block)
    return subprocess.run(["bash", "-c", harness], capture_output=True, text=True, timeout=30).stdout


def _made(d: Path, extra: str = "") -> None:
    for x in ("elan", "workspace"):
        (d / x).mkdir(parents=True)
    (d / ".installed-by-aurora").write_text("")
    if extra:
        (d / extra).write_text("mine")


def test_c656_uninstall_never_removes_a_lean_home_inside_aurora_nor_a_folder_holding_more(tmp_path):
    root = tmp_path / "aurora"
    inside = root / "usr"
    _made(inside)
    out = _lean_block(root, "usr")
    assert "RUN" not in out and "inside Aurora" in out
    outside = tmp_path / "lean"
    _made(outside, extra="notes.txt")                                  # something else in it: kept
    assert "RUN" not in _lean_block(root, str(outside))
    (outside / "notes.txt").unlink()
    out = _lean_block(root, str(outside))
    assert "RUN" in out and str(outside) in out.split("RUN", 1)[1]    # exactly what the script made: removed
    link = tmp_path / "leanlink"
    link.symlink_to(outside)
    assert "RUN" not in _lean_block(root, str(link))
