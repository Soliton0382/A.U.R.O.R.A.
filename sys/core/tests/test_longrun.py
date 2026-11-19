# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ Long runs (prj_longrun, N145): the limits are declared first and the machine's ceilings hold; a short run in the
cage ends, its outputs hashed into the frozen predictions' ledger; the wall time, the disk and the CPU stop a run that
passes them; a run left «running» by a restart is resumed with LONGRUN_RESUMED=1 and continues from its checkpoint;
another GPU job refuses a GPU run (law 6); the referee may only look. Invented projects in tmp_path; the cage needs
bwrap."""
import json
import shutil
import subprocess
import time

import pytest

from aurora import prj_act as A
from aurora import prj_longrun as R
from aurora import prj_prereg as P
from aurora.sec_mask import Pseudonymizer


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    """N145-N147 are off by default while under review (C642): their own tests switch them on."""
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True



def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "lungo"
    p.mkdir(parents=True)
    (p / "sim.sh").write_text("echo simulating\n", encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "DISK_EVERY_S", 0.2)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


LIM = {"wall_s": 60, "mem_mb": 2048, "disk_mb": 50}


def wait(cfg, rid, project="lungo", s=30.0):
    end = time.time() + s
    while time.time() < end:
        st = R.load(cfg, project, rid)
        if st.get("finished"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"run {rid} did not finish: {R.load(cfg, project, rid)}")


def test_limits_declared_first_and_capped(cfg):
    with pytest.raises(ValueError, match="declare wall_s"):
        R.limits(cfg, {"mem_mb": 10, "disk_mb": 10})
    with pytest.raises(ValueError, match="declare disk_mb"):
        R.limits(cfg, {"wall_s": 10, "mem_mb": 10})
    with pytest.raises(ValueError, match="ceilings"):
        R.limits(cfg, {"wall_s": 13 * 3600, "mem_mb": 10, "disk_mb": 10})   # AURORA_LONGRUN_MAX_HOURS 12
    lim = R.limits(cfg, {"wall_s": 100, "mem_mb": 512, "disk_mb": 5})
    assert lim["cpu_s"] == 100 and lim["gpu"] is False


def test_bad_patterns_refused(cfg, proj):
    for bad in ("/etc/*", "../x", ".git/config"):
        with pytest.raises(ValueError):
            R.start(cfg, "lungo", "true", R.limits(cfg, LIM), outputs=[bad], code_files=["sim.sh"])


@needs_cage
def test_short_run_ends_and_outputs_are_hashed_into_the_ledger(cfg, proj):
    st = R.start(cfg, "lungo", 'mkdir -p out && echo 42 > out/a.txt && echo "half" > "$LONGRUN_CHECKPOINT/PROGRESS"',
                 R.limits(cfg, LIM), "invented sim", outputs=["out/*.txt"], code_files=["sim.sh"])
    assert st["frozen"] == "001"                           # frozen before it started (AURORA_PREREG_MODE warn)
    st = wait(cfg, st["id"])
    assert st["status"] == "ended" and st["exit"] == 0 and st["outputs_count"] == 1
    man = (proj / "longrun" / f"{st['id']}.MANIFEST.txt").read_text()   # C625: in the locked folder
    assert "out/a.txt" in man
    e = P.entries(cfg, "lungo")[0]
    assert e["status"] == "closed" and e["outcomes"][0]["outcome"] == "passed"
    assert st["manifest_sha256"] in e["outcomes"][0]["value"] and e["integrity"] == "intact"
    rep = json.loads((proj / "longrun" / f"{st['id']}.json").read_text())
    assert list(rep["outputs_sha256"]) == ["out/a.txt"]
    assert R.status(cfg, "lungo", st["id"])["progress"] == "half"
    assert P.locked("longrun/001.json")                   # Aurora's report: no write tool may touch it


@needs_cage
def test_wall_time_stops_the_run(cfg, proj):
    st = R.start(cfg, "lungo", "sleep 30", R.limits(cfg, {**LIM, "wall_s": 1}), code_files=["sim.sh"])
    st = wait(cfg, st["id"])
    assert st["status"] == "stopped" and "wall time" in st["why"]
    assert P.entries(cfg, "lungo")[0]["outcomes"][0]["outcome"] == "failed"


@needs_cage
def test_disk_limit_stops_the_run(cfg, proj):
    # three files under the per-file cap (ulimit -f: the disk declared), together over it: Aurora's measure stops it
    st = R.start(cfg, "lungo", "for i in 1 2 3; do head -c 800000 /dev/zero > big$i.bin; done; sleep 20",
                 R.limits(cfg, {**LIM, "disk_mb": 1}), code_files=["sim.sh"])
    st = wait(cfg, st["id"])
    assert st["status"] == "stopped" and "grew" in st["why"]


@needs_cage
def test_cpu_limit_stops_the_run(cfg, proj):
    st = R.start(cfg, "lungo", "while :; do :; done", R.limits(cfg, {**LIM, "cpu_s": 1}), code_files=["sim.sh"])
    st = wait(cfg, st["id"])
    assert st["status"] == "stopped" and "CPU" in st["why"]


@needs_cage
def test_stop_by_request(cfg, proj):
    st = R.start(cfg, "lungo", "sleep 30", R.limits(cfg, LIM), code_files=["sim.sh"])
    time.sleep(0.5)
    R.stop(cfg, "lungo", st["id"])
    st = wait(cfg, st["id"])
    assert st["status"] == "stopped" and st["why"] == "stopped by request"


@needs_cage
def test_a_run_cut_by_a_restart_is_resumed_from_its_checkpoint(cfg, proj, monkeypatch):
    cmd = ('c="$LONGRUN_CHECKPOINT/count"; n=$(cat "$c" 2>/dev/null || echo 0); echo $((n+1)) > "$c"; '
           'if [ "$LONGRUN_RESUMED" = 1 ]; then echo resumed > done.txt; exit 0; fi; sleep 30')
    launched = []
    monkeypatch.setattr(R, "launch", lambda *a, **k: launched.append(a))
    rid = R.start(cfg, "lungo", cmd, R.limits(cfg, LIM), outputs=["done.txt"], code_files=["sim.sh"])["id"]
    # as a dead API leaves it: one attempt made (its checkpoint written), the state «running», nobody watching
    (proj / "checkpoints" / rid / "count").write_text("1\n")
    R._update(cfg, "lungo", rid, status="running", attempts=1, used_s=12.0)
    monkeypatch.undo()
    assert rid in R.sweep(cfg, "lungo")
    st = wait(cfg, rid)
    assert st["status"] == "ended" and st["attempts"] == 2 and st["used_s"] >= 12.0
    assert (proj / "checkpoints" / rid / "count").read_text().strip() == "2"
    assert (proj / "done.txt").read_text().strip() == "resumed"


def test_no_resume_when_off_says_interrupted(cfg, proj):
    cfg.values["AURORA_LONGRUN_RESUME"] = False
    cfg.values["AURORA_PREREG_MODE"] = "off"
    st = {"id": "001", "project": "lungo", "title": "x", "command": "true", "limits": R.limits(cfg, LIM),
          "outputs": [], "status": "running", "attempts": 1, "used_s": 5.0, "created": "", "t": time.time(),
          "frozen": "", "exit": None, "why": "", "log": str(R._dir(cfg, "lungo") / "001.log")}
    R._save(cfg, "lungo", st)
    R.sweep(cfg, "lungo")
    st = R.load(cfg, "lungo", "001")
    assert st["status"] == "interrupted" and st["finished"]


def test_gpu_run_refused_when_another_gpu_job_holds_the_lock(cfg, proj, monkeypatch):
    monkeypatch.setattr(R, "gpu_holder", lambda cfg: "a painting")
    with pytest.raises(RuntimeError, match="GPU is busy"):
        R.start(cfg, "lungo", "true", R.limits(cfg, {**LIM, "gpu": True}), code_files=["sim.sh"])
    assert R.runs(cfg, "lungo") == []                     # nothing frozen, nothing started


def test_one_active_run_per_user(cfg, proj, monkeypatch):
    monkeypatch.setattr(R, "launch", lambda *a, **k: None)
    R.start(cfg, "lungo", "sleep 1", R.limits(cfg, LIM), code_files=["sim.sh"])
    with pytest.raises(RuntimeError, match="AURORA_LONGRUN_MAX_ACTIVE"):
        R.start(cfg, "lungo", "sleep 1", R.limits(cfg, LIM), code_files=["sim.sh"])


def test_off_says_so(cfg, proj):
    cfg.values["AURORA_LONGRUN_ENABLED"] = False
    assert "AURORA_LONGRUN_ENABLED" in R.act(cfg, "lungo", {"action": "start", "command": "true", **LIM})
    assert not R.rule(cfg) and R.offered(cfg, "freeze_predictions") == []


def test_tool_is_the_conductors_and_the_referee_may_only_look(cfg, proj):
    assert R.NAME in {t["name"] for t in A.TOOLS}
    run = A.Run(cfg, "lungo", Pseudonymizer(cfg), "goal")
    run.readonly = True
    run.tools = A.TOOLS
    out = A._do(run, R.NAME, {"action": "start", "command": "true", **LIM})
    assert out.startswith("REFUSED") and "read-only" in out
    assert "(no long runs)" in A._do(run, R.NAME, {"action": "list"})
    from aurora import prj_referee
    assert R.NAME in {t["name"] for t in prj_referee.TOOLS}
