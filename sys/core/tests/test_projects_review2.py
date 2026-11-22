# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ The second independent review of N145 / N146 / C615 / N147 (20 Nov 2026): every attack it reproduced, kept as a
test (C625–C640). Invented projects in tmp_path; the caged ones need bwrap."""
import io
import json
import resource
import shutil
import subprocess
import sys
import time
import types
import zipfile

import numpy as np
import pytest

from aurora import prj_act as A
from aurora import prj_discover as D
from aurora import prj_longrun as R
from aurora import prj_longrun_cage as C
from aurora import prj_novelty as N
from aurora import prj_policy, prj_prereg as P, prj_provenance as V, prj_run, sys_fresh
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
LIM = {"wall_s": 30, "mem_mb": 2048, "disk_mb": 50}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(R, "POLL_S", 0.1)
    monkeypatch.setattr(R, "DISK_EVERY_S", 0.2)
    monkeypatch.setattr(R, "SAVE_EVERY_S", 0.2)


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "lungo"
    p.mkdir(parents=True)
    (p / "sim.sh").write_text("echo v1 > out.txt\n")
    return p


def wait(cfg, rid, s=40.0):
    end = time.time() + s
    while time.time() < end:
        st = R.load(cfg, "lungo", rid)
        if st.get("finished"):
            return st
        time.sleep(0.1)
    raise AssertionError(R.load(cfg, "lungo", rid))


# ---- N145 ----------------------------------------------------------------------------------------------------------
@needs_cage
def test_c625_a_manifest_link_never_overwrites_aurora_s_ledger(cfg, proj):
    shadow = P._shadow(cfg, "lungo")
    before = shadow.read_text() if shadow.exists() else ""
    cmd = f'ln -s {shadow} "$LONGRUN_CHECKPOINT/MANIFEST.txt"; f=$(printf "x\\nFORGED"); : > "$f"; echo ok > o.txt'
    st = wait(cfg, R.start(cfg, "lungo", cmd, R.limits(cfg, LIM), "probe", code_files=["sim.sh"])["id"])
    assert "FORGED" not in shadow.read_text() and shadow.read_text().startswith(before)
    assert st["manifest"].startswith("longrun/") and (proj / st["manifest"]).is_file()
    man = (proj / st["manifest"]).read_text()
    assert "FORGED" not in man and "names skipped" in man       # the name with a line break is never written
    assert [e["status"] for e in P.entries(cfg, "lungo")] == ["closed"]


@needs_cage
def test_c625_a_progress_link_reads_nothing_outside(cfg, proj, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN=abc123")
    st = R.start(cfg, "lungo", f'ln -s {secret} "$LONGRUN_CHECKPOINT/PROGRESS"', R.limits(cfg, LIM),
                 code_files=["sim.sh"])
    wait(cfg, st["id"])
    assert R.status(cfg, "lungo", st["id"])["progress"] == ""


@needs_cage
def test_c626_cpu_is_the_whole_run_s(cfg, proj):
    cmd = "for i in 1 2 3 4; do ( while :; do :; done ) & done; wait"
    st = wait(cfg, R.start(cfg, "lungo", cmd, R.limits(cfg, {**LIM, "cpu_s": 2}), code_files=["sim.sh"])["id"])
    assert st["status"] == "stopped" and "whole run" in st["why"]
    assert st["cpu_used_s"] < 2 + 4 * 1.5                       # four processes, a poll of 0.1 s: never 4 × 2 s


@needs_cage
def test_c626_processes_are_bounded(cfg, proj):
    (proj / "fork.py").write_text("import os, time\nn = 0\ntry:\n    for _ in range(2000):\n        if os.fork() == 0:\n"
                                  "            time.sleep(3)\n            os._exit(0)\n        n += 1\n"
                                  "except OSError:\n    open('forks.txt', 'w').write(str(n))\n")
    wait(cfg, R.start(cfg, "lungo", "python fork.py", R.limits(cfg, LIM), code_files=["sim.sh", "fork.py"])["id"])
    assert int((proj / "forks.txt").read_text()) < C.TASKS_MAX       # ulimit -u in the run's user namespace


@needs_cage
def test_c626_the_cage_s_tmp_is_the_memory_declared(cfg, proj):
    cmd = "head -c 60000000 /dev/zero > /tmp/x; echo $? > tmp.txt"
    st = wait(cfg, R.start(cfg, "lungo", cmd, R.limits(cfg, {**LIM, "mem_mb": 50}), code_files=["sim.sh"])["id"])
    if st.get("meter") == "cgroup":                    # C654: with a cgroup of its own /tmp is in its memory.max
        assert st["status"] == "stopped" and "memory" in st["why"]
    else:
        assert (proj / "tmp.txt").read_text().strip() != "0"


@needs_cage
def test_c627_the_disk_sees_every_folder(cfg, proj):
    cmd = "mkdir -p node_modules; for i in 1 2 3; do head -c 800000 /dev/zero > node_modules/b$i; done; sleep 10"
    st = wait(cfg, R.start(cfg, "lungo", cmd, R.limits(cfg, {**LIM, "disk_mb": 1}), code_files=["sim.sh"])["id"])
    assert st["status"] == "stopped" and "grew" in st["why"]


def test_c630_the_agent_cannot_close_a_long_run_s_entry(cfg, proj, monkeypatch):
    monkeypatch.setattr(R, "launch", lambda *a, **k: None)
    st = R.start(cfg, "lungo", "false", R.limits(cfg, LIM), code_files=["sim.sh"])
    out = P.tool(cfg, "lungo", "close_predictions", {"id": st["frozen"], "outcomes": [
        {"id": "R1", "outcome": "passed", "value": "ok"}], "evidence": "sim.sh"})
    assert out.startswith("REFUSED") and "longrun" in out
    assert P.tool(cfg, "lungo", "freeze_predictions", {"title": "Long run 9: mine", "code_files": ["sim.sh"],
                                                       "predictions": [{"id": "R1", "text": "x"}]}).startswith("REFUSED")


def test_c628_a_resume_never_runs_changed_code(cfg, proj, monkeypatch):
    launched = []
    monkeypatch.setattr(R, "launch", lambda *a, **k: launched.append(a))
    rid = R.start(cfg, "lungo", "bash sim.sh", R.limits(cfg, LIM), code_files=["sim.sh"])["id"]
    R._update(cfg, "lungo", rid, status="running", attempts=1, used_s=1.0, t=time.time() - 3600)
    launched.clear()
    (proj / "sim.sh").write_text("echo CHANGED > out.txt\n")
    R.sweep(cfg, "lungo")
    st = R.load(cfg, "lungo", rid)
    assert not launched and st["status"] == "interrupted" and "sim.sh" in st["why"]


def test_c628_code_files_are_required_with_frozen_predictions(cfg, proj):
    with pytest.raises(ValueError, match="code_files"):
        R.start(cfg, "lungo", "true", R.limits(cfg, LIM))


def test_c629_a_traversing_project_name_touches_nothing(cfg, proj, monkeypatch):
    monkeypatch.setattr(R, "launch", lambda *a, **k: None)
    rid = R.start(cfg, "lungo", "sleep 100", R.limits(cfg, LIM), code_files=["sim.sh"])["id"]
    R._update(cfg, "lungo", rid, status="running")
    out = R.act(cfg, "lungo/../lungo", {"action": "stop", "run": rid})
    assert out.startswith("REFUSED") and not R.load(cfg, "lungo", rid).get("stop")


def test_c626_gpu_runs_move_the_reasoner_and_have_no_address_limit(cfg, proj, monkeypatch):
    from contextlib import contextmanager

    from aurora import mdl_image
    calls = []

    @contextmanager
    def lock(*a, **k):
        calls.append("lock")
        yield
    monkeypatch.setattr(mdl_image, "gpu_lock", lock)
    monkeypatch.setattr(mdl_image, "reasoner_out", lambda cfg: calls.append("out"))
    monkeypatch.setattr(mdl_image, "reasoner_back", lambda cfg, s: calls.append("back"))
    monkeypatch.setattr(R, "_attempt", lambda *a: calls.append("run"))
    monkeypatch.setattr(R, "launch", lambda *a, **k: None)
    monkeypatch.setattr(R, "gpu_holder", lambda cfg: "")
    rid = R.start(cfg, "lungo", "true", R.limits(cfg, {**LIM, "gpu": True}), code_files=["sim.sh"])["id"]
    R.supervise(cfg, "lungo", rid)
    assert calls[:4] == ["lock", "out", "run", "back"]
    assert "ulimit -v" not in C.wrapped(R.load(cfg, "lungo", rid))
    assert "ulimit -v" in C.wrapped({**R.load(cfg, "lungo", rid), "limits": R.limits(cfg, LIM)})


def test_c631_the_morning_restart_waits_for_a_long_run(cfg, monkeypatch):
    monkeypatch.setattr(R, "any_alive", lambda: 1)
    from aurora import sys_ethics, sys_health
    monkeypatch.setattr(sys_ethics, "integrity", lambda: (True, ""))
    monkeypatch.setattr(sys_health, "gpu_job", lambda cfg: "")
    monkeypatch.setattr(sys_fresh, "_slots_busy", lambda cfg: False)
    assert "long run" in (sys_fresh.why_not(cfg, [], False) or "")


def test_c631_a_sweep_never_launches_a_run_its_starter_is_launching(cfg, proj, monkeypatch):
    launched = []
    monkeypatch.setattr(R, "launch", lambda *a, **k: launched.append(a))
    rid = R.start(cfg, "lungo", "true", R.limits(cfg, LIM), code_files=["sim.sh"])["id"]
    launched.clear()
    assert R.load(cfg, "lungo", rid)["status"] == "starting"
    R.sweep(cfg, "lungo")
    assert not launched


# ---- N146 ----------------------------------------------------------------------------------------------------------
def _down(monkeypatch):
    from aurora import kno_web
    monkeypatch.setattr(kno_web, "search", lambda q, n: [])
    # C722: the novelty check asks search_why (results and each engine's failure): the network down, said so
    monkeypatch.setattr(kno_web, "search_why", lambda q, n: ([], ["auto: network (ConnectError: unreachable)"]))


def test_c634_network_down_is_never_not_found(cfg, monkeypatch):
    _down(monkeypatch)

    def down(url, **params):
        raise ConnectionError("network unreachable")
    r = N.check(cfg, "The mean number of cycles of a xor multiplication permutation grows quadratically",
                get=down, record=False)
    assert r["status"] == "not_checked" and "web" in r["failed"]


def test_c635_an_italian_claim_needs_english_keywords_and_scores_on_them(cfg):
    rec = {"title": "The number of cycles of xor multiplication permutations grows quadratically", "text": "",
           "url": "u", "year": "2024", "authors": []}
    src = {"arxiv": lambda q, n, get: [rec]}
    claim = "Il numero medio di cicli di una permutazione di moltiplicazione xor cresce quadraticamente"
    assert N.check(cfg, claim, sources=src, get=lambda *a, **k: None, record=False)["status"] == "refused"
    r = N.check(cfg, claim, keywords=["xor multiplication permutation cycles"], sources=src,
                get=lambda *a, **k: None, record=False)
    assert r["status"] == "found"


def test_c637_arxiv_falls_back_to_any_word(cfg):
    empty = "<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
    one = ("<feed xmlns='http://www.w3.org/2005/Atom'><entry><id>http://arxiv.org/abs/1</id><title>Xor cycles</title>"
           "<published>2020-01-01</published><summary>s</summary></entry></feed>")
    seen = []

    def get(url, **p):
        seen.append(p["search_query"])
        return types.SimpleNamespace(text=one if " OR " in p["search_query"] else empty)
    out = N.arxiv("xor cycles permutation", 5, get)
    assert len(out) == 1 and " AND " in seen[0] and " OR " in seen[1]


def test_c636_a_riservato_project_sends_no_query(cfg, proj):
    prj_policy.save(cfg, "lungo", {"riservato": True})
    sent = []
    r = N.check(cfg, "The mean number of cycles of a xor multiplication permutation grows", project="lungo",
                get=lambda *a, **k: sent.append(a), sources={"arxiv": lambda q, n, get: get(q)}, record=False)
    assert r["status"] == "not_checked" and not sent and "riservato" in r["errors"][0]


def test_c638_novelty_reports_never_overwrite(cfg, proj):
    (proj / "novelty").mkdir()
    (proj / "novelty" / "002_x.json").write_text("{}")
    rec = {"title": "Xor multiplication permutation cycles grow", "text": "", "url": "u", "year": "", "authors": []}
    r = N.check(cfg, "xor multiplication permutation cycles grow fast", project="lungo",
                sources={"s": lambda q, n, get: [rec]}, get=lambda *a, **k: None)
    assert r["report"].startswith("novelty/003_") and (proj / "novelty" / "002_x.json").read_text() == "{}"


# ---- C615 ----------------------------------------------------------------------------------------------------------
def test_c629_no_write_tool_reaches_venv(cfg, proj):
    run = A.Run(cfg, "lungo", Pseudonymizer(cfg), "goal")
    run.tools = A.TOOLS
    with pytest.raises(ValueError, match="not writable"):
        A._do(run, "write_file", {"path": ".venv/lib/python3/site-packages/zz.pth", "content": "import os"})
    assert not (proj / ".venv" / "lib").exists()
    agent = types.SimpleNamespace(cfg=cfg, local_only=False)
    out = prj_policy.guard(agent, "projects", "project_write_file", {"name": "lungo", "path": ".venv/x.pth"},
                           lambda *a: None)
    assert out.startswith("REFUSED")


def test_c629_a_linked_venv_or_locked_folder_refuses_the_cage(cfg, proj, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (proj / ".venv").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match=".venv"):
        prj_run.cage(cfg, proj, "true")
    (proj / ".venv").unlink()
    (proj / "prereg").write_text("not a folder")
    with pytest.raises(ValueError, match="prereg"):
        prj_run.cage(cfg, proj, "true")
    assert not prj_run.trusted_venv(proj)


# ---- N147 ----------------------------------------------------------------------------------------------------------
def _table(path, x, y):
    cols = [f"x{i}" for i in range(x.shape[1])] + ["y"]
    path.write_text(",".join(cols) + "\n" + "\n".join(",".join(f"{v:.6g}" for v in row)
                                                       for row in np.column_stack([x, y])) + "\n")


def test_c640_a_trailing_newline_is_the_same_table(cfg, proj):
    cfg.values["AURORA_PREREG_MODE"] = "off"
    g = np.random.default_rng(1)
    _table(proj / "t.csv", g.uniform(1, 2, (200, 2)), g.normal(size=200))
    a = D.discover(cfg, "lungo", "t.csv", "y", runner=D.direct)
    (proj / "t.csv").write_text((proj / "t.csv").read_text() + "\n")
    b = D.discover(cfg, "lungo", "t.csv", "y", runner=D.direct)
    assert a["status"] != "refused" and b["status"] == "refused" and "used already" in b["errors"][0]


def test_c640_a_target_tried_again_on_an_agent_s_table_is_not_claimable(cfg, proj):
    g = np.random.default_rng(2)
    x = g.uniform(1, 3, (300, 1))
    _table(proj / "a.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))
    _table(proj / "b.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))
    V.record(cfg, "lungo", proj, ["b.csv"], "write")             # b.csv: the agent's
    D.discover(cfg, "lungo", "a.csv", "y", runner=D.direct)
    r = D.discover(cfg, "lungo", "b.csv", "y", runner=D.direct)
    assert r["attempt"] == 2 and r["status"] != "discovered"


def test_c647_new_data_the_owner_brings_stay_claimable_on_a_target_tried_before(cfg, proj):
    g = np.random.default_rng(2)
    x = g.uniform(1, 3, (300, 1))
    _table(proj / "a.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))
    _table(proj / "b.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))   # the owner's, no agent wrote it
    V.record_owner(cfg, "lungo", proj, ["b.csv"], "upload")    # C697: brought in as the owner's (positive provenance)
    D.discover(cfg, "lungo", "a.csv", "y", runner=D.direct)
    r = D.discover(cfg, "lungo", "b.csv", "y", runner=D.direct)
    assert r["attempt"] == 2 and r["status"] == "discovered"


def test_c646_a_renamed_target_and_refusals_do_not_reset_the_count(cfg, proj):
    g = np.random.default_rng(3)
    x = g.uniform(1, 3, (300, 1))
    _table(proj / "a.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))
    D.discover(cfg, "lungo", "a.csv", "y", runner=D.direct)
    for _ in range(60):                                           # refusals: never counted, never pushing it out
        D.discover(cfg, "lungo", "missing.csv", "y", runner=D.direct)
    (proj / "b.csv").write_text((proj / "a.csv").read_text().replace("x0,y", "x0,Y", 1))
    V.record(cfg, "lungo", proj, ["b.csv"], "write")
    r = D.discover(cfg, "lungo", "b.csv", "Y", runner=D.direct)
    assert r["status"] in ("refused", "error") or (r["attempt"] == 2 and r["status"] != "discovered")
    assert D.target_key("Ｙ") == D.target_key("y")


@needs_cage
def test_c632_a_table_made_by_a_command_and_dated_back_is_never_claimable(cfg, proj):
    code = ("import numpy as np, os\ng=np.random.default_rng(5)\nx=g.uniform(1,3,300)\ny=x**1.5*(1+0.01*g.normal(size=300))\n"
            "open('made.csv','w').write('x,y\\n'+''.join(f'{a:.6g},{b:.6g}\\n' for a,b in zip(x,y)))\n"
            "os.utime('made.csv',(1,1))\n")
    (proj / "mk.py").write_text(code)
    assert prj_run.run(cfg, "lungo", "python mk.py")["exit"] == 0
    r = D.discover(cfg, "lungo", "made.csv", "y", runner=D.direct)
    assert r["status"] != "discovered" and any("written by Aurora's agent" in c for c in r["caveats"])


def test_c632_a_write_tool_s_table_is_never_claimable_and_a_frozen_run_s_is(cfg, proj):
    g = np.random.default_rng(7)
    x = g.uniform(1, 3, (300, 1))
    _table(proj / "w.csv", x, x[:, 0] ** 1.5 * (1 + 0.01 * g.normal(size=300)))
    agent = types.SimpleNamespace(cfg=cfg, local_only=False)
    prj_policy.guard(agent, "projects", "project_write_file", {"name": "lungo", "path": "w.csv"}, lambda *a: None)
    assert V.verdict(cfg, "lungo", "w.csv", "x")[0] is False
    V.record(cfg, "lungo", proj, ["w.csv"], "longrun", run="001", frozen="003", intact=True)
    ok, how = V.verdict(cfg, "lungo", "w.csv", D.table(proj, "w.csv", "y", None)["sha256"])
    assert ok and "frozen long run 001" in how


def test_c639_an_npz_with_another_member_is_refused_unread(proj):
    p = proj / "bomb.npz"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        buf = io.BytesIO()
        np.save(buf, np.arange(30.0))
        z.writestr("y.npy", buf.getvalue())
        z.writestr("x.npy", buf.getvalue())
        z.writestr("junk", b"\0" * 50_000_000)
    r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    with pytest.raises(ValueError, match="only"):
        D.load(p.read_bytes(), ".npz")
    assert (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - r0) / 1024 < 40


def test_c639_a_csv_is_read_by_the_c_reader(proj, monkeypatch):
    monkeypatch.setattr(np, "genfromtxt", lambda *a, **k: (_ for _ in ()).throw(AssertionError("genfromtxt")))
    (proj / "c.csv").write_text("x,y\n1,2\n3,nan\n")
    assert D.load((proj / "c.csv").read_bytes(), ".csv")["y"].shape == (2,)


def test_c633_an_invisible_prefix_does_not_hide_a_reserved_title(cfg, proj):
    for title in ("\u200bDiscovered law for y", "\uff24\uff29\uff33\uff23\uff2f\uff36\uff25\uff32\uff25\uff24 law",
                  "long\u200d run 7"):
        assert P.reserved(title)
    out = P.tool(cfg, "lungo", "freeze_predictions", {"title": "\u200bDiscovered law for y", "code_files": ["sim.sh"],
                                                      "predictions": [{"id": "D1", "text": "x"}]})
    assert out.startswith("REFUSED")
