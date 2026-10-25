# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Libraries a project needs, installed by Aurora into the project's own environment (projects.project_install):
Aurora's libraries seen, not copied nor changed; wheels only; what came written down; the cage runs with it."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

from aurora import prj_run, sys_config

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "projects"


def _plugin(monkeypatch, cfg):
    monkeypatch.setattr(sys_config, "_cached", cfg)
    monkeypatch.setenv("AURORA_PLUGIN", "projects")
    spec = importlib.util.spec_from_file_location("projects_plugin_server", PLUGIN / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_library_aurora_has_is_seen_not_fetched_and_bad_names_refused(cfg, monkeypatch):
    p = _plugin(monkeypatch, cfg)
    proj = cfg.path("AURORA_PROJECTS_DIR") / "prova"
    proj.mkdir(parents=True)
    (proj / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    for bad in (["numpy; rm -rf /"], ["--index-url=http://x numpy"], ["../x"], []):
        with pytest.raises(Exception):
            p.project_install("prova", bad)
    said = p.project_install("prova", ["numpy"])                               # Aurora's own: nothing downloaded
    assert "already there" in said and (proj / ".venv" / "bin" / "python").exists()
    assert ".venv/" in (proj / ".gitignore").read_text(encoding="utf-8")
    assert (proj / "requirements-aurora.txt").read_text(encoding="utf-8").startswith("# what Aurora installed")
    out = subprocess.run([str(proj / ".venv" / "bin" / "python"), "-c", "import numpy; print(numpy.__file__)"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and str(proj) not in out.stdout                   # read from Aurora's, not copied
    cage = prj_run.cage(cfg, proj, "python -V")
    path = cage[cage.index("PATH") + 1]
    assert path.startswith(f"{proj / '.venv' / 'bin'}:")                          # the cage runs with it


def test_a_long_file_says_where_it_stops_and_is_read_on(cfg, monkeypatch):
    # C376: a file over 20,000 characters was cut without a word — Aurora read half of her own notes
    p = _plugin(monkeypatch, cfg)
    proj = cfg.path("AURORA_PROJECTS_DIR") / "lungo"
    proj.mkdir(parents=True)
    (proj / "note.md").write_text("a" * 25000 + "FINE", encoding="utf-8")
    first = p.project_read_file("lungo", "note.md")
    assert first.startswith("a" * 20000) and "5004 more characters" in first and "offset=20000" in first
    assert p.project_read_file("lungo", "note.md", offset=20000) == "a" * 5000 + "FINE"


def test_a_long_document_is_written_a_section_per_call(cfg, monkeypatch):
    # C397: a whole paper in one call ran past the model's budget and was never written
    p = _plugin(monkeypatch, cfg)
    proj = cfg.path("AURORA_PROJECTS_DIR") / "carta"
    proj.mkdir(parents=True)
    p.project_write_file("carta", "docs/paper.md", "# Titolo\n")
    out = p.project_write_file("carta", "docs/paper.md", "## 1. Intro\n", append=True)
    assert (proj / "docs/paper.md").read_text() == "# Titolo\n## 1. Intro\n" and "2 in all" in out
    p.project_write_file("carta", "docs/paper.md", "nuovo\n")                     # without append: the whole file
    assert (proj / "docs/paper.md").read_text() == "nuovo\n"


def test_a_part_of_a_file_is_changed_only_when_it_occurs_once(cfg, monkeypatch):
    # C398: a model that could not rewrite a whole paper could not fix one line of it either
    p = _plugin(monkeypatch, cfg)
    proj = cfg.path("AURORA_PROJECTS_DIR") / "carta2"
    proj.mkdir(parents=True)
    (proj / "paper.md").write_text("## A\nuno\n## B\nuno\nfine\n")
    assert "edited" in p.project_edit_file("carta2", "paper.md", "## B\nuno", "## B\ndue")
    assert (proj / "paper.md").read_text() == "## A\nuno\n## B\ndue\nfine\n"
    import pytest
    with pytest.raises(Exception) as e:
        p.project_edit_file("carta2", "paper.md", "## ", "### ")                   # twice in the file: ambiguous
    assert "2 times" in str(e.value)
    with pytest.raises(Exception):
        p.project_edit_file("carta2", "paper.md", "assente", "x")
