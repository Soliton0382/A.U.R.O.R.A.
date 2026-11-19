# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📐 Formal proofs (prj_proof, N143): a .lean file of the project is scanned (sorry, native_decide, axiom, unsafe,
custom tactics, foreign imports refused before compiling), compiled by Lean in a read-only cage, and «proved» only
when every theorem depends on the three standard axioms at most; a frozen prediction «PROOF: <file>» is closed by
Aurora's check, never by the agent's outcome; the tool is the conductor's, the agent's and the referee's. Invented Lean
files in tmp_path; the tests that compile need the real toolchain (AURORA_LEAN_HOME) and bwrap, else they skip."""
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import prj_act as A
from aurora import prj_conduct as C
from aurora import prj_prereg as P
from aurora import prj_proof as F
from aurora import prj_referee as R
from aurora.sec_mask import Pseudonymizer

LEAN = Path(__file__).resolve().parents[3] / "sys" / "runtime" / "lean"


def _bwrap() -> bool:
    return bool(shutil.which("bwrap")) and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                              capture_output=True).returncode


def _real() -> bool:
    return (LEAN / "workspace" / "lean-toolchain").is_file() and _bwrap()


needs_cage = pytest.mark.skipif(not _bwrap(), reason="bubblewrap cannot make a namespace here")
needs_lean = pytest.mark.skipif(not _real(), reason="Lean (AURORA_LEAN_HOME) or bwrap missing")

TRUE = "import Mathlib\n\nnamespace Prova\n\ntheorem due_piu_due : (2:ℕ) + 2 = 4 := by norm_num\n\nend Prova\n"


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "aritmetica"
    (p / "proofs").mkdir(parents=True)
    return p


@pytest.fixture
def lean(cfg):
    cfg.values["AURORA_LEAN_HOME"] = str(LEAN)               # absolute: the real toolchain, read only
    return cfg


def put(proj, rel, text):
    (proj / rel).parent.mkdir(parents=True, exist_ok=True)
    (proj / rel).write_text(text, encoding="utf-8")
    return rel


# ---- refused before anything is compiled (no toolchain needed) -----------------------------------------------------
@pytest.mark.parametrize("body,what", [
    ("theorem t : 1 = 2 := by sorry", "sorry"),
    ("theorem t : 1 = 2 := by admit", "admit"),
    ("theorem t : 10 < 20 := by native_decide", "native_decide"),
    ("theorem t : 10 < 20 := by decide +native", "decide +native"),
    ("axiom falso : False\ntheorem t : 1 = 2 := falso.elim", "axiom"),
    ("unsafe def f : Nat := 1", "unsafe"),
    ("@[implemented_by g] def f : Nat := 1", "implemented_by"),
    ("macro \"trucco\" : tactic => `(tactic| sorry)", "macro / elab / syntax"),
    ("elab \"trucco\" : tactic => pure ()", "macro / elab / syntax"),
    ("run_cmd pure ()", "run_cmd / run_elab / run_tac / by_elab"),
    ("#eval IO.println \"x\"", "#eval"),
    ("set_option debug.skipKernelTC true in\ntheorem t : 1 = 1 := rfl", "set_option (debug / kernel)"),
])
def test_cheats_are_refused_before_compiling(cfg, proj, body, what, monkeypatch):
    monkeypatch.setattr(F.subprocess, "run", lambda *a, **k: pytest.fail("compiled"))
    r = F.check(cfg, "aritmetica", put(proj, "proofs/t.lean", f"import Mathlib\n{body}\n"))
    assert r["status"] == "refused" and what in {f["what"] for f in r["forbidden"]}, r
    assert any(f["line"] >= 2 for f in r["forbidden"])


def test_comments_and_strings_are_not_code(cfg, proj):
    code = F.strip('-- sorry here\n/- admit /- nested sorry -/ -/\ndef s := "sorry"\ntheorem t : 1 = 1 := rfl\n')
    assert F.forbidden(code, "x.lean") == [] and F.declared(code) == ["t"]
    assert "#print" not in code and code.count("\n") == 4


def test_names_follow_the_namespaces(cfg):
    code = F.strip("namespace A\ntheorem x : True := trivial\nsection\nlemma y : True := trivial\nend\nend A\n"
                   "theorem _root_.z : True := trivial\n@[simp] private theorem w : True := trivial\n")
    assert F.declared(code) == ["A.x", "A.y", "z", "w"]


def test_outside_the_project_and_foreign_imports_are_refused(cfg, proj, tmp_path, monkeypatch):
    monkeypatch.setattr(F.subprocess, "run", lambda *a, **k: pytest.fail("compiled"))
    (tmp_path / "fuori.lean").write_text(TRUE, encoding="utf-8")
    for path in ("../../fuori.lean", str(tmp_path / "fuori.lean"), "/etc/passwd", "proofs/manca.lean"):
        r = F.check(cfg, "aritmetica", path)
        assert r["status"] == "refused", path
    (proj / "link.lean").symlink_to(tmp_path / "fuori.lean")
    assert F.check(cfg, "aritmetica", "link.lean")["status"] == "refused"
    r = F.check(cfg, "aritmetica", put(proj, "proofs/i.lean", "import Mathlib\nimport Utre.Segreto\ntheorem t : 1 = 1 := rfl\n"))
    assert r["status"] == "refused" and "import Utre.Segreto" in r["forbidden"][0]["what"]


def test_a_cheat_in_an_imported_project_file_is_refused(cfg, proj, monkeypatch):
    monkeypatch.setattr(F.subprocess, "run", lambda *a, **k: pytest.fail("compiled"))
    put(proj, "Lib/Aiuto.lean", "import Mathlib\ntheorem aiuto : 1 = 2 := by sorry\n")
    r = F.check(cfg, "aritmetica", put(proj, "proofs/m.lean", "import Lib.Aiuto\ntheorem t : 1 = 1 := rfl\n"))
    assert r["status"] == "refused" and r["forbidden"][0]["file"] == "Lib/Aiuto.lean"


def test_no_lean_installed_is_said(cfg, proj):
    r = F.check(cfg, "aritmetica", put(proj, "proofs/t.lean", TRUE))
    assert r["status"] == "error" and "Lean non installato" in r["errors"][0]
    assert F.history(cfg, "aritmetica")[-1]["status"] == "error"


def test_off_checks_nothing(cfg, proj):
    cfg.values["AURORA_PROOF_ENABLED"] = False
    r = F.check(cfg, "aritmetica", put(proj, "proofs/t.lean", TRUE))
    assert r["status"] == "error" and "AURORA_PROOF_ENABLED" in r["errors"][0]
    assert F.offered(cfg, "freeze_predictions proof_check") == [] and F.rule(cfg) == ""


# ---- the cage, with a stand-in Lean (no toolchain needed) -----------------------------------------------------------
def fake_lean(cfg, tmp_path, script: str) -> None:
    home = tmp_path / "lean"
    (home / "workspace" / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib" / "lean").mkdir(parents=True)
    (home / "workspace" / "lean-toolchain").write_text("leanprover/lean4:v9.9.9\n", encoding="utf-8")
    b = home / "elan" / "toolchains" / "leanprover--lean4---v9.9.9" / "bin"
    b.mkdir(parents=True)
    (b / "lean").write_text("#!/bin/bash\n" + script, encoding="utf-8")
    (b / "lean").chmod(0o755)
    cfg.values["AURORA_LEAN_HOME"] = str(home)


@needs_cage
def test_the_cage_cannot_write_the_project(cfg, proj, tmp_path):
    fake_lean(cfg, tmp_path, "")
    tc = F.toolchain(cfg)
    args = F.cage(cfg, proj.resolve(), tc, f"echo x > {proj}/scritto.txt; echo y > {tc['home']}/w; "
                                           "echo z > /tmp/build.txt && cat /tmp/build.txt && echo $LEAN_PATH")
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert not (proj / "scritto.txt").exists() and not (tc["home"] / "w").exists()
    assert "z" in r.stdout and "/tmp/build:" in r.stdout and "Read-only" in r.stderr


@needs_cage
def test_the_timeout_is_honoured(cfg, proj, tmp_path):
    fake_lean(cfg, tmp_path, "sleep 30\n")
    cfg.values["AURORA_PROOF_TIMEOUT_S"] = 1
    r = F.check(cfg, "aritmetica", put(proj, "proofs/t.lean", TRUE))
    assert r["status"] == "error" and "AURORA_PROOF_TIMEOUT_S" in r["errors"][0] and r["seconds"] < 10


@needs_cage
def test_a_sorry_axiom_from_the_compiler_is_not_proved(cfg, proj, tmp_path):
    # a stand-in for an elaboration that failed: Lean reports sorryAx for the theorem (and exit 1)
    fake_lean(cfg, tmp_path, "cat >/dev/null\necho '{\"severity\":\"error\",\"fileName\":\"<stdin>\",\"pos\":{\"line\":5,"
                             "\"column\":1},\"data\":\"unsolved goals\"}'\necho '{\"severity\":\"information\",\"fileName\":"
                             "\"<stdin>\",\"pos\":{\"line\":8,\"column\":0},\"data\":\"'\"'\"'Prova.due_piu_due'\"'\"' "
                             "depends on axioms: [propext, sorryAx]\"}'\nexit 1\n")
    r = F.check(cfg, "aritmetica", put(proj, "proofs/t.lean", TRUE))
    assert r["status"] == "not_proved" and r["axioms"] == {"Prova.due_piu_due": ["propext", "sorryAx"]}
    assert any("proofs/t.lean:5:1: unsolved goals" in e for e in r["errors"]) and any("sorryAx" in e for e in r["errors"])


# ---- the real Lean (skipped without the toolchain) -----------------------------------------------------------------
@needs_lean
def test_a_true_theorem_is_proved(lean, proj):
    r = F.check(lean, "aritmetica", put(proj, "proofs/t.lean", TRUE + "\ntheorem terzo (p : Prop) : p ∨ ¬p := Classical.em p\n"))
    assert r["status"] == "proved", r
    assert set(r["axioms"]) == {"Prova.due_piu_due", "terzo"}
    assert all(set(a) <= set(F.STANDARD) for a in r["axioms"].values())
    assert F.history(lean, "aritmetica")[-1]["status"] == "proved"


@needs_lean
def test_a_false_statement_is_not_proved(lean, proj):
    r = F.check(lean, "aritmetica", put(proj, "proofs/f.lean", "import Mathlib\n\ntheorem f : (2:ℕ) + 2 = 5 := by norm_num\n"))
    assert r["status"] == "not_proved" and any(e.startswith("proofs/f.lean:3:") for e in r["errors"]), r


@needs_lean
def test_a_project_file_imported_is_built_in_the_cage(lean, proj):
    put(proj, "Lib/Base.lean", "import Mathlib\n\ntheorem base (n : ℕ) : n + 0 = n := by simp\n")
    r = F.check(lean, "aritmetica", put(proj, "proofs/u.lean", "import Lib.Base\n\ntheorem uso : (3:ℕ) + 0 = 3 := base 3\n"))
    assert r["status"] == "proved", r
    assert not list(proj.rglob("*.olean"))                    # the build stayed in the cage's tmpfs


# ---- the N142 link: «PROOF:» predictions are closed by Aurora ------------------------------------------------------
def test_a_proof_prediction_is_closed_by_aurora_not_by_the_agent(cfg, proj, monkeypatch):
    put(proj, "proofs/t.lean", TRUE)
    put(proj, "esito.txt", "fatto\n")
    seen = []
    monkeypatch.setattr(F, "check", lambda c, p, path, record=True: seen.append(path) or {
        "path": path, "status": "not_proved", "errors": ["proofs/t.lean:5:1: unsolved goals"], "axioms": {},
        "theorems": ["Prova.due_piu_due"], "seconds": 1.0, "sha256": "x"})
    e = P.freeze(cfg, "aritmetica", "Due più due", [{"id": "T1", "text": "PROOF: proofs/t.lean due più due fa quattro"},
                                                     {"id": "N1", "text": "la tabella ha 4 righe"}], [])
    assert e["proofs"] == {"T1": "proofs/t.lean"} and "proofs/t.lean" in e["code"]
    out = P.tool(cfg, "aritmetica", "close_predictions", {"id": e["id"], "evidence": "esito.txt", "outcomes": [
        {"id": "T1", "outcome": "passed"}, {"id": "N1", "outcome": "passed", "value": "4"}]})
    assert seen == ["proofs/t.lean"] and "T1 not_proved (you said passed)" in out
    got = P.entries(cfg, "aritmetica")[0]
    t1 = next(o for o in got["outcomes"] if o["id"] == "T1")
    assert t1["outcome"] == "failed" and t1["claimed"] == "passed" and got["counted"] == {"passed": 1, "failed": 1, "void": 0}
    assert got["proofs"]["T1"]["status"] == "not_proved"


def test_a_proof_prediction_needs_no_outcome_and_passes_only_if_proved(cfg, proj, monkeypatch):
    put(proj, "esito.txt", "fatto\n")
    monkeypatch.setattr(F, "check", lambda c, p, path, record=True: {
        "path": path, "status": "proved", "errors": [], "axioms": {"t": ["propext"]}, "theorems": ["t"],
        "seconds": 1.0, "sha256": "x"})
    e = P.freeze(cfg, "aritmetica", "Da scrivere", [{"id": "T1", "text": "PROOF: proofs/nuovo.lean"}], [])
    assert e["code"] == {}                                    # not written yet: nothing to hash
    P.close(cfg, "aritmetica", e["id"], [], "esito.txt")
    assert P.entries(cfg, "aritmetica")[0]["counted"]["passed"] == 1
    assert P.tool(cfg, "aritmetica", "freeze_predictions", {"title": "x", "code_files": [], "predictions": [
        {"id": "T", "text": "PROOF: ../fuori.lean"}]}).startswith("REFUSED")


# ---- who may use the tool --------------------------------------------------------------------------------------------
def test_the_tool_is_the_conductor_s_the_agent_s_and_the_referee_s(cfg, proj, monkeypatch):
    assert F.NAME in {t["name"] for t in A.TOOLS} and F.NAME in {t["name"] for t in R.TOOLS}
    assert "write_file" not in {t["name"] for t in R.TOOLS}
    run = A.Run(cfg, "aritmetica", Pseudonymizer(cfg), "g")
    run.tools, run.readonly, run.notes = R.TOOLS, True, False
    monkeypatch.setattr(F, "check", lambda c, p, path, record=True: {
        "path": path, "status": "proved", "errors": [], "axioms": {"t": []}, "theorems": ["t"], "seconds": 0.5})
    out = A.call(run, F.NAME, {"path": "proofs/t.lean"})
    assert not out["error"] and out["text"].startswith("PROVED")
    cmd = A._command(run, SimpleNamespace(bin="claude", model="opus"), "/s", "/m", "sid", False, persist=False)
    assert f"mcp__aurora__{F.NAME}" in cmd[cmd.index("--allowedTools") + 1].split(",")
    assert "proof_check" in R.PROMPT
    offered = F.offered(cfg, P.rule(cfg))                     # a project's phase: the rule in its context
    assert [t["name"] for t in offered] == [F.NAME] and offered[0]["input_schema"]["required"] == ["project", "path"]
    assert F.offered(cfg, "che tempo fa domani") == []
    agent = SimpleNamespace(cfg=cfg, projects=set())
    assert F.agent_call(agent, {"project": "aritmetica", "path": "proofs/t.lean"}).startswith("PROVED")
    assert agent.projects == {"aritmetica"}


def test_the_draft_says_theorems_are_proved_only_by_proof_check(cfg):
    assert "proof_check says PROVED" in C.draft_system(cfg, "aritmetica", "x")
    cfg.values["AURORA_PROOF_ENABLED"] = False
    assert "proof_check" not in C.draft_system(cfg, "aritmetica", "x")
