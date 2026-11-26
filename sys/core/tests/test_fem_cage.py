# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N155: when FEniCSx is installed, the projects' cage binds it read only and gives $FEM_PYTHON (CUDA hidden); when
it is not, nothing of it appears and the rule is not given."""
from pathlib import Path

from aurora import prj_run


def _fake(tmp_path: Path) -> Path:
    py = tmp_path / "sys" / "runtime" / "fenicsx" / "env" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    return tmp_path


def test_the_cage_binds_fenicsx_read_only_with_fem_python(cfg, tmp_path, monkeypatch):
    root = _fake(tmp_path / "aurora")
    monkeypatch.setattr(prj_run, "fem_home", lambda r: (root / "sys" / "runtime" / "fenicsx").resolve())
    proj = tmp_path / "p"
    proj.mkdir()
    args = prj_run.cage(cfg, proj, "true", readonly=True)
    fem = str((root / "sys" / "runtime" / "fenicsx").resolve())
    i = args.index(fem)
    assert args[i - 1] == "--ro-bind" and args[i + 1] == fem
    j = args.index("FEM_PYTHON")
    assert args[j - 1] == "--setenv" and args[j + 1] == f"{fem}/env/bin/python"
    assert args[args.index("CUDA_VISIBLE_DEVICES") + 1] == ""
    assert i < args.index("--clearenv") < j                # bound before the environment is cleared, set after


def test_without_fenicsx_nothing_of_it_is_in_the_cage(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(prj_run, "fem_home", lambda r: None)
    proj = tmp_path / "p"
    proj.mkdir()
    assert "FEM_PYTHON" not in prj_run.cage(cfg, proj, "true", readonly=True)


def test_fem_home_needs_the_environment(tmp_path):
    assert prj_run.fem_home(tmp_path) is None
    assert prj_run.fem_home(_fake(tmp_path)) is not None
