# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The 3D printer's zip (prj_print, N41): one STL per part named by its sign and name, a README with the sizes in mm
and advice said to be generic; only the parts that have their STL; no name leaves the projects' folder."""
import io
import json
import zipfile

import pytest

from aurora import prj_print


@pytest.fixture
def model(cfg):
    m = cfg.path("AURORA_PROJECTS_DIR") / "lampada" / "cad" / "base"
    m.mkdir(parents=True)
    (m / "parts.json").write_text(json.dumps({"parts": [
        {"sign": 10, "name": "Piastra di base", "size_mm": [120.0, 80.0, 5.0]},
        {"sign": 20, "name": "Braccio", "size_mm": [10.0, 10.0, 150.0]},
        {"sign": 30, "name": "Senza STL", "size_mm": [1.0, 1.0, 1.0]}]}), encoding="utf-8")
    (m / "part_0.stl").write_bytes(b"solid a\nendsolid a\n")
    (m / "part_1.stl").write_bytes(b"solid b\nendsolid b\n")
    return "lampada"


def test_the_zip_holds_each_part_and_a_readme(cfg, model):
    z = zipfile.ZipFile(io.BytesIO(prj_print.bundle(cfg, model, "base")))
    assert sorted(z.namelist()) == ["010_piastra-di-base.stl", "020_braccio.stl", "README.txt"]
    assert z.read("020_braccio.stl") == b"solid b\nendsolid b\n"
    readme = z.read("README.txt").decode()
    assert "millimetri" in readme and "120 × 80 × 5 mm" in readme and "CONSIGLIO GENERICO" in readme
    assert "Senza STL" not in readme
    assert "GENERIC ADVICE" in zipfile.ZipFile(io.BytesIO(prj_print.bundle(cfg, model, "base", "en"))).read("README.txt").decode()


def test_the_list_and_the_names_that_are_refused(cfg, model):
    assert [p["sign"] for p in prj_print.models(cfg, model)[0]["parts"]] == [10, 20]
    for project, m in (("../fuori", "base"), (model, "../../x"), ("manca", "base")):
        with pytest.raises(ValueError):
            prj_print.bundle(cfg, project, m)
    with pytest.raises(FileNotFoundError):
        prj_print.bundle(cfg, model, "vuoto")
    (cfg.path("AURORA_PROJECTS_DIR") / "senza-cad").mkdir()
    assert prj_print.models(cfg, "senza-cad") == []
