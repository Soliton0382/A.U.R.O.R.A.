# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The realistic view and the simulators (prj_view, prj_sim, N42): a part's material is the one given, else guessed
from its name and said to be guessed; a part's mesh never leaves its model's folder; a simulator's formulas use only
known names and allowed functions, and a file that does not pass is listed with its error."""
import json

import pytest

from aurora import prj_sim, prj_view


@pytest.fixture
def project(cfg):
    root = cfg.path("AURORA_PROJECTS_DIR") / "motore"
    m = root / "cad" / "base"
    m.mkdir(parents=True)
    (m / "parts.json").write_text(json.dumps({"parts": [
        {"sign": 10, "name": "Bobina A1"}, {"sign": 20, "name": "Albero"},
        {"sign": 30, "name": "Coperchio", "material": "aluminium"}, {"sign": 40, "name": "Pezzo strano"}]}), encoding="utf-8")
    for k in range(4):
        (m / f"part_{k}.stl").write_bytes(b"solid a\nendsolid a\n")
    (m / "exploded_0.stl").write_bytes(b"solid e\nendsolid e\n")
    (root / "sim").mkdir()
    return "motore"


def test_materials_given_guessed_and_the_fallback(cfg, project):
    parts = prj_view.scene(cfg, project)[0]["parts"]
    assert [(p["material"], p["guessed"]) for p in parts] == [
        ("copper", True), ("steel", True), ("aluminium", False), ("plastic_light", True)]
    assert [p["exploded"] for p in parts] == [True, False, False, False]
    assert set(p["material"] for p in parts) <= set(prj_view.MATERIALS)


def test_a_mesh_stays_in_its_folder(cfg, project):
    assert prj_view.mesh(cfg, project, "base", 1).name == "part_1.stl"
    assert prj_view.mesh(cfg, project, "base", 0, exploded=True).name == "exploded_0.stl"
    with pytest.raises(FileNotFoundError):
        prj_view.mesh(cfg, project, "base", 1, exploded=True)
    for p, m in (("../x", "base"), (project, "../../etc"), ("manca", "base")):
        with pytest.raises(ValueError):
            prj_view.mesh(cfg, p, m, 0)


SIM = {"title": "Bobina", "consts": {"rho": 1.68e-8},
       "params": [{"id": "N", "label": "spire", "min": 10, "max": 400, "step": 10, "value": 100},
                  {"id": "d", "label": "filo", "unit": "mm", "min": 0.1, "max": 1, "step": 0.01, "value": 0.35}],
       "outputs": [{"id": "A", "expr": "pi*(d/2000)^2", "hidden": True},
                   {"id": "R", "label": "resistenza", "unit": "ohm", "expr": "rho*N*0.1/A"},
                   {"id": "ok", "expr": "if(R < 5, 1, 0)"}],
       "plot": {"x": "N", "y": "R"}}


def test_a_simulator_is_read_and_checked(cfg, project):
    folder = cfg.path("AURORA_PROJECTS_DIR") / project / "sim"
    (folder / "bobina.json").write_text(json.dumps(SIM), encoding="utf-8")
    bad = dict(SIM, outputs=[{"id": "x", "expr": "__import__('os')"}])
    (folder / "rotto.json").write_text(json.dumps(bad), encoding="utf-8")
    (folder / "nonjson.json").write_text("{", encoding="utf-8")
    got = {s["name"]: s for s in prj_sim.sims(cfg, project)}
    assert got["bobina"]["plot"] == {"x": "N", "y": ["R"]} and got["bobina"]["outputs"][0]["hidden"]
    assert "error" in got["rotto"] and "error" in got["nonjson"]
    with pytest.raises(ValueError):
        prj_sim.sims(cfg, "../fuori")


@pytest.mark.parametrize("expr", ["a.b", "x[0]", "lambda: 1", "'s'", "open(1)", "y", "1 < N < 3", "N if N else 1",
                                  "min(N, key=1)", "N ** 2 ** 999 +"])
def test_formulas_that_are_refused(expr):
    with pytest.raises(ValueError):
        prj_sim.check_expr(expr, {"N"})


def test_formulas_that_pass_and_the_order_of_names():
    for expr in ("-N^2 + sqrt(abs(N))*pi", "if(N >= 2, mu0, e)", "atan2(N, 1) / 2", "1e-3*N"):
        prj_sim.check_expr(expr, {"N"})
    later = dict(SIM, outputs=[{"id": "R", "expr": "A*2"}, {"id": "A", "expr": "N"}])   # A used before it exists
    with pytest.raises(ValueError):
        prj_sim.check(later)
    with pytest.raises(ValueError):
        prj_sim.check(dict(SIM, params=[{"id": "N", "min": 5, "max": 1}]))
