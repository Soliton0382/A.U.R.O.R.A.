# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import importlib.util
from pathlib import Path

import pytest

from aurora import sys_config


@pytest.fixture
def notes(cfg, monkeypatch, tmp_path):
    folder = tmp_path / "vault-obsidian"
    (folder / "Progetti").mkdir(parents=True)
    (folder / "Progetti" / "Aurora.md").write_text("# Aurora\nIdee per il plugin calendario.\n")
    (folder / ".obsidian").mkdir()
    (folder / ".obsidian" / "hidden.md").write_text("config")
    cfg.values["AURORA_NOTES_DIR"] = str(folder)
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    spec = importlib.util.spec_from_file_location("notes", Path(__file__).resolve().parents[2] / "plugins" / "notes" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, folder


def test_notes_are_found_read_and_only_grow(notes):
    N, folder = notes
    assert "Progetti/Aurora" in N.notes_list() and "hidden" not in N.notes_list()         # .obsidian is not a note
    assert N.notes_search("plugin calendario").startswith("Progetti/Aurora: Idee per il plugin")
    assert N.notes_write("Progetti/Aurora", "Seconda idea.") == "added to: Progetti/Aurora"
    assert N.notes_read("Progetti/Aurora").endswith("Idee per il plugin calendario.\n\n\nSeconda idea.\n")
    assert N.notes_write("Diario/2026-10-02", "Oggi.") == "created: Diario/2026-10-02"
    assert (folder / "Diario" / "2026-10-02.md").read_text() == "Oggi.\n"


def test_a_note_never_leaves_its_folder(notes):
    N, folder = notes
    for bad in ("../fuori", "../../etc/passwd", "/etc/hosts"):
        with pytest.raises(Exception):
            N.notes_write(bad, "x")
    assert not (folder.parent / "fuori.md").exists()
