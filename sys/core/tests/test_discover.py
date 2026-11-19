# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The discovery engine (prj_discover, N147): known laws are found again from invented noisy tables (Kepler's third
law, free fall, an exponential decay, the pendulum, two variables at once) and predict the held-out rows; pure noise
gives «nothing found»; the split is frozen before the search and the chosen law before the held-out rows are touched;
the search never receives a held-out row; the tool is the conductor's and the agent's, never in a read-only run; a
table outside the project or a text formula is refused. Invented tables in tmp_path; the caged run needs bwrap."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import prj_act as A
from aurora import prj_discover as D
from aurora import prj_discover_search as S
from aurora import prj_prereg as P
from aurora.sec_mask import Pseudonymizer


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    """N145-N147 are off by default while under review (C642): their own tests switch them on."""
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True
    global CFG
    CFG = cfg


CFG = None


def owners(proj, rel: str) -> str:
    """C697/C698: the invented table brought in as the owner's (the page's upload: prj_provenance.record_owner) —
    since the provenance is positive, a table nobody vouched for is never DISCOVERED."""
    from aurora import prj_provenance
    prj_provenance.record_owner(CFG, proj.name, proj, [rel], "upload", "test")
    return rel



def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "leggi"
    (p / "dati").mkdir(parents=True)
    return p


def csv(proj, name, cols: dict) -> str:
    keys = list(cols)
    rows = zip(*(cols[k] for k in keys))
    (proj / "dati" / name).write_text(",".join(keys) + "\n" + "".join(",".join(f"{v:.10g}" for v in r) + "\n"
                                                                      for r in rows), encoding="utf-8")
    return owners(proj, f"dati/{name}")


R = np.random.default_rng(11)


@pytest.fixture(autouse=True)
def _same_numbers():
    """Every test draws the same invented rows whatever runs before it (a true law fails D1 a few times in a hundred:
    measured, docs/MEASUREMENTS)."""
    global R
    R = np.random.default_rng(11)


def kepler(n=80):
    a = R.uniform(0.3, 30, n)
    return {"a": a, "T": a ** 1.5 * (1 + R.normal(0, 0.01, n))}


LAWS = {
    "kepler": (kepler, "T", ["a"], ("a^(3/2)",)),
    "fall": (lambda n=80: (lambda t: {"t": t, "d": 0.5 * 9.81 * t ** 2 + R.normal(0, 0.05, n)})(R.uniform(0.1, 3, n)),
             "d", ["t"], ("t^(2)",)),
    "decay": (lambda n=80: (lambda t: {"t": t, "N": 100 * np.exp(-0.3 * t) * (1 + R.normal(0, 0.02, n))})(R.uniform(0, 10, n)),
              "N", ["t"], ("exp(", "·t)")),
    "pendulum": (lambda n=80: (lambda L: {"L": L, "T": 2 * np.pi * np.sqrt(L / 9.81) * (1 + R.normal(0, 0.01, n))})(R.uniform(0.1, 2, n)),
                 "T", ["L"], ("L^(1/2)",)),
    "pendulum2": (lambda n=100: (lambda L, g: {"L": L, "g": g, "T": 2 * np.pi * np.sqrt(L / g) * (1 + R.normal(0, 0.01, n))})(
        R.uniform(0.1, 2, n), R.uniform(1, 25, n)), "T", ["L", "g"], ("L^(1/2)", "g^(-1/2)")),
}


# ---- the search alone -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("law", list(LAWS))
def test_the_search_finds_the_known_law_again(law):
    make, target, inputs, parts = LAWS[law]
    cols = make()
    x = np.column_stack([cols[i] for i in inputs])
    out = S.main({"x": x.tolist(), "y": cols[target].tolist(), "names": inputs})
    assert all(p in out["chosen"]["text"] for p in parts), out["chosen"]["text"]
    assert out["chosen"]["cv_rmse"] < 0.5 * out["baselines"]["linear"]["cv_rmse"]


def test_the_pendulum_constant_is_two_pi():
    cols = LAWS["pendulum2"][0]()
    out = S.main({"x": np.column_stack([cols["L"], cols["g"]]).tolist(), "y": cols["T"].tolist(), "names": ["L", "g"]})
    assert abs(out["chosen"]["c"][0] - 2 * np.pi) < 0.05


def test_noise_gives_the_baseline():
    x = R.uniform(0, 10, 80)
    out = S.main({"x": x[:, None].tolist(), "y": R.normal(5, 1, 80).tolist(), "names": ["x"]})
    assert out["chosen"].get("baseline"), out["chosen"]["text"]


def test_a_law_is_a_structure_never_text():
    out = S.main({"x": R.uniform(1, 2, (30, 1)).tolist(), "y": R.uniform(1, 2, 30).tolist(), "names": ["__import__"]})
    for f in [out["chosen"], *out["front"]]:
        assert set(f["terms"][0][0]) <= {"v", "op", "p"} if f["terms"] else True
        assert all(fa["op"] in ("pow", "log", "sin", "cos", "exp") for t in f["terms"] for fa in t)


# ---- the experiment -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("law", list(LAWS))
def test_a_known_law_is_discovered_and_predicts_unseen_rows(cfg, proj, law):
    make, target, inputs, parts = LAWS[law]
    rel = csv(proj, f"{law}.csv", make())
    r = D.discover(cfg, "leggi", rel, target, inputs, runner=D.direct)
    assert r["status"] == "discovered", D.text(r)
    assert r["D1"] == r["D2"] == "passed" and r["integrity"] == "intact" and len(r["frozen"]) == 2
    assert r["heldout_rmse"] < D.D2_FACTOR * r["baseline_heldout_rmse"]
    rep = json.loads((proj / r["report"]).read_text())
    assert rep["heldout_sha256"] == r["heldout_sha256"] and rep["found"]["chosen"]["text"] == r["law"]
    assert "DISCOVERED" in D.text(r) and D.history(cfg, "leggi")[-1]["status"] == "discovered"


def test_pure_noise_gives_nothing_found(cfg, proj):
    rel = csv(proj, "rumore.csv", {"x": R.uniform(0, 10, 100), "y": R.normal(5, 1, 100)})
    r = D.discover(cfg, "leggi", rel, "y", runner=D.direct)
    assert r["status"] == "nothing" and "Do not call this law discovered" in D.text(r)
    assert len(r["frozen"]) == 1                              # the split only: no law to freeze


def test_the_split_is_frozen_before_the_search_and_the_law_before_the_heldout(cfg, proj):
    rel = csv(proj, "k.csv", kepler())
    seen = {}

    def runner(cfg_, root, payload, limit):
        seen["entries_at_search"] = [e["title"] for e in P.entries(cfg, "leggi") if e.get("event") == "freeze"]
        seen["rows"] = len(payload["y"])
        return D.direct(cfg_, root, payload, limit)

    r = D.discover(cfg, "leggi", rel, "T", runner=runner)
    assert seen["entries_at_search"] == ["Discovery split: T from dati/k.csv"]
    assert seen["rows"] == r["train_rows"] < r["rows"]
    law = next(e for e in P.entries(cfg, "leggi") if e["id"] == r["frozen"][1] and e.get("event") == "freeze")
    frozen = (proj / law["file"]).read_text()
    assert r["law"] in frozen and "held-out rows with a relative RMSE" in frozen
    led = [json.loads(ln) for ln in (proj / "prereg" / "LEDGER.jsonl").read_text().splitlines()]
    closes = [e for e in led if e["event"] == "close"]
    assert [c["id"] for c in closes] == r["frozen"] and all(c["integrity"] == "intact" for c in closes)
    assert [e["event"] for e in led] == ["freeze", "freeze", "close", "close"]


def test_the_search_never_receives_a_heldout_row(cfg, proj):
    cols = kepler(80)
    rel = csv(proj, "k.csv", cols)
    got = {}

    def runner(cfg_, root, payload, limit):
        got["y"] = payload["y"]
        return D.direct(cfg_, root, payload, limit)

    r = D.discover(cfg, "leggi", rel, "T", runner=runner)
    t = D.table(proj.resolve(), rel, "T", None)
    assert r["seed"] == D.seed_of(t["canonical"], "T")           # C620, C640: the split is the numbers', never chosen
    tr, ho = D.split(len(t["y"]), r["seed"], 0.3)
    assert sorted(got["y"]) == sorted(t["y"][tr].tolist())
    assert not set(np.round(t["y"][ho], 9)) & set(np.round(got["y"], 9))
    assert r["heldout_sha256"] == D._sha_rows(ho)


def test_a_law_that_fails_on_unseen_rows_is_not_confirmed(cfg, proj):
    rel = csv(proj, "k.csv", kepler())

    def liar(cfg_, root, payload, limit):                     # a search claiming a tiny error it cannot keep
        out = D.direct(cfg_, root, payload, limit)
        out["chosen"] = {**out["chosen"], "d1_bound": out["chosen"]["d1_bound"] / 100}
        return out

    r = D.discover(cfg, "leggi", rel, "T", runner=liar)
    assert r["status"] == "not_confirmed" and r["D1"] == "failed"


def test_without_frozen_predictions_it_is_never_discovered(cfg, proj):
    cfg.values["AURORA_PREREG_MODE"] = "off"
    rel = csv(proj, "k.csv", kepler())
    r = D.discover(cfg, "leggi", rel, "T", runner=D.direct)
    assert r["status"] == "passed_not_frozen" and not r["frozen"] and not P.entries(cfg, "leggi")


@pytest.mark.parametrize("data,target,why", [
    ("../fuori.csv", "y", "not a file of the project"), ("dati/k.csv", "manca", "no column"),
    ("dati/k.txt", "T", "a .csv or .npz"), ("dati/k.csv", "T", "1 to 8 input columns")])
def test_bad_requests_are_refused(cfg, proj, data, target, why):
    csv(proj, "k.csv", kepler())
    (proj / "dati" / "k.txt").write_text("T\n1\n", encoding="utf-8")
    (proj.parent / "fuori.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    inputs = ["T"] if why.startswith("1 to") else None
    r = D.discover(cfg, "leggi", data, target, inputs, runner=D.direct)
    assert r["status"] == "refused" and why in r["errors"][0], r["errors"]


def test_off_says_so(cfg, proj):
    cfg.values["AURORA_DISCOVER_ENABLED"] = False
    rel = csv(proj, "k.csv", kepler())
    r = D.discover(cfg, "leggi", rel, "T", runner=D.direct)
    assert r["status"] == "error" and "AURORA_DISCOVER_ENABLED" in r["errors"][0] and not D.rule(cfg)


def test_npz_tables_are_read_without_pickles(cfg, proj):
    cols = kepler()
    np.savez(proj / "dati" / "k.npz", a=cols["a"], T=cols["T"])
    r = D.discover(cfg, "leggi", owners(proj, "dati/k.npz"), "T", runner=D.direct)
    assert r["status"] == "discovered" and "a^(3/2)" in r["law"]


def test_reports_are_locked_against_the_tools(cfg, proj):
    assert P.locked("discover/001_t.json") and P.locked("prereg/LEDGER.jsonl") and not P.locked("dati/k.csv")


# ---- the tool --------------------------------------------------------------------------------------------------
def test_the_tool_is_the_conductor_s_and_never_in_a_read_only_run(cfg, proj, monkeypatch):
    rel = csv(proj, "k.csv", kepler())
    monkeypatch.setattr(D, "caged", D.direct)
    assert D.NAME in {t["name"] for t in A.TOOLS}
    run = A.Run(cfg, "leggi", Pseudonymizer(cfg), "g")
    run.readonly = True
    assert A.call(run, D.NAME, {"data": rel, "target": "T"})["text"].startswith("REFUSED")
    run.readonly = False
    out = A.call(run, D.NAME, {"data": rel, "target": "T"})
    assert out["text"].startswith("DISCOVERED"), out


def test_the_agent_gets_the_tool_only_in_a_phase(cfg, proj, monkeypatch):
    assert D.offered(cfg, "una domanda qualunque") == []
    spec = D.offered(cfg, "use freeze_predictions before the experiment")
    assert spec and spec[0]["input_schema"]["required"] == ["project", "data", "target"]
    rel = csv(proj, "k.csv", kepler())
    monkeypatch.setattr(D, "caged", D.direct)
    agent = SimpleNamespace(cfg=cfg, projects=set())
    assert D.agent_call(agent, {"project": "leggi", "data": rel, "target": "T"}).startswith("DISCOVERED")
    assert agent.projects == {"leggi"} and D.agent_call(agent, {"data": rel}).startswith("ERROR")


@needs_cage
def test_the_search_runs_in_the_cage(cfg, proj):
    rel = csv(proj, "k.csv", kepler())
    r = D.discover(cfg, "leggi", rel, "T")
    assert r["status"] == "discovered" and "a^(3/2)" in r["law"], D.text(r)


# ---- C619–C624: the referee's findings (19 Nov) ----------------------------------------------------------------------
def test_d2_is_judged_against_the_better_baseline_and_the_args_cannot_choose(cfg, proj):
    rel = csv(proj, "k.csv", kepler())
    r = D.discover(cfg, "leggi", rel, "T", runner=D.direct)
    b = r["baselines_heldout_rmse"]
    assert r["baseline_heldout_rmse"] == min(b.values()) and set(b) == {"constant", "linear", "zero"}
    assert set(D.run_args({"data": rel, "target": "T", "seed": 7, "baseline": "constant"})) == {"data", "target", "inputs", "holdout"}


def test_too_few_heldout_rows_for_the_inputs_are_refused(cfg, proj):
    cols = {f"x{i}": R.uniform(0, 1, 100) for i in range(8)}
    rel = csv(proj, "molti.csv", {**cols, "y": R.normal(5, 1, 100)})
    r = D.discover(cfg, "leggi", rel, "y", runner=D.direct)
    assert r["status"] == "refused" and "80 held-out rows needed" in r["errors"][0]


def test_noise_with_several_inputs_is_not_discovered(cfg, proj):
    for i in range(6):
        cols = {f"x{j}": R.uniform(0.5, 5, 200) for j in range(4)}
        rel = csv(proj, f"r{i}.csv", {**cols, "y": R.normal(5, 1, 200)})
        r = D.discover(cfg, "leggi", rel, "y", runner=D.direct)
        assert r["status"] in ("nothing", "not_confirmed"), D.text(r)


def test_the_heldout_rows_are_used_once(cfg, proj):
    rel = csv(proj, "k.csv", kepler())
    assert D.discover(cfg, "leggi", rel, "T", runner=D.direct)["status"] == "discovered"
    again = D.discover(cfg, "leggi", rel, "T", inputs=["a"], holdout=0.4, runner=D.direct)
    assert again["status"] == "refused" and "used already" in again["errors"][0]


def test_a_table_written_in_the_run_is_never_a_discovery(cfg, proj):
    since = __import__("time").time() - 1
    rel = csv(proj, "k.csv", kepler())
    r = D.discover(cfg, "leggi", rel, "T", runner=D.direct, since=since)
    assert r["status"] == "passed_not_claimable" and "written or changed in this run" in D.text(r)


def test_a_search_stopped_on_time_is_not_claimable(cfg, proj):
    rel = csv(proj, "k.csv", kepler())

    def slow(cfg_, root, payload, limit):
        return {**D.direct(cfg_, root, payload, limit), "stopped": True}

    r = D.discover(cfg, "leggi", rel, "T", runner=slow)
    assert r["status"] == "passed_not_claimable" and "time limit" in D.text(r)


def test_a_bad_project_name_writes_nothing_in_the_state(cfg, proj, tmp_path):
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    r = D.discover(cfg, "../../../../evil", "dati/k.csv", "T", runner=D.direct)
    assert r["status"] == "refused" and sorted(str(p) for p in tmp_path.rglob("*")) == before
    assert not any("evil" in str(p) for p in tmp_path.parent.rglob("discoveries.json"))


def test_off_keeps_no_history(cfg, proj):
    cfg.values["AURORA_DISCOVER_ENABLED"] = False
    D.discover(cfg, "leggi", csv(proj, "k.csv", kepler()), "T", runner=D.direct)
    assert D.history(cfg, "leggi") == []


def test_a_report_never_overwrites_one(cfg, proj):
    (proj / "discover").mkdir()
    (proj / "discover" / "002_t.json").write_text("{}", encoding="utf-8")
    r = D.discover(cfg, "leggi", csv(proj, "k.csv", kepler()), "T", runner=D.direct)
    assert r["report"].startswith("discover/003_") and (proj / "discover" / "002_t.json").read_text() == "{}"
    import hashlib
    assert hashlib.sha256((proj / r["report"]).read_bytes()).hexdigest() == r["report_sha256"]
    led = [json.loads(ln) for ln in (proj / "prereg" / "LEDGER.jsonl").read_text().splitlines()]
    assert any(r["report_sha256"] in o.get("note", "") for e in led if e["event"] == "close" for o in e["outcomes"])


def test_the_engine_s_entries_cannot_be_forged_nor_closed_by_hand(cfg, proj):
    out = P.tool(cfg, "leggi", "freeze_predictions", {"title": "Discovered law for T", "code_files": [],
                                                      "predictions": [{"id": "D1", "text": "x"}]})
    assert out.startswith("REFUSED") and "discover_law" in out
    r = D.discover(cfg, "leggi", csv(proj, "k.csv", kepler()), "T", runner=D.direct)
    e = next(x for x in P.entries(cfg, "leggi") if x["id"] == r["frozen"][1])
    assert e["origin"] == D.ORIGIN
    split = next(x for x in P.entries(cfg, "leggi") if x["id"] == r["frozen"][0])
    assert split["counted"]["passed"] == 0 and split["counted"]["void"] == 1     # S1: procedural, never a «passed»
    opened = P.freeze(cfg, "leggi", "x", [{"id": "A", "text": "y"}], [], origin=D.ORIGIN)
    out = P.tool(cfg, "leggi", "close_predictions", {"id": opened["id"], "evidence": "dati/k.csv",
                                                     "outcomes": [{"id": "A", "outcome": "passed"}]})
    assert out.startswith("REFUSED") and "never by hand" in out


def test_large_or_odd_tables_are_refused_not_cut(cfg, proj):
    (proj / "dati" / "lunga.csv").write_text("x,y\n" + "1,2\n" * (D.MAX_ROWS + 1), encoding="utf-8")
    r = D.discover(cfg, "leggi", "dati/lunga.csv", "y", runner=D.direct)
    assert r["status"] == "refused" and "at most" in r["errors"][0]
    np.savez_compressed(proj / "dati" / "bomba.npz", x=np.zeros(D.MAX_ROWS + 5), y=np.zeros(D.MAX_ROWS + 5))
    r = D.discover(cfg, "leggi", "dati/bomba.npz", "y", runner=D.direct)
    assert r["status"] == "refused" and "numbers per array" in r["errors"][0]


def test_column_names_are_read_as_written(cfg, proj):
    cols = kepler()
    rel = csv(proj, "k.csv", {"a (UA)": cols["a"], "T (anni)": cols["T"]})
    r = D.discover(cfg, "leggi", rel, "T (anni)", runner=D.direct)
    assert r["status"] == "discovered" and "a (UA)^(3/2)" in r["law"]


def test_the_frozen_law_carries_its_exact_structure(cfg, proj):
    r = D.discover(cfg, "leggi", csv(proj, "k.csv", kepler()), "T", runner=D.direct)
    e = next(x for x in P.entries(cfg, "leggi") if x["id"] == r["frozen"][1])
    assert r["law_sha256"] in (proj / e["file"]).read_text()


@needs_cage
def test_a_python_in_the_project_never_runs_the_search(cfg, proj):
    fake = proj / ".venv" / "bin" / "python"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\necho '@@RESULT@@{}'\n", encoding="utf-8")
    fake.chmod(0o755)
    r = D.discover(cfg, "leggi", csv(proj, "k.csv", kepler()), "T")
    assert r["status"] == "discovered" and "a^(3/2)" in r["law"], D.text(r)

