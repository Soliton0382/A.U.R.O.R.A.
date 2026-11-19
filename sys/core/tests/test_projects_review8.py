# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧱 The eighth referee's findings (20 Nov), reproduced and closed. Invented projects in tmp_path — a tmpfs on the
reference machine: the writes here (tens of MB) never touch the real disk.
  C700: files deleted while mapped (descriptor closed) or held by a descriptor in flight in a socket were not counted
        by the disk guard; a long run's processes were up to 15 s old.
  C701: a .git the user made in the terminal during a long run was set aside at the run's end.
  C702: without a cgroup the per-process address space was presented as a memory ceiling.
  O1: the guard's thaw after hold() in a try/finally. O3: /etc/aurora and the host's cgroup tree hidden in the cages.
  O4: project_install says which scripts it left out."""
import importlib.util
import mmap
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aurora import prj_longrun as R
from aurora import prj_run, prj_term, sys_config
from aurora import prj_run_box as B
from aurora import prj_run_disk as D

MB = 1024 * 1024
PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "projects"


def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")


@pytest.fixture(autouse=True)
def _on(cfg, monkeypatch):
    cfg.values["AURORA_LONGRUN_ENABLED"] = True
    cfg.values["AURORA_PREREG_MODE"] = "off"
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    p.mkdir(parents=True)
    return p


_orig = B.profile


def _wait(cfg, rid, s=60.0):
    end = time.time() + s
    while time.time() < end:
        st = R.load(cfg, "demo", rid)
        if st.get("finished"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"run {rid} did not finish: {R.load(cfg, 'demo', rid)}")


# the referee's writer (n3.py), smaller: N files of M MB each, mapped, the descriptor closed, then deleted
MAPPED = r'''
import mmap, os, sys, time
n, size, how = int(sys.argv[1]), int(sys.argv[2]) << 20, sys.argv[3]
keep = []
for i in range(n):
    fd = os.open(f"blob{i}", os.O_RDWR | os.O_CREAT, 0o600)
    if how == "mapped":                       # the whole file mapped and written through the mapping
        os.ftruncate(fd, size)
        m = mmap.mmap(fd, size, trackfd=False)
        for off in range(0, size, 4096):
            m[off] = 1
        keep.append(m)
    else:                                     # written with write(); one page mapped, or the fd sent in a socket
        for _ in range(size >> 20):
            os.write(fd, b"x" * (1 << 20))
        if how == "page":
            keep.append(mmap.mmap(fd, 4096, trackfd=False))
        else:
            import array, socket
            if not keep:
                keep.extend(socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM))
            keep[0].sendmsg([b"x"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
    os.close(fd)
    os.unlink(f"blob{i}")
    time.sleep(0.2)
print("filled", how, flush=True)
time.sleep(float(sys.argv[4]) if len(sys.argv) > 4 else 2)
print("still alive")
'''


# ---- C700: the files no folder lists ---------------------------------------------------------------------------
def test_c700_held_sees_mapped_deleted_files_and_socket_carriers(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    b0, h0 = D.held([os.getpid()], root)                   # pytest's own sockets, if any
    fd = os.open(root / "gone", os.O_RDWR | os.O_CREAT, 0o600)
    os.ftruncate(fd, 3 * MB)
    m = mmap.mmap(fd, 3 * MB, trackfd=False)
    os.close(fd)
    os.unlink(root / "gone")
    try:
        b, hidden = D.held([os.getpid()], root)
        assert b - b0 >= 3 * MB and hidden - h0 == 1       # before: 0 bytes (only /proc/<pid>/fd was read)
        a, c = socket.socketpair()
        try:
            assert D.held([os.getpid()], root)[1] - h0 == 1   # C707: an idle pair carries nothing
            a.send(b"x")                                      # a byte queued: a descriptor could ride on it
            assert D.held([os.getpid()], root)[1] - h0 == 3   # the mapping and the two sockets
        finally:
            a.close()
            c.close()
        other = Path("/proc")                              # not on the project's path or device: not hidden (memfd,
        assert D.held([os.getpid()], other)[1] == h0       # the cage's RAM disks: its cgroup's memory)
    finally:
        m.close()


class _Fs:
    def __init__(self, free_mb, size_mb=100_000, files=1_000_000, ffree=500_000):
        self.f_frsize, self.f_blocks, self.f_bavail = MB, size_mb, free_mb
        self.f_files, self.f_favail = files, ffree


def test_c700_guard_counts_the_lost_space_while_something_is_hidden(monkeypatch):
    fs = {"v": _Fs(50_000)}
    monkeypatch.setattr(B.os, "statvfs", lambda p: fs["v"])
    monkeypatch.setattr(B, "CONFIRM_S", 0.0)
    m = {"v": (0, 0)}
    g = B.Guard("/x", 100, measure=lambda: m["v"], base=0)
    fs["v"], m["v"] = _Fs(49_850), (20 * MB, 0)            # 150 MB lost, 20 MB measured, nothing hidden: others
    assert g.check() == "" and g.clean == (49_850 * MB, 20 * MB)
    fs["v"], m["v"] = _Fs(49_700), (25 * MB, 1)            # 150 MB more lost, 5 measured, one mapping hidden
    why = g.check()
    assert "grew by 170.0 MB > 100 MB" in why and "holder(s) of files no folder lists" in why
    fs["v"] = _Fs(50_000)
    g2 = B.Guard("/x", 100, measure=lambda: (10 * MB, 2), base=0, grown0=30 * MB)   # a long run's 2nd attempt
    fs["v"] = _Fs(49_920)                                   # 80 MB lost since the attempt began, 30 MB from before
    assert "grew by 110.0 MB > 100 MB" in g2.check()


@needs_cage
@pytest.mark.parametrize("how", ["mapped", "page", "socket"])
def test_c700_run_in_project_stops_files_it_deleted_while_held(cfg, proj, monkeypatch, how):
    # before: 6 × 80 MB mapped, budget 100 MB: exit 0. Here 6 × 10 MB on a budget of 20 MB (tmpfs)
    run = B.profile("run")
    monkeypatch.setattr(B, "profile", lambda kind, readonly=False: {**run, "disk_mb": 20} if kind == "run"
                        else _orig(kind, readonly))
    (proj / "mm.py").write_text(MAPPED)
    r = prj_run.run(cfg, "demo", f"python3 mm.py 6 10 {how}")
    assert r["exit"] == B.DISK_STOP and "the project grew by" in r["output"], r
    assert "still alive" not in r["output"]


@needs_cage
def test_c700_a_long_run_stops_files_it_deleted_while_mapped(cfg, proj, monkeypatch):
    # before: disk_mb 50, 12 × 40 MB mapped: «ended 0». Here disk_mb 10, 6 × 8 MB
    monkeypatch.setattr(R, "DISK_EVERY_S", 15.0)
    (proj / "mm.py").write_text(MAPPED)
    st = R.start(cfg, "demo", "python3 mm.py 6 8 mapped 20", R.limits(cfg, {"wall_s": 120, "mem_mb": 2048,
                                                                            "disk_mb": 10}), "mapped", code_files=[])
    t0 = time.time()
    st = _wait(cfg, st["id"])
    assert st["status"] == "stopped" and "the project grew by" in st["why"], st
    assert time.time() - t0 < 15


# ---- O1: the guard never leaves the command frozen -----------------------------------------------------------------
def test_o1_the_guard_thaws_after_an_error_and_after_a_measure_under_the_budget(monkeypatch):
    fs = {"v": _Fs(50_000)}
    monkeypatch.setattr(B.os, "statvfs", lambda p: fs["v"])
    monkeypatch.setattr(B, "CONFIRM_S", 0.0)
    thawed = []

    def boom():
        raise PermissionError(13, "denied")
    g = B.Guard("/x", 100, measure=boom, base=0, hold=lambda: (lambda: thawed.append(1)))
    fs["v"] = _Fs(49_800)
    with pytest.raises(PermissionError):
        g.check()
    assert thawed == [1]                                   # before: left frozen for ever
    g.measure = lambda: 10 * MB
    assert g.check() == "" and thawed == [1, 1]
    g.measure = lambda: 500 * MB
    fs["v"] = _Fs(49_000)
    assert "grew by" in g.check() and thawed == [1, 1]     # stopped: left frozen until it is killed


# ---- C701: the user's terminal and a long run never overlap ----------------------------------------------------------
def test_c701_no_terminal_while_a_long_run_goes(cfg, proj, monkeypatch):
    monkeypatch.setattr(R, "busy", lambda c, name: name == "demo")
    with pytest.raises(prj_term.TermError, match="long run of this project is going"):
        prj_term._cage(cfg, proj)


def test_c701_no_long_run_while_a_terminal_is_open(cfg, proj, monkeypatch):
    if not shutil.which("bwrap"):
        pytest.skip("bwrap")

    class P:
        def poll(self):
            return None
    monkeypatch.setitem(prj_term._sessions, "t1", {"proc": P(), "path": str(proj)})
    assert prj_term.open_on(proj) == 1 and prj_term.open_on(proj.parent) == 0
    with pytest.raises(RuntimeError, match="terminal"):
        R.start(cfg, "demo", "true", R.limits(cfg, {"wall_s": 10, "mem_mb": 256, "disk_mb": 10}), "x", code_files=[])
    assert R.runs(cfg, "demo") == []


@needs_cage
def test_c701_the_referees_attack_the_users_git_is_never_set_aside(cfg, proj):
    # before (n7.py): the terminal's cage made .git during a run of 6 s; the run's end set it aside
    st = R.start(cfg, "demo", "sleep 2", R.limits(cfg, {"wall_s": 60, "mem_mb": 512, "disk_mb": 10}), "wait",
                 code_files=[])
    with pytest.raises(prj_term.TermError):
        prj_term._cage(cfg, proj)
    _wait(cfg, st["id"])
    args = prj_term._cage(cfg, proj)[:-2] + ["-c", "git init -q -b main && git add -A && git -c user.name=u -c "
                                                   "user.email=u@x commit -qm mine --allow-empty && echo made"]
    assert "made" in subprocess.run(args, capture_output=True, text=True, timeout=60).stdout
    assert (proj / ".git").is_dir() and not list(proj.glob(".git.set-aside-*"))


# ---- C702: the fallback said, never presented as a ceiling --------------------------------------------------------
@needs_cage
def test_c702_without_a_cgroup_the_output_says_there_is_no_memory_ceiling(cfg, proj):
    from aurora import prj_longrun_meter as M
    if M.delegated() is not None:
        pytest.skip("a delegated cgroup here: the kernel's ceiling holds")
    r = prj_run.run(cfg, "demo", "echo hi")
    assert "no memory ceiling for the command as a whole" in r["output"] and "C702" in r["output"]
    ro = prj_run.run(cfg, "demo", "echo hi", readonly=True)           # the referee's: no address space limit, no
    assert "C702" not in ro["output"]                                 # note (it was never presented as one)


# ---- O3: /etc/aurora and the host's cgroup tree hidden ----------------------------------------------------------------
@needs_cage
def test_o3_the_machines_setup_is_hidden_in_the_cages(cfg, proj):
    r = prj_run.run(cfg, "demo", "echo L:$(ls -A /etc/aurora /sys/fs/cgroup 2>/dev/null | grep -v : | tr -d '\\n'):; "
                                 "(echo x > /sys/fs/cgroup/planted) 2>/dev/null || echo cg-ro; "
                                 "test -e /etc/aurora/root.conf || echo conf-gone")
    out = r["output"]
    assert "L::" in out and "cg-ro" in out, out                        # both empty; the tmpfs read only
    assert "conf-gone" in out
    from aurora import prj_browse
    args = prj_browse._git_cage(proj, cfg) or []
    assert not args or ("/sys/fs/cgroup" in args and ("/etc/aurora" in args or not Path("/etc/aurora").is_dir()))


# ---- O4: the scripts left out, said ----------------------------------------------------------------------------------
def test_o4_merge_returns_the_scripts_it_left_out(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(sys_config, "_cached", cfg)
    monkeypatch.setenv("AURORA_PLUGIN", "projects")
    spec = importlib.util.spec_from_file_location("projects_plugin_server_r8", PLUGIN / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = cfg.path("AURORA_PROJECTS_DIR") / "pkg"
    p.mkdir(parents=True)
    env = p / ".venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env)], check=True, capture_output=True)
    stage = tmp_path / "stage"
    (stage / "bin").mkdir(parents=True)
    for n in ("git", "ls", "python3.99", "aurora-r8-tool"):
        (stage / "bin" / n).write_text("#!/bin/sh\necho hi\n")
    site = next(env.glob("lib/python*/site-packages"))
    assert mod._merge(stage, site, env, p) == ["git", "ls", "python3.99"]
    assert (env / "bin" / "aurora-r8-tool").is_file()
