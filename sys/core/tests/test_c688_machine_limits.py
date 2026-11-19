# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧱 The seventh referee's attacks on the machine, reproduced and now failing (C688, C689, C691; invented projects in
tmp_path — a tmpfs on the reference machine: nothing here fills the real disk).
  - C688: a caged command with no file-size, disk or memory limit (1.5 GB in 0.4 s); a long run of disk_mb 10 whose
    100 processes wrote 954 MB between two 15 s looks; /dev a writable tmpfs of half the memory (O1); code_files
    without a limit (O6). A cgroup of the cage's own where a delegated one exists (a transient user service).
  - C689: long_run's outputs globbed through a link to / — for ever, and an oracle on the host's files.
  - C691: the set-aside's name planted ahead by the command.
The cage needs bwrap."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from aurora import prj_longrun as R
from aurora import prj_longrun_cage as C
from aurora import prj_run
from aurora import prj_run_box as B

HERE = Path(__file__).resolve()
CORE = HERE.parents[1]
MB = 1024 * 1024
# the referee's writer: 100 processes of 10 MB each, all at once
FLOOD = "mkdir -p out; for i in $(seq 1 100); do (head -c 10000000 /dev/zero > out/part$i) & done; wait; sleep 30"


def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")


@pytest.fixture(autouse=True)
def _on(cfg, monkeypatch):
    for k in ("AURORA_LONGRUN_ENABLED",):
        cfg.values[k] = True
    cfg.values["AURORA_PREREG_MODE"] = "off"
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    p.mkdir(parents=True)
    return p


def wait(cfg, rid, s=60.0):
    end = time.time() + s
    while time.time() < end:
        st = R.load(cfg, "demo", rid)
        if st.get("finished"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"run {rid} did not finish: {R.load(cfg, 'demo', rid)}")


def _empty(folder: Path) -> None:
    for f in folder.rglob("*"):
        if f.is_file() and not f.is_symlink():
            f.open("w").close()


# ---- C688: prj_run's cage --------------------------------------------------------------------------------------------
@needs_cage
def test_c688_a_single_file_stops_at_its_limit(cfg, proj, monkeypatch):
    # before: 1.5 GB written in 0.4 s, ulimit -f unlimited. Here a profile of 8 MB per file, 20 MB written
    run = B.profile("run")
    monkeypatch.setattr(B, "profile", lambda kind, readonly=False: {**run, "file_mb": 8})
    r = prj_run.run(cfg, "demo", "ulimit -f; head -c 20000000 /dev/zero > big")
    assert r["output"].split()[0] == str(8 * 1024) and "File too large" in r["output"]       # KB
    assert (proj / "big").stat().st_size == 8 * MB                                          # stopped at 8 MB exactly
    _empty(proj)


@needs_cage
def test_c688_the_project_cannot_grow_past_its_budget(cfg, proj, monkeypatch):
    # 100 processes × 10 MB at once on a budget of 20 MB: stopped by the guard (statvfs every 2 ms, then measured)
    run = B.profile("run")
    monkeypatch.setattr(B, "profile", lambda kind, readonly=False: {**run, "disk_mb": 20})
    t0 = time.time()
    r = prj_run.run(cfg, "demo", FLOOD)
    grown = B.disk_bytes(proj) / MB
    assert r["exit"] == B.DISK_STOP and "the project grew by" in r["output"], r
    assert grown < 400 and time.time() - t0 < 10                     # before: all of 1,000 MB, and the sleep's 30 s
    _empty(proj)


@needs_cage
def test_c688_the_fallback_limits_memory_and_processes_and_dev_is_read_only(cfg, proj):
    # no delegated cgroup here (outside a service): the address space (run's profile), ulimit -u in the cage's own
    # user namespace; /dev read only, /dev/shm a tmpfs of 64 MB (O1: before, /dev was writable, half the memory)
    r = prj_run.run(cfg, "demo", "ulimit -v; ulimit -u; echo x > /dev/planted 2>/dev/null || echo dev-ro; "
                                 "df -k /dev/shm | tail -1; head -c 100000000 /dev/zero > /dev/shm/x 2>/dev/null; "
                                 "du -k /dev/shm/x; echo y > /dev/null && echo null-ok; "
                                 "python3 -c 'import resource; print(resource.getrlimit(resource.RLIMIT_CORE))'")
    out = r["output"].split("\n")
    assert out[0] == str(B.profile("run")["mem_mb"] * 1024) and out[1] == "512" and out[2] == "dev-ro"
    assert out[3].split()[1] == str(64 * 1024) and int(out[4].split()[0]) <= 64 * 1024
    assert "null-ok" in out and "(1, 1)" in out


@needs_cage
def test_c688_the_timeout_ends_the_script_and_the_cage_together(cfg, proj):
    cfg.values["AURORA_PROJECT_RUN_S"] = 5
    token = "c688-timeout-" + os.urandom(4).hex()
    t0 = time.time()
    r = prj_run.run(cfg, "demo", f"(exec -a {token} sleep 60) & exec -a {token} sleep 60")
    assert r["exit"] == -1 and "STOPPED after 5 s" in r["output"] and time.time() - t0 < 15
    time.sleep(0.5)
    left = []
    for d in os.listdir("/proc"):
        try:
            if d.isdigit() and token.encode() in Path(f"/proc/{d}/cmdline").read_bytes():
                left.append(d)
        except OSError:
            pass
    assert left == []


def test_c688_profiles_the_terminal_generous_the_referee_without_address_space():
    user, ro, run = B.profile("user"), B.profile("run", readonly=True), B.profile("run")
    assert user["mem_mb"] >= run["mem_mb"] and user["tasks"] > run["tasks"] and user["file_mb"] > run["file_mb"]
    assert not user["as"] and not ro["as"] and run["as"]         # Lean, the referee, the GPU map far more than they use
    assert not ro["watch"] and ro["disk_mb"] == 0 and user["watch"] and user["disk_mb"] == 0   # the floor only
    args = prj_run.cage(None, Path("/nonexistent-c688"), "true", git_writable=True)
    conf = json.loads(args[3])
    assert args[2].endswith("prj_run_box.py") and conf["mem_mb"] == user["mem_mb"] and conf["tasks"] == 1024
    assert args[-4:-1] == ["--", "bash", "-c"] and "--remount-ro" in args


class _Fs:
    """os.statvfs's result, with the free space the test says."""
    def __init__(self, free_mb, size_mb=100_000, files=1_000_000, ffree=500_000):
        self.f_frsize, self.f_blocks, self.f_bavail = MB, size_mb, free_mb
        self.f_files, self.f_favail = files, ffree


def test_c688_guard_floor_budget_and_others_writes(monkeypatch):
    fs = {"v": _Fs(50_000)}
    monkeypatch.setattr(B.os, "statvfs", lambda p: fs["v"])
    monkeypatch.setattr(B, "CONFIRM_S", 0.0)
    used = {"v": 0}
    g = B.Guard("/x", 100, measure=lambda: used["v"], base=0)
    assert g.floor == 2000 * MB                                     # 2 % of 100 GB
    fs["v"] = _Fs(49_950)
    assert g.check() == ""                                          # 50 MB fewer free: under the budget, not measured
    fs["v"] = _Fs(49_000)                                           # 1 GB fewer free, the project grew by 10 MB only:
    used["v"] = 10 * MB                                             # someone else wrote — measured, not stopped
    assert g.check() == "" and g.left == 90 * MB and g.ref == 49_000 * MB
    fs["v"] = _Fs(48_950)
    used["v"] = 60 * MB
    assert g.check() == ""                                          # 50 MB more since the measure, 90 left
    fs["v"] = _Fs(48_800)
    used["v"] = 160 * MB
    assert "grew by 160.0 MB > 100 MB" in g.check()
    fs["v"] = _Fs(1500)
    assert "under the floor" in B.Guard.check(g)
    fs["v"] = _Fs(40_000, ffree=1000)
    assert "inodes" in g.check()
    fs["v"] = _Fs(300)                                              # a machine almost full at the start: half of what
    assert B.Guard("/x").floor == 150 * MB                          # is free, never all of it


# ---- C688: a long run ----------------------------------------------------------------------------------------------
@needs_cage
def test_c688_a_long_run_stops_near_its_disk_not_at_the_next_look(cfg, proj, monkeypatch):
    # before: 953.9 MB written on disk_mb 10 before the stop, 15.9 s (the size measured every 15 s)
    monkeypatch.setattr(R, "DISK_EVERY_S", 15.0)
    st = R.start(cfg, "demo", FLOOD, R.limits(cfg, {"wall_s": 120, "mem_mb": 2048, "disk_mb": 10}), "flood",
                 code_files=[])
    peak, t0 = 0, time.time()
    while not R.load(cfg, "demo", st["id"]).get("finished") and time.time() - t0 < 60:
        try:
            peak = max(peak, B.disk_bytes(proj))
        except B.Unmeasurable:
            pass
        time.sleep(0.05)
    st = wait(cfg, st["id"])
    assert st["status"] == "stopped" and "the project grew by" in st["why"], st
    assert peak / MB < 400 and time.time() - t0 < 10, (peak / MB, st)
    _empty(proj)


def test_c688_o6_code_files_are_capped(cfg, proj):
    for i in range(C.MAX_CODE_FILES + 1):
        (proj / f"m{i}.py").write_text("x = 1\n")
    with pytest.raises(ValueError, match="at most 64 code files"):
        C.code_state(proj, [f"m{i}.py" for i in range(C.MAX_CODE_FILES + 1)], "true")
    with open(proj / "huge.bin", "wb") as fh:                       # sparse: 65 MB that take no disk
        fh.truncate((C.MAX_CODE_MB + 1) * MB)
    with pytest.raises(ValueError, match="at most 64 MB"):
        C.code_state(proj, ["huge.bin"], "true")
    assert C.code_state(proj, ["m0.py"], "true")["code"]


# ---- C689: the outputs' patterns -------------------------------------------------------------------------------------
def test_c689_patterns_never_follow_a_link_nor_tell_what_is_outside(proj, tmp_path):
    outside = tmp_path / "host"
    (outside / "etc").mkdir(parents=True)
    for i in range(40):
        (outside / "etc" / f"f{i}.conf").write_text("secret")
    (proj / "rootlink").symlink_to(outside)
    (proj / "res").mkdir()
    (proj / "res" / "a.csv").write_text("1\n")
    (proj / "res" / "deep").mkdir()
    (proj / "res" / "deep" / "b.csv").write_text("2\n")
    (proj / "res" / "via").symlink_to(outside / "etc")
    st = {"outputs": R._patterns(["rootlink/etc/*.conf", "res/**/*.csv", "*/via/*", "**/*.conf"])}
    out, skipped = R.outputs(proj, st)
    assert sorted(out) == ["res/a.csv", "res/deep/b.csv"] and skipped == 0       # before: 0 hashed, 40 skipped
    assert st["outputs_refused"] == ["rootlink/etc/*.conf"]


def test_c689_a_deep_pattern_over_a_link_to_root_ends_at_once(proj):
    # before: 13 M matches in 20 s, finish() «finishing» for good
    (proj / "rootlink").symlink_to("/")
    st = {"outputs": R._patterns(["rootlink/sys/class/*/*/subsystem/*/subsystem/*/subsystem/*/uevent",
                                  "*/sys/class/*/*/subsystem/*/uevent", "**/**/**/**/**/uevent"])}
    t0 = time.time()
    out, skipped = R.outputs(proj, st)
    assert out == {} and skipped == 0 and time.time() - t0 < 2


def test_c689_the_walk_is_capped(proj, monkeypatch):
    (proj / "many").mkdir()
    for i in range(300):
        (proj / "many" / f"f{i}.txt").write_text("x")
    files, refused, capped = C.match_outputs(proj, ["many/*.txt"], cap=100)
    assert capped and len(files) <= 100 and not refused


def test_c689_finish_never_holds_the_lock_while_it_hashes(cfg, proj, monkeypatch):
    # sweep finished a run inside its lock: a slow finish held start() and every other sweep
    st = {"id": "001", "project": "demo", "title": "t", "command": "true", "limits": {"wall_s": 1, "gpu": False},
          "outputs": [], "status": "ended", "attempts": 1, "used_s": 0, "t": time.time(), "frozen": "", "exit": 0,
          "git_mark": [], "log": str(proj / "x.log")}
    R._save(cfg, "demo", st)
    entered, release = threading.Event(), threading.Event()

    def slow(root, s):
        entered.set()
        release.wait(10)
        return {}, 0
    monkeypatch.setattr(R, "outputs", slow)
    t = threading.Thread(target=R.sweep, args=(cfg, "demo"), daemon=True)
    t.start()
    assert entered.wait(10)
    got = R._lock.acquire(timeout=2)                                 # another thread takes the lock meanwhile
    assert got
    R._lock.release()
    release.set()
    t.join(10)
    assert R.load(cfg, "demo", "001").get("finished")


def test_c689_a_failing_finish_is_not_left_finishing(cfg, proj, monkeypatch):
    st = {"id": "002", "project": "demo", "title": "t", "command": "true", "limits": {"wall_s": 1, "gpu": False},
          "outputs": [], "status": "ended", "attempts": 1, "used_s": 0, "t": time.time(), "frozen": "", "exit": 0,
          "git_mark": [], "log": str(proj / "x.log")}
    R._save(cfg, "demo", st)
    monkeypatch.setattr(R, "outputs", lambda root, s: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        R.finish(cfg, "demo", "002")
    assert not R.load(cfg, "demo", "002").get("finishing")


# ---- C691: the set-aside's name ------------------------------------------------------------------------------------
@needs_cage
def test_c691_a_set_aside_name_planted_ahead_does_not_keep_the_git(cfg, proj):
    cmd = ('now=$(date +%s); for t in $(seq $now $((now+60))); do mkdir -p .git.set-aside-$t/keep; done; '
           'mkdir -p .git/hooks && echo planted')
    r = prj_run.run(cfg, "demo", cmd)
    assert "set aside as .git.set-aside-" in r["output"], r
    assert not (proj / ".git").exists() and prj_run.git_mark(proj) is None    # before: the .git stayed
    moved = [x for x in proj.iterdir() if x.name.startswith(".git.set-aside-") and (x / "hooks").is_dir()]
    assert len(moved) == 1 and len(moved[0].name.split("-")[-1]) == 16      # 64 random bits after the time


def test_c691_the_rename_never_replaces_what_is_there(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "dst").mkdir()                                         # empty: a plain rename(2) would replace it
    with pytest.raises(FileExistsError):
        prj_run._rename_new(tmp_path / "src", tmp_path / "dst")
    assert (tmp_path / "src").is_dir()
    prj_run._rename_new(tmp_path / "src", tmp_path / "new")
    assert (tmp_path / "new").is_dir() and not (tmp_path / "src").exists()


# ---- C688: a cgroup of the cage's own (a transient user service with its cgroup delegated) -----------------------
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
def test_c688_a_cgroup_of_the_cage_s_own_holds_memory_processes_and_disk(tmp_path):
    out = subprocess.run(["systemd-run", "--user", "--wait", "--pipe", "--quiet", "-p", "Delegate=yes",
                          f"--working-directory={tmp_path}", "-E", f"PYTHONPATH={CORE}", "--",
                          sys.executable, str(HERE), "probe", str(tmp_path)],
                         capture_output=True, text=True, timeout=180)
    line = [x for x in out.stdout.splitlines() if x.startswith("{")]
    assert line, out.stdout + out.stderr
    r = json.loads(line[-1])
    assert r["base"] and r["live_cgroups"] == 1 and r["memory_max"] == 64 * MB and r["pids_max"] == 24
    assert r["mem_rc"] != 0 and "memory limit" in r["mem_out"]          # 400 MB in a cage of 64 MB: the kernel ends it
    assert r["forks_ok"] < 30 and r["fork_refused"]
    assert r["raise_rc"] != 0                                          # the cage cannot raise its own limit
    assert r["disk_rc"] == B.DISK_STOP and r["disk_peak_mb"] < 400
    assert r["left_after"] == 0                                        # every cage's cgroup removed


def _probe(tmp: Path) -> dict:
    base = None
    from aurora import prj_longrun_meter as M
    base = M.delegated()
    r = {"base": str(base or "")}
    box = {**B.profile("run"), "mem_mb": 64, "tasks": 24}
    p = subprocess.Popen(prj_run.cage(None, tmp, "sleep 1", box=box), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.5)
    live = list(base.glob(B.PREFIX + "*")) if base else []
    r["live_cgroups"] = len(live)
    r["memory_max"] = int((live[0] / "memory.max").read_text()) if live else 0
    r["pids_max"] = int((live[0] / "pids.max").read_text()) if live else 0
    p.wait()
    m = subprocess.run(prj_run.cage(None, tmp, "python3 -c 'b = bytearray(400 * 1024 * 1024); print(len(b))'",
                                    box=box), capture_output=True, text=True)
    r.update(mem_rc=m.returncode, mem_out=m.stderr[-300:])
    forks = ("import os, time\nn = 0\ntry:\n    for _ in range(30):\n        if os.fork() == 0:\n"
             "            time.sleep(3); os._exit(0)\n        n += 1\nexcept OSError as e:\n    print('refused', e)\n"
             "print('forks=%d' % n)\n")
    (tmp / "forks.py").write_text(forks, encoding="utf-8")
    f = subprocess.run(prj_run.cage(None, tmp, "python3 forks.py", box={**box, "tasks": 24}), capture_output=True,
                       text=True)
    r["forks_ok"] = int(([x.split("=")[1] for x in f.stdout.split() if x.startswith("forks=")] or ["99"])[0])
    r["fork_refused"] = "refused" in f.stdout
    x = subprocess.run(prj_run.cage(None, tmp, "for f in /sys/fs/cgroup/memory.max /sys/fs/cgroup/*/memory.max; do "
                                    "echo max > $f && exit 0; done; exit 1", box=box), capture_output=True)
    r["raise_rc"] = x.returncode
    d = subprocess.Popen(prj_run.cage(None, tmp, FLOOD, box={**box, "mem_mb": 2048, "tasks": 512, "disk_mb": 10}),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    peak = 0
    while d.poll() is None:
        try:
            peak = max(peak, B.disk_bytes(tmp))
        except B.Unmeasurable:
            pass
        time.sleep(0.02)
    r.update(disk_rc=d.returncode, disk_peak_mb=round(peak / MB, 1))
    _empty(tmp)
    r["left_after"] = len(list(base.glob(B.PREFIX + "*"))) if base else -1
    return r


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "probe":
    os.environ.setdefault("AURORA_ENV_FILE", "/nonexistent")
    print(json.dumps(_probe(Path(sys.argv[2]))), flush=True)
    os._exit(0)
