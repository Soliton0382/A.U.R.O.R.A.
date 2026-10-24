# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖥️ prj_live: one look at everything that moves in a project, for the page's activity console."""
import pytest

from aurora import prj_conduct, prj_live


def test_a_look_has_the_conductor_the_files_and_the_running_phase(cfg):
    root = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n")
    prj_conduct.add(cfg, "demo", "ask", "Fai la fase 1")
    g = prj_conduct.add(cfg, "demo", "goal", "# Fase 1: batteria\n\ndettagli", status="running", run_id="r9")
    d = prj_live.snapshot(cfg, "demo")
    assert [e["kind"] for e in d["conduct"]] == ["ask", "goal"]
    assert d["conduct"][1]["head"] == "Fase 1: batteria" and d["running"] == "r9"
    assert [f["path"] for f in d["files"]] == ["src/a.py"] and d["commits"] == [] and d["talk"]["n"] == 0
    prj_conduct.update(cfg, "demo", g["id"], status="done")
    assert prj_live.snapshot(cfg, "demo")["running"] is None


def test_a_look_refuses_a_bad_or_missing_project(cfg):
    for bad in ("../x", "nope"):
        with pytest.raises(ValueError):
            prj_live.snapshot(cfg, bad)
