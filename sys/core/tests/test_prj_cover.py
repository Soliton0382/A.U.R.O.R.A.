# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A project's cover (prj_cover): the page's picture first, then the project's own, then a picture of its main
source file (made again only when that file changes); none of these: no cover; only PNG/JPEG taken, made again."""
import io

import pytest
from PIL import Image

from aurora import prj_cover


@pytest.fixture
def project(cfg):
    root = cfg.path("AURORA_PROJECTS_DIR") / "algo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "helpers.py").write_text("x = 1\n" * 50, encoding="utf-8")
    (root / "src" / "main.py").write_text('#!/usr/bin/env python3\n"""Doc\nmore doc\n"""\nimport os\n\ndef run():\n    return "ok"  # done\n',
                                          encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("import main\n" * 500, encoding="utf-8")
    return "algo"


def _png(w=1600, h=900):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_the_code_picture_shows_the_main_file_after_its_docstring(cfg, project):
    root = cfg.path("AURORA_PROJECTS_DIR") / project
    assert prj_cover.main_file(root).name == "main.py" and prj_cover.kind(cfg, project) == "code"
    assert prj_cover._lines(root / "src" / "main.py")[0] == "import os"
    data, mime = prj_cover.get(cfg, project)
    assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).size == (960, 540)
    assert prj_cover.get(cfg, project)[0] == data                       # kept until the file changes


def test_the_pages_picture_wins_and_is_made_again(cfg, project):
    n = prj_cover.put(cfg, project, _png())
    assert n > 0 and prj_cover.kind(cfg, project) == "set"
    data, mime = prj_cover.get(cfg, project)
    assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).size == (960, 540)
    for bad in (b"", b"GIF89a....", b"<svg/>"):
        with pytest.raises(ValueError):
            prj_cover.put(cfg, project, bad)


def test_a_project_without_code_or_picture_has_none_and_names_stay_inside(cfg):
    (cfg.path("AURORA_PROJECTS_DIR") / "vuoto").mkdir(parents=True)
    assert prj_cover.kind(cfg, "vuoto") == "none" and prj_cover.get(cfg, "vuoto") is None
    for bad in ("../x", "manca"):
        with pytest.raises(ValueError):
            prj_cover.kind(cfg, bad)


def test_a_cad_model_is_drawn_when_there_is_no_picture(cfg, project):
    m = cfg.path("AURORA_PROJECTS_DIR") / project / "cad" / "base"
    m.mkdir(parents=True)
    (m / "parts.json").write_text('{"parts": [{"sign": 10, "name": "piastra", "material": "copper"}]}', encoding="utf-8")
    (m / "part_0.stl").write_text("solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 5\n"
                                  "endloop\nendfacet\nendsolid a\n", encoding="utf-8")
    assert prj_cover.kind(cfg, project) == "cad"                         # before the code's picture
    data, mime = prj_cover.get(cfg, project)
    img = Image.open(io.BytesIO(data))
    assert mime == "image/jpeg" and img.size == (960, 540) and len(set(img.convert("L").get_flattened_data())) > 3
