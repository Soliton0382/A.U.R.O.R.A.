# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The 3D printer's zip (prj_print, N41): one STL per part named by its sign and name, a README with the sizes in mm
and advice said to be generic; only the parts that have their STL; no name leaves the projects' folder."""
import io
import json
import zipfile

import pytest

from aurora import prj_cover_cad, prj_print


@pytest.fixture
def model(cfg):
    m = cfg.path("AURORA_PROJECTS_DIR") / "lampada" / "cad" / "base"
    m.mkdir(parents=True)
    (m / "parts.json").write_text(json.dumps({"parts": [
        {"sign": 10, "name": "Piastra di base", "size_mm": [120.0, 80.0, 5.0]},
        {"sign": 20, "name": "Braccio", "size_mm": [10.0, 10.0, 150.0]},
        {"sign": 30, "name": "Senza STL", "size_mm": [1.0, 1.0, 1.0]}]}), encoding="utf-8")
    (m / "part_0.stl").write_text(_box("a", 120, 80, 5), encoding="utf-8")          # lying already
    (m / "part_1.stl").write_text(_box("b", 10, 30, 150, x0=200), encoding="utf-8")  # standing: its 30 × 150 side goes down
    return "lampada"


def _box(name, dx, dy, dz, x0=0.0):
    """An STL box (12 triangles) from (x0, 0, 0) to (x0 + dx, dy, dz)."""
    c = [(x0 + i * dx, j * dy, k * dz) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    out = [f"solid {name}"]
    for a, b, cc, d in faces:
        for t in ((a, b, cc), (a, cc, d)):
            out += ["facet normal 0 0 0", "outer loop", *(f"vertex {c[v][0]} {c[v][1]} {c[v][2]}" for v in t),
                    "endloop", "endfacet"]
    return "\n".join(out + [f"endsolid {name}", ""])


def test_the_zip_holds_each_part_and_a_readme(cfg, model):
    z = zipfile.ZipFile(io.BytesIO(prj_print.bundle(cfg, model, "base")))
    assert sorted(z.namelist()) == ["010_piastra-di-base.stl", "020_braccio.stl", "README.txt", "piatto_1.3mf"]
    arm = prj_cover_cad.load_stl_bytes(z.read("020_braccio.stl")).reshape(-1, 3)
    assert arm.min(0).tolist() == [0, 0, 0] and round(float(arm[:, 2].max()), 3) == 10    # laid on its 30 × 150 side
    readme = z.read("README.txt").decode()
    assert "millimetri" in readme and "120 × 80 × 5 mm" in readme and "CONSIGLIO GENERICO" in readme
    assert "già appoggiata" in readme and "220 × 220" in readme
    plate = zipfile.ZipFile(io.BytesIO(z.read("piatto_1.3mf")))
    xml = plate.read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in xml and xml.count("<object ") == 2 and xml.count("<item ") == 2
    assert "3D/3dmodel.model" in plate.read("_rels/.rels").decode()
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


def test_a_plate_larger_than_the_bed_is_said(cfg, model):
    readme = zipfile.ZipFile(io.BytesIO(prj_print.bundle(cfg, model, "base", bed=(100, 100)))).read("README.txt").decode()
    assert "più grandi del piatto di 100 × 100 mm: 010_piastra-di-base.stl" in readme
