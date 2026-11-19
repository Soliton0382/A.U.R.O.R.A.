# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ C654: the whole long run's CPU cannot be dodged with short children the kernel reaps (a parent that ignores
SIGCHLD: their time reaches no parent and no /proc sum). The referee's attack through the real cage and prj_longrun;
the service-cgroup ledger (no delegation, this machine today) and a cgroup of the run's own (a delegated cgroup: a
transient user service with Delegate=yes, when systemd-run --user is there) — its hard memory and process limits, and
a cage that cannot raise them or leave. Invented commands; the cage needs bwrap."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aurora import prj_longrun as R
from aurora import prj_longrun_meter as M

HERE = Path(__file__).resolve()
CORE = HERE.parents[1]

# the referee's attack: SIGCHLD ignored, children of `each` CPU seconds born one after the other, each dead before
# the next look; the parent itself almost idle
ATTACK = """import os, signal, sys, time
n, each = int(sys.argv[1]), float(sys.argv[2])
signal.signal(signal.SIGCHLD, signal.SIG_IGN)
for _ in range(n):
    if os.fork() == 0:
        t = time.process_time()
        while time.process_time() - t < each:
            pass
        os._exit(0)
    time.sleep(each * 1.1)
"""


def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")
needs_cgroup = pytest.mark.skipif(M.own() is None or M.cpu_usec(M._dir(M.own() or "/")) is None,
                                  reason="no cgroup v2 counter readable here")


@pytest.fixture(autouse=True)
def _on(cfg, monkeypatch):
    cfg.values["AURORA_LONGRUN_ENABLED"] = True
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "DISK_EVERY_S", 0.2)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "lungo"
    p.mkdir(parents=True)
    (p / "attack.py").write_text(ATTACK, encoding="utf-8")
    return p


def wait(cfg, rid, s=60.0):
    end = time.time() + s
    while time.time() < end:
        st = R.load(cfg, "lungo", rid)
        if st.get("finished"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"run {rid} did not finish: {R.load(cfg, 'lungo', rid)}")


@needs_cage
@needs_cgroup
def test_c654_children_the_kernel_reaps_are_counted_and_stop_the_run(cfg, proj):
    # 10 children × 0.4 s = 4 s of CPU on 1 s declared; the /proc sum saw ~0.4 s of such a run and let it end (exit 0)
    st = R.start(cfg, "lungo", "python3 attack.py 10 0.4", R.limits(cfg, {"wall_s": 60, "mem_mb": 1024, "disk_mb": 10,
                                                                          "cpu_s": 1}), code_files=["attack.py"])
    t0 = time.time()
    st = wait(cfg, st["id"])
    assert st["meter"] in ("cgroup", "ledger")
    assert st["status"] == "stopped" and "CPU time 1 s of the whole run" in st["why"], st
    assert 1.0 <= st["cpu_used_s"] < 2.5 and time.time() - t0 < 4.0      # stopped near 1 s, long before the 4 s


@needs_cage
def test_c654_core_every_process_of_a_run_starts_with_core_limit_one(cfg, proj):
    # C654-core: with a piped core_pattern only RLIMIT_CORE 1 makes the kernel skip the dump (0 is still recorded)
    (proj / "core.py").write_text("import resource\nprint(resource.getrlimit(resource.RLIMIT_CORE))\n")
    st = wait(cfg, R.start(cfg, "lungo", "python3 core.py > core.txt; bash -c 'ulimit -c -H' > hard.txt",
                           R.limits(cfg, {"wall_s": 30, "mem_mb": 1024, "disk_mb": 10}), code_files=["core.py"])["id"])
    assert st["status"] == "ended", st
    assert (proj / "core.txt").read_text().strip() == "(1, 1)"
    assert (proj / "hard.txt").read_text().strip() == "0"      # bash counts 512-byte blocks: 1 byte reads 0


@needs_cgroup
def test_ledger_counts_what_the_kernel_reaped_unseen(tmp_path):
    (tmp_path / "attack.py").write_text(ATTACK, encoding="utf-8")
    m = M.Meter({"mem_mb": 512}, "t", 64, root=None) if M.delegated() is None else None
    if m is None or m.mode != "ledger":
        pytest.skip("this process has a delegated cgroup: the ledger is not used here")
    p = subprocess.Popen([sys.executable, "-I", str(tmp_path / "attack.py"), "6", "0.3"])
    seen = []
    while p.poll() is None:
        time.sleep(0.2)
        seen.append(m.read(p.pid))
    seen.append(m.read(p.pid))
    seen.append(m.read(p.pid))
    assert max(s["cpu_s"] for s in seen) >= 1.5                             # 6 × 0.3 = 1.8 s, the tree alone ~0.3
    assert any(s["unseen_s"] > 1.0 for s in seen)
    assert all(a["cpu_s"] <= b["cpu_s"] for a, b in zip(seen, seen[1:]))   # never less than read before


def test_one_reading_alone_never_counts_a_loss(monkeypatch):
    # a process reaped between the reads of its parent and its own looks lost once: two readings must agree
    m = M.Meter.__new__(M.Meter)
    m.mode, m.cpu, m._lost, m.u0, m.l0, m.dir, m.oom = "ledger", 0.0, [], 0.0, 0.0, None, 0
    readings = iter([(10.0, 10.0), (300.0, 10.0), (11.0, 11.0), (20.0, 11.0), (21.0, 11.0)])
    monkeypatch.setattr(m, "_ledger", lambda procs: next(readings))
    monkeypatch.setattr(M, "_scan", lambda: {})
    got = [m.read(1)["unseen_s"] for _ in range(5)]
    assert got == [0.0, 0.0, 0.0, 0.0, 9.0]


def test_pause_shortens_near_the_end():
    assert M.pause(1.0, 1000) == 1.0
    assert M.pause(1.0, 0.0) == 0.05
    assert M.pause(1.0, M.NCPU * 0.5) == 0.5


def test_no_delegation_outside_a_service(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    assert M._find() is None                                              # a desktop's scope is never taken over


# ---- a cgroup of the run's own: a transient user service with its cgroup delegated -----------------------------
def _user_systemd() -> bool:
    if not shutil.which("systemd-run"):
        return False
    try:
        return not subprocess.run(["systemd-run", "--user", "--wait", "--quiet", "-p", "Delegate=yes", "--", "/bin/true"],
                                  capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return False


@needs_cage
@pytest.mark.skipif(not _user_systemd(), reason="no user systemd that delegates a cgroup here")
def test_a_cgroup_of_its_own_counts_limits_and_holds(tmp_path):
    (tmp_path / "attack.py").write_text(ATTACK, encoding="utf-8")
    out = subprocess.run(["systemd-run", "--user", "--wait", "--pipe", "--quiet", "-p", "Delegate=yes",
                          f"--working-directory={tmp_path}", "-E", f"PYTHONPATH={CORE}", "--",
                          sys.executable, str(HERE), "probe", str(tmp_path)],
                         capture_output=True, text=True, timeout=120)
    line = [x for x in out.stdout.splitlines() if x.startswith("{")]
    assert line, out.stdout + out.stderr
    r = json.loads(line[-1])
    assert r["mode"] == "cgroup" and r["moved_into_main"]
    assert r["attack_cpu_s"] >= 1.6                       # 6 × 0.3 s, every one counted by the kernel
    assert r["attack_proc_sum_s"] < 1.0                   # what the /proc sum saw of the same run
    assert r["forks_ok"] < 30 and r["fork_refused"]       # pids.max 24 holds in the cage
    assert r["oom"] >= 1 and r["mem_rc"] != 0             # 400 MB in a run of 64 MB: the kernel ends it
    assert r["raise_limit_rc"] != 0 and r["leave_rc"] != 0   # the cage can neither raise its limit nor leave
    assert r["removed"]


def _probe(tmp: Path) -> dict:
    """Run inside the delegated service: the meter's cgroup mode with the real cage (bwrap)."""
    base = M.delegated()
    r = {"mode": "", "moved_into_main": bool(base) and (M.own() or "").endswith("/" + M.SUB)}

    def cage(cmd):
        return ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--ro-bind", "/", "/", "--dev", "/dev",
                "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(tmp), str(tmp), "--chdir", str(tmp), "--",
                "bash", "-c", cmd]

    def run(cmd, lim, tasks=64):
        m = M.Meter(lim, "probe", tasks)
        p = subprocess.Popen(m.argv(cage(cmd)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        top = 0.0
        while p.poll() is None:
            time.sleep(0.1)
            top = max(top, sum(M._scan().get(x, ("", 0, 0.0))[2] for x in m.read(p.pid)["pids"]))
        text = p.stdout.read()
        rc = p.wait()
        d = m.dir
        end = m.close()
        return m, rc, text, end, top, d

    m, rc, _t, end, top, d = run(f"{sys.executable} -I attack.py 6 0.3", {"mem_mb": 256})
    r.update(mode=m.mode, attack_cpu_s=end["cpu_s"], attack_proc_sum_s=top, removed=d is not None and not d.exists())
    forks = ("import os, time\nn = 0\ntry:\n    for _ in range(30):\n        if os.fork() == 0:\n"
             "            time.sleep(3); os._exit(0)\n        n += 1\nexcept OSError as e:\n    print('refused', e)\n"
             "print('forks=%d' % n)\n")
    (tmp / "forks.py").write_text(forks, encoding="utf-8")
    _m, _rc, text, _e, _t2, _d = run(f"{sys.executable} -I forks.py", {"mem_mb": 256}, tasks=24)
    r["forks_ok"] = int(([x.split("=")[1] for x in text.split() if x.startswith("forks=")] or ["99"])[0])
    r["fork_refused"] = "refused" in text
    _m, rc, _x, end, _t3, _d = run(f"{sys.executable} -c 'b = bytearray(400 * 1024 * 1024); print(len(b))'",
                                   {"mem_mb": 64})
    r.update(mem_rc=rc, oom=end["oom"])
    own = M.own()
    m = M.Meter({"mem_mb": 64}, "esc", 64)
    g = str(m.dir)
    p = subprocess.run(m.argv(cage(f'echo max > {g}/memory.max')), capture_output=True)
    r["raise_limit_rc"] = p.returncode
    p = subprocess.run(m.argv(cage(f'echo $$ > {M._dir(own)}/cgroup.procs')), capture_output=True)
    r["leave_rc"] = p.returncode
    r["max_after"] = (m.dir / "memory.max").read_text().strip()
    m.close()
    return r


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "probe":
    print(json.dumps(_probe(Path(sys.argv[2]))), flush=True)
    os._exit(0)
