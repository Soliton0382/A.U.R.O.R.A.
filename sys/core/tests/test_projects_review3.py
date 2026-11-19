# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ The third independent review of N145 / N146 / C615 / N147 (20 Nov 2026): every attack it reproduced, kept as a
test (C642–C657). Invented projects in tmp_path; the caged ones need bwrap."""
import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from aurora import prj_act as A
from aurora import prj_discover as D
from aurora import prj_longrun as R
from aurora import prj_longrun_cage as C
from aurora import prj_novelty as N
from aurora import prj_prereg as P
from aurora import prj_provenance as V
from aurora import prj_run, prj_safeio
from aurora.sec_mask import Pseudonymizer

ROOT = Path(__file__).resolve().parents[3]
ENGINES = ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED")


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "lungo"
    p.mkdir(parents=True)
    (p / "sim.sh").write_text("echo v1 > out.txt\n")
    return p


def _on(cfg):
    for k in ENGINES:
        cfg.values[k] = True


# ---- C642: off by default, not offered ---------------------------------------------------------------------------
def test_c642_the_engines_are_off_by_default_and_their_tools_not_offered(cfg, proj):
    schema = json.loads((ROOT / "sys/core/config/settings_schema.json").read_text())["settings"]
    rec = {s["key"]: s for s in schema if s["key"] in ENGINES}
    assert all(rec[k]["recommended"] == "false" and "true" in rec[k]["old_recommended"] for k in ENGINES)
    for k in ENGINES:
        cfg.values[k] = False
    names = {t["name"] for t in A.Run(cfg, "lungo", Pseudonymizer(cfg), "g").tools}
    assert not names & {"long_run", "novelty_check", "discover_law"} and "read_file" in names
    out = A.call(A.Run(cfg, "lungo", Pseudonymizer(cfg), "g"), "long_run", {"action": "list"})
    assert out["error"] and "not one of this run's tools" in out["text"]
    _on(cfg)
    names = {t["name"] for t in A.Run(cfg, "lungo", Pseudonymizer(cfg), "g").tools}
    assert {"long_run", "novelty_check", "discover_law"} <= names


# ---- C643: never check-then-open by name -------------------------------------------------------------------------
def _exchange(a: Path, b: Path) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    return libc.syscall(316, -100, str(a).encode(), -100, str(b).encode(), 2)   # renameat2, RENAME_EXCHANGE


@pytest.mark.skipif(os.uname().machine != "x86_64", reason="renameat2's number is x86_64's")
def test_c643_a_folder_swapped_for_a_link_never_lets_a_write_out(cfg, proj, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (proj / "d").mkdir()
    (proj / "lnk").symlink_to(outside)
    stop = threading.Event()

    def swap():
        while not stop.is_set():
            _exchange(proj / "d", proj / "lnk")

    t = threading.Thread(target=swap, daemon=True)
    t.start()
    run = A.Run(cfg, "lungo", Pseudonymizer(cfg), "g")
    end = time.time() + 2.0
    n = 0
    while time.time() < end:
        A.call(run, "write_file", {"path": "d/x.txt", "content": "x"})
        A.call(run, "read_file", {"path": "d/x.txt"})
        n += 1
    stop.set()
    t.join(5)
    assert n > 50 and not (outside / "x.txt").exists() and not list(outside.iterdir())


def test_c643_the_safe_opener_refuses_links_dots_and_pipes(proj, tmp_path):
    (tmp_path / "secret").write_text("TOKEN=abc")
    (proj / "s").symlink_to(tmp_path / "secret")
    os.mkfifo(proj / "pipe")
    for bad in ("s", "../secret", "pipe", "sim.sh/x"):
        with pytest.raises(ValueError):
            prj_safeio.read_bytes(proj, bad)
    with pytest.raises(ValueError):
        prj_safeio.write_text(proj, "s", "x")
    assert (tmp_path / "secret").read_text() == "TOKEN=abc"
    prj_safeio.write_text(proj, "a/b/c.txt", "ok")
    assert prj_safeio.read_text(proj, "a/b/c.txt") == "ok"
    names = [p for p, _, _ in prj_safeio.walk(proj)]
    assert "s" in names and not any(n.startswith("s/") for n in names)


def test_c643_no_file_tool_while_a_long_run_of_the_project_goes(cfg, proj):
    _on(cfg)
    R._save(cfg, "lungo", {"id": "001", "status": "running", "limits": {}, "t": time.time()})
    out = A.call(A.Run(cfg, "lungo", Pseudonymizer(cfg), "g"), "write_file", {"path": "x.txt", "content": "x"})
    assert out["error"] and "long run" in out["text"] and not (proj / "x.txt").exists()
    R._update(cfg, "lungo", "001", status="ended")                 # O1 of C709: ended, its finish() not yet done
    assert A.call(A.Run(cfg, "lungo", Pseudonymizer(cfg), "g"), "write_file", {"path": "x.txt", "content": "x"})["error"]
    R._update(cfg, "lungo", "001", finished="2026-11-20")
    assert not A.call(A.Run(cfg, "lungo", Pseudonymizer(cfg), "g"), "write_file",
                      {"path": "x.txt", "content": "x"})["error"]


# ---- C644: a pipe under the next run's .keep ----------------------------------------------------------------------
def test_c644_a_pipe_never_hangs_the_checkpoint_folder(proj):
    (proj / "checkpoints" / "001").mkdir(parents=True)
    os.mkfifo(proj / "checkpoints" / "001" / ".keep")
    t0 = time.time()
    with pytest.raises(FileExistsError):
        prj_safeio.create_exclusive(proj, "checkpoints/001/.keep")
    prj_safeio.create_exclusive(proj, "checkpoints/002/.keep")
    assert time.time() - t0 < 2


# ---- C645: an unreadable folder is no way around the disk limit ----------------------------------------------------
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_c645_an_unreadable_folder_stops_the_measure(proj):
    (proj / "h").mkdir()
    (proj / "h" / "big").write_bytes(b"\0" * 4096)
    os.chmod(proj / "h", 0)
    try:
        with pytest.raises(C.Unmeasurable):
            C.disk_bytes(proj)
    finally:
        os.chmod(proj / "h", 0o755)


# ---- C648: finished once; one GPU run at a time ------------------------------------------------------------------
def test_c648_finish_runs_once(cfg, proj):
    _on(cfg)
    R._save(cfg, "lungo", {"id": "001", "status": "ended", "exit": 0, "limits": {}, "t": time.time(), "outputs": [],
                           "frozen": "", "attempts": 1, "used_s": 1, "cpu_used_s": 1})
    R.finish(cfg, "lungo", "001")
    R.finish(cfg, "lungo", "001")
    R.sweep(cfg, "lungo")
    assert len(list((proj / "longrun").glob("001.MANIFEST*"))) == 1
    assert len(list((proj / "longrun").glob("001*.json"))) == 1


def test_c648_a_second_gpu_run_is_refused_while_one_starts(cfg, proj, monkeypatch):
    _on(cfg)
    monkeypatch.setattr(R, "gpu_holder", lambda cfg: "")
    monkeypatch.setattr(R, "shutil_which", lambda x: "/usr/bin/bwrap")
    monkeypatch.setattr(R, "launch", lambda *a, **k: None)
    monkeypatch.setattr(P, "mode", lambda cfg: "off")
    cfg.values["AURORA_LONGRUN_MAX_ACTIVE"] = 5
    lim = R.limits(cfg, {"wall_s": 30, "mem_mb": 512, "disk_mb": 10, "gpu": True})
    R.start(cfg, "lungo", "true", lim, code_files=["sim.sh"])
    with pytest.raises(RuntimeError, match="GPU long run"):
        R.start(cfg, "lungo", "true", lim, code_files=["sim.sh"])


# ---- C649: provenance by ctime and inode; a capped snapshot --------------------------------------------------------
def test_c649_a_same_size_rewrite_with_its_mtime_set_back_is_seen(proj):
    f = proj / "t.csv"
    f.write_text("x,y\n1,2\n")
    before = prj_run.snapshot(proj)
    st = f.stat()
    time.sleep(0.02)
    f.write_text("x,y\n3,4\n")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert "t.csv" in prj_run.changed(before, prj_run.snapshot(proj))


def test_c649_tables_past_the_cap_are_still_listed_and_nothing_is_claimable(cfg, proj, monkeypatch):
    monkeypatch.setattr(prj_run, "MAX_FILES", 5)
    for i in range(10):
        (proj / f"f{i}.txt").write_text("x")
    (proj / "late.csv").write_text("x,y\n1,2\n")
    snap, capped = prj_run.snapshot_full(proj)
    assert capped and "late.csv" in snap
    V.record_capped(cfg, "lungo")
    ok, why = V.verdict(cfg, "lungo", "late.csv", "0" * 64)
    assert not ok and "no record that the owner brought" in why       # C697: no owner's row, whatever the cap


# ---- C650–C652: the literature check -----------------------------------------------------------------------------
def test_c651_claims_in_other_languages_ask_for_english_keywords(cfg):
    _on(cfg)
    for claim in ("La loi de la chute des corps est une loi pour les objets", "Die Periode des Pendels ist nicht mit der Masse"):
        r = N.check(cfg, claim, sources={}, record=False, report=False)
        assert r["status"] in ("refused", "error") and "not in English" in " ".join(r["errors"])
    assert N.foreign("The period of a pendulum does not depend on its mass") == ""


def test_c652_the_agent_must_name_the_project(cfg):
    _on(cfg)
    agent = type("Ag", (), {"cfg": cfg, "projects": set()})()
    assert N.agent_call(agent, {"claim": "the period of a pendulum grows with its length"}).startswith("REFUSED")
    s = N.offered(cfg, "freeze_predictions")[0]["input_schema"]
    assert "project" in s["required"]


def test_c650_the_verdict_names_its_query(cfg):
    r = {"status": "not_found", "seconds": 1.0, "query": "pendulum period length", "answered": ["arxiv"]}
    assert "for the query «pendulum period length»" in N.text(r)


# ---- C653: lookalike letters in reserved titles ------------------------------------------------------------------
def test_c653_lookalike_letters_do_not_hide_a_reserved_title():
    for t in ("Disсovered law for y", "Lоng run 9", "DΙSCOVERY split", "Ｄiscovered law"):
        assert P.reserved(t), t
    for t in ("Discussion of the law", "Long-term plan", "Lungo run"):
        assert not P.reserved(t), t


# ---- C657: the installer -----------------------------------------------------------------------------------------
SCRIPT = ROOT / "sys/core/script/sys_proofs_install.sh"


def test_c657_dry_run_in_any_order_and_no_foreign_folder(tmp_path):
    new = tmp_path / "lean"
    r = subprocess.run(["bash", str(SCRIPT), str(new), "--dry-run"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "[dry-run]" in r.stdout and not new.exists()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".ssh").mkdir()
    r = subprocess.run(["bash", str(SCRIPT), "--dry-run", str(home)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "not made by this script" in r.stdout
    assert subprocess.run(["bash", str(SCRIPT), "--nope"], capture_output=True, timeout=60).returncode == 2


def test_c656_uninstall_never_removes_a_lean_home_inside_aurora():
    text = (ROOT / "uninstall.sh").read_text()
    assert '"$ROOT"/*) ok' in text and "! -name workspace" in text


# ---- C655: project_install never runs the project's interpreter --------------------------------------------------
def test_c655_project_install_never_runs_the_project_s_python(cfg, monkeypatch):
    import importlib.util
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    monkeypatch.setenv("AURORA_PLUGIN", "projects")
    spec = importlib.util.spec_from_file_location("projects_plugin_r3", ROOT / "sys/plugins/projects/server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert not hasattr(mod, "TOKEN")                         # C674: the plugin holds no token any more
    proj = cfg.path("AURORA_PROJECTS_DIR") / "prova"
    proj.mkdir(parents=True)
    calls = []
    real = subprocess.run

    def spy(args, *a, **k):
        calls.append([str(x) for x in args])
        if "--dry-run" in args:
            return subprocess.CompletedProcess(args, 0, json.dumps({"install": []}), "")
        return real(args, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", spy)
    assert "already there" in mod.project_install("prova", ["numpy"])
    venv_py = str(proj / ".venv" / "bin" / "python")
    assert not any(venv_py in c or "--python" in c for c in calls)
