# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔎 The tenth (final) review of N145–N147 (20 Nov), its attacks replayed on invented installations (tmp_path, a tmpfs
on the reference machine: the writes here, tens of MB, never touch the real disk):
  C710 descriptors /proc/<pid>/fd does not show — a thread's own table (unshare(CLONE_FILES)), a process made
       non-dumpable (its table unreadable) — counted by the disk guard;
  C711 create_picture painted locally in a run held to the local model or touching a «riservato» project;
  C712 a clone's tables checked for echoes of the agent's and the plugins' tables, as an upload's (C708);
  C713 no long run while the owner's «Salva» is being made (one key for the project, resolved);
  a plan step put off while the owner holds the project, no try spent.
Invented data only."""
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import prj_longrun as R
from aurora import prj_policy
from aurora import prj_provenance as V
from aurora import prj_run
from aurora import prj_run_box as B
from aurora import prj_run_disk as D

MB = 1024 * 1024


def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")


@pytest.fixture(autouse=True)
def _on(cfg, monkeypatch):
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True
    cfg.values["AURORA_PREREG_MODE"] = "off"
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


def _proj(cfg, name):
    p = cfg.path("AURORA_PROJECTS_DIR") / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---- C710: every descriptor table, an unreadable one counted ---------------------------------------------------------
def _link(fd: str) -> str:
    try:
        return os.readlink(f"/proc/{os.getpid()}/fd/{fd}")
    except OSError:                                    # listdir's own descriptor, closed meanwhile
        return ""


def test_c710_held_reads_a_thread_s_own_descriptor_table(tmp_path):
    b0, _ = D.held([os.getpid()], tmp_path)
    ready, done, err = threading.Event(), threading.Event(), []

    def own_table():
        try:
            os.unshare(os.CLONE_FILES)                 # this thread's table: /proc/<pid>/fd does not show it
            fd = os.open(tmp_path / "gone", os.O_RDWR | os.O_CREAT, 0o600)
            os.write(fd, b"x" * (3 * MB))
            os.unlink(tmp_path / "gone")
        except OSError as e:
            err.append(e)
        ready.set()
        done.wait(10)
        if not err:
            os.close(fd)
    t = threading.Thread(target=own_table)
    t.start()
    try:
        ready.wait(10)
        if err:
            pytest.skip(f"unshare(CLONE_FILES) refused here: {err[0]}")
        assert not any(_link(x).endswith("gone (deleted)") for x in os.listdir(f"/proc/{os.getpid()}/fd"))
        b, _ = D.held([os.getpid()], tmp_path)
        assert b - b0 >= 3 * MB                        # before: 0
    finally:
        done.set()
        t.join()


NODUMP = r'''
import ctypes, sys, time
ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)                  # PR_SET_DUMPABLE 0: /proc/<pid>/fd unreadable from outside
print("ready", flush=True)
time.sleep(30)
'''


def test_c710_a_table_that_cannot_be_read_counts_as_hidden(tmp_path):
    p = subprocess.Popen([sys.executable, "-c", NODUMP], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "ready"
        try:
            os.listdir(f"/proc/{p.pid}/fd")
            pytest.skip("a non-dumpable process's descriptors are readable here (privileged)")
        except PermissionError:
            pass
        assert D.held([p.pid], tmp_path)[1] >= 1       # before: skipped in silence, 0
    finally:
        p.kill()
        p.wait()
    assert D.held([p.pid], tmp_path) == (0, 0)         # gone: nothing hidden


# the referee's writer (x1.py), smaller: N files of M MB written, deleted, kept open in a thread's own table or by a
# non-dumpable process
HIDE = r'''
import ctypes, os, sys, threading, time
mode, n, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
def fill():
    if mode == "thread":
        os.unshare(os.CLONE_FILES)
    fds = []
    for i in range(n):
        fd = os.open(f"b{i}", os.O_RDWR | os.O_CREAT, 0o600)
        for _ in range(size): os.write(fd, b"x" * (1 << 20))
        os.unlink(f"b{i}"); fds.append(fd); time.sleep(0.2)
    print("filled", mode, flush=True); time.sleep(float(sys.argv[4]) if len(sys.argv) > 4 else 2)
    print("still alive", flush=True)
if mode == "nodump":
    ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)
    fill()
else:
    t = threading.Thread(target=fill); t.start(); t.join()
'''


@needs_cage
@pytest.mark.parametrize("mode", ["thread", "nodump"])
def test_c710_run_in_project_stops_what_a_hidden_table_holds(cfg, monkeypatch, mode):
    # before: 6 × 80 MB on a budget of 100 MB, exit 0. Here 6 × 10 MB on a budget of 20 MB (tmpfs)
    orig = B.profile
    monkeypatch.setattr(B, "profile", lambda kind, readonly=False: {**orig(kind, readonly), "disk_mb": 20}
                        if kind == "run" else orig(kind, readonly))
    p = _proj(cfg, "demo")
    (p / "hide.py").write_text(HIDE)
    r = prj_run.run(cfg, "demo", f"python3 hide.py {mode} 6 10")
    assert r["exit"] == B.DISK_STOP and "the project grew by" in r["output"], r
    assert "still alive" not in r["output"]


@needs_cage
@pytest.mark.parametrize("mode", ["thread", "nodump"])
def test_c710_a_long_run_stops_what_a_hidden_table_holds(cfg, monkeypatch, mode):
    # before: disk_mb 50, 12 × 40 MB: «ended 0». Here disk_mb 10, 6 × 8 MB
    monkeypatch.setattr(R, "DISK_EVERY_S", 15.0)
    p = _proj(cfg, "demo")
    (p / "hide.py").write_text(HIDE)
    st = R.start(cfg, "demo", f"python3 hide.py {mode} 6 8 20",
                 R.limits(cfg, {"wall_s": 120, "mem_mb": 2048, "disk_mb": 10}), mode, code_files=[])
    end = time.time() + 60
    while not (st := R.load(cfg, "demo", st["id"])).get("finished"):
        assert time.time() < end, st
        time.sleep(0.1)
    assert st["status"] == "stopped" and "the project grew by" in st["why"], st


# ---- C711: create_picture held local ---------------------------------------------------------------------------------
def _agent(cfg, projects=(), local=False):
    from aurora.agt_loop import Agent
    import logging
    a = Agent.__new__(Agent)
    a.cfg, a.asked, a.net_read, a.projects, a.named_projects = cfg, True, None, set(projects), set()
    a.goal_text, a.loop_tools, a.host = "x", None, SimpleNamespace(get=lambda n: None)
    a.local_only, a.produced, a.log = local, [], logging.getLogger("test-review10")
    return a


class _Painted(Exception):
    pass


@pytest.mark.parametrize("projects,local,want", [({"brevetto"}, False, True), ({"locale"}, True, True),
                                                  ({"aperto"}, False, False)])
def test_c711_create_picture_is_painted_locally_in_a_local_or_reserved_run(cfg, monkeypatch, projects, local, want):
    from aurora import mdl_image, sys_features
    for n in ("brevetto", "locale", "aperto"):
        _proj(cfg, n)
    prj_policy.save(cfg, "brevetto", {"models": "cloud", "riservato": True})
    prj_policy.save(cfg, "locale", {"models": "local"})
    monkeypatch.setattr(sys_features, "need", lambda *a, **k: None)
    seen = {}

    def paint(prompt, name, cfg=None, emit=None, title="", local_only=False):
        seen["local_only"] = local_only
        raise _Painted()
    monkeypatch.setattr(mdl_image, "paint", paint)
    a = _agent(cfg, projects, local)
    out = a._call("create_picture", {"prompt": "an invented drawing of a brass gear train", "title": "x"}, {},
                  lambda *x: None, "r1")
    assert "not painted" in out and seen["local_only"] is want      # before: False in all three


def test_c711_the_painter_with_local_only_never_asks_the_provider(cfg, monkeypatch):
    from aurora import mdl_image, mdl_media
    asked = []
    monkeypatch.setattr(mdl_media, "provider", lambda cfg, task: asked.append(task) or ("openai", ""))

    def no_gpu(*a, **k):
        raise _Painted()                               # the local painter reached: stopped before the GPU
    monkeypatch.setattr(mdl_image, "gpu_lock", no_gpu)
    with pytest.raises(_Painted):
        mdl_image.paint("an invented drawing of a brass gear train", "t", cfg, local_only=True)
    assert asked == []


# ---- C712: a clone's tables checked for echoes -----------------------------------------------------------------------
def _body(seed: int, head: str = "t,v") -> str:
    g = np.random.default_rng(seed)
    x = g.uniform(1, 5, 200)
    return head + "\n" + "".join(f"{a:.6f},{3 * a * a + e:.6f}\n" for a, e in zip(x, g.normal(0, 0.01, 200)))


def _api(cfg, monkeypatch):
    import importlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import core, projects
    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[core.auth] = lambda: None
    return TestClient(app)


def _clone_of(monkeypatch, files: dict):
    from aurora import prj_gitsafe

    def fake(full, dest, token):                       # git replaced by a copy of the pushed tree
        def make():
            for rel, body in files.items():
                (Path(dest) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(dest) / rel).write_text(body)
        return [sys.executable, "-c", "pass"], {"_make": make}
    real_run = subprocess.run

    def run(cmd, env=None, **k):
        if isinstance(env, dict) and "_make" in env:
            env["_make"]()
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, env=env, **k)
    monkeypatch.setattr(prj_gitsafe, "clone_command", fake)
    monkeypatch.setattr(subprocess, "run", run)


def test_c712_a_plugin_s_table_cloned_back_is_never_the_owner_s(cfg, monkeypatch):
    rc = _proj(cfg, "lab")
    body = _body(1)
    (rc / "circuits").mkdir()
    (rc / "circuits" / "tran.csv").write_text(body)                   # a plugin's table: no row at all
    mine = _body(2, "x,y")                                              # the owner's own table, new
    _clone_of(monkeypatch, {"circuits/tran.csv": body, "data/own.csv": mine})
    client = _api(cfg, monkeypatch)
    r = client.post("/v1/aurora/projects/clone", json={"full_name": "someone/rc"})
    assert r.status_code == 200, r.text
    name = r.json()["name"]
    o = V.origin(cfg, name, "circuits/tran.csv", _sha(body.encode()))
    assert o["kind"] == "agent" and not o["claimable"] and "project lab" in o["why"], o   # before: «owner»
    assert V.origin(cfg, name, "data/own.csv", _sha(mine.encode()))["kind"] == "owner"


def test_c712_an_agent_s_table_of_another_project_cloned_back_stays_the_agent_s(cfg, monkeypatch):
    a = _proj(cfg, "scratch")
    body = _body(3)
    (a / "out.csv").write_text(body)
    V.record(cfg, "scratch", a, ["out.csv"], "command")
    (a / "out.csv").unlink()                                            # gone from the folder: only its row
    _clone_of(monkeypatch, {"res/out.csv": body})
    client = _api(cfg, monkeypatch)
    name = client.post("/v1/aurora/projects/clone", json={"full_name": "someone/res"}).json()["name"]
    assert not V.origin(cfg, name, "res/out.csv", _sha(body.encode()))["claimable"]


def test_c712_past_the_clone_s_time_its_tables_are_unchecked(cfg):
    _proj(cfg, "other")
    body = _body(4).encode()
    canon = V._canonical(body, "a.csv")
    got = __import__("aurora.prj_provenance_seen", fromlist=["x"]).echoes(
        cfg, "new", [("a.csv", len(body), _sha(body), canon)], time.monotonic() - 1)
    assert got == {"a.csv": {"unchecked": "all"}}
    from aurora import prj_provenance_seen as S
    assert "could not be compared" in S.said(got["a.csv"])


# ---- C713: no long run during the owner's «Salva» --------------------------------------------------------------------
def test_c713_a_long_run_is_refused_while_the_owner_saves(cfg, monkeypatch):
    from aurora import prj_package
    p = _proj(cfg, "both")
    alias = p.parent / "alias"
    alias.symlink_to(p)                                # another spelling of the same folder: one key (resolved)
    with prj_package._guard:
        lock = prj_package._locks.setdefault(prj_package._key(prj_run.project_dir(cfg, "both")), threading.Lock())
    lock.acquire()
    try:
        assert prj_package.making(p) and prj_package.making(alias) and prj_package.making(str(p.resolve()))
        with pytest.raises(RuntimeError, match="saving this project"):        # before: started
            R.start(cfg, "both", "sleep 1", R.limits(cfg, {"wall_s": 30, "mem_mb": 512, "disk_mb": 10}), "x",
                    code_files=[])
    finally:
        lock.release()
    assert not prj_package.making(p)


# ---- a plan step put off while the owner holds the project ----------------------------------------------------------
def test_a_plan_step_put_off_by_the_owner_spends_no_try(cfg, monkeypatch):
    from aurora import prj_package, prj_plan, prj_term
    _proj(cfg, "demo")
    cfg.values["AURORA_PROJECT_AUTONOMY"] = 2
    plan = prj_plan.create(cfg, "demo", "un parser", [{"title": "t", "test": "true"}])
    plan["active"] = True
    prj_plan.save(cfg, "demo", plan)
    monkeypatch.setattr(prj_term, "open_on", lambda project: 1)
    with pytest.raises(prj_run.Busy):
        prj_run.run(cfg, "demo", "true")
    for n in range(prj_plan.TRIES + 1):
        out = prj_plan.record(cfg, "demo", 0, {"exit": -2, "output": "not run: terminal", "deferred": True},
                              f"r{n}", "")
    s = out["plan"]["steps"][0]
    assert out["event"] == "" and s["status"] == "open" and s.get("tries", 0) == 0     # before: blocked
    assert s["deferred"][-1]["deferred"] and prj_plan.next_step(out["plan"]) == 0
    assert s["runs"] == [] and len(s["deferred"]) == prj_plan.TRIES + 1  # C714: kept apart, never among the attempts
    assert "PREVIOUS ATTEMPTS" not in prj_plan.goal_for(out["plan"], "demo", 0)
    assert prj_plan.due(cfg, ["demo"], now=time.time() + prj_plan.GAP_S + 1) is None   # C714: held, no agent
    monkeypatch.setattr(prj_term, "open_on", lambda project: 0)
    assert prj_plan.due(cfg, ["demo"], now=time.time() + prj_plan.GAP_S + 1) == "demo"
    assert prj_plan.due(cfg, ["demo"]) is None          # the put-off one still waits its GAP_S: not hammered
    assert prj_plan.daily_line(cfg, "demo") == ""      # put-off runs are no attempts
    out = prj_plan.record(cfg, "demo", 0, {"exit": 1, "output": "1 failed"}, "rx", "")
    assert out["plan"]["steps"][0]["tries"] == 1        # a real failure still counts
    assert prj_package.making(cfg.path("AURORA_PROJECTS_DIR") / "demo") is False
