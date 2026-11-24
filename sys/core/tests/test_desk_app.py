# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: the app's store (desk/app/store.py) — the accessibility switch put back only when it still holds
what the app wrote (M334 P1: it persists in dconf), the personal library 0700/0600, examples only when kept."""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk.app import draft, store  # noqa: E402

FX = json.loads((Path(__file__).parent / "data" / "desk_demo_events.json").read_text(encoding="utf-8"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    st = tmp_path / "state" / "aurora-desk"
    monkeypatch.setattr(store, "STATE", st)
    monkeypatch.setattr(store, "LIBRARY", st / "library")
    monkeypatch.setattr(store, "DRAFTS", st / "library" / "bozze")
    monkeypatch.setattr(store, "BENCH", st / "bench")
    monkeypatch.setattr(store, "A11Y", st / "a11y.json")
    return st


class Switch:
    def __init__(self, on: bool):
        self.on, self.sets = on, []

    def get(self):
        return self.on

    def set(self, v):
        self.sets.append(v)
        self.on = v


@pytest.fixture
def switch(monkeypatch):
    sw = Switch(False)
    monkeypatch.setattr(store, "a11y_enabled", sw.get)
    monkeypatch.setattr(store, "_set_a11y", sw.set)
    return sw


def test_on_then_back_off(home, switch):
    store.a11y_on()
    assert switch.on is True and json.loads(store.A11Y.read_text()) == {"before": False, "wrote": True}
    assert stat.S_IMODE(os.stat(store.A11Y).st_mode) == 0o600
    assert store.a11y_restore() == "back to False" and switch.on is False and not store.A11Y.exists()


def test_never_turned_off_if_it_was_on_before(home, switch):
    switch.on = True                                     # the owner had it on (a screen reader)
    store.a11y_on()
    store.a11y_restore()
    assert switch.on is True and switch.sets == []


def test_left_alone_if_changed_meanwhile(home, switch):
    store.a11y_on()
    switch.on = False                                    # someone turned it off meanwhile
    r = store.a11y_restore()
    assert "left as it is" in r and switch.sets == [True]


def test_a_crash_is_repaired_at_the_next_start(home, switch):
    store.a11y_on()                                      # the app dies here; a11y.json stays
    assert store.A11Y.exists()
    assert store.a11y_restore() == "back to False"      # main() calls this at start


def test_an_older_record_keeps_the_real_before(home, switch):
    store.a11y_on()                                      # before = False
    store.a11y_on()                                      # a second start must not record «before = True»
    assert json.loads(store.A11Y.read_text())["before"] is False


def test_save_draft_private_and_valid(home):
    d = draft.build(FX["C"], {"name": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}, network=False)
    r = store.save_draft(d["procedure"], "linux", "kcalc", "somma-1", {})
    assert r["errors"] == [] and r["sha256"]
    p = Path(r["path"])
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(p.parent).st_mode) == 0o700
    assert json.loads(p.read_text())["id"] == "per:linux/kcalc/somma-1"
    assert not p.with_name("somma-1.esempi.json").exists()      # examples dropped unless kept
    assert "12+30" not in p.read_text()


def test_kept_examples_go_apart(home):
    d = draft.build(FX["C"], {"name": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}, network=False)
    r = store.save_draft(d["procedure"], "linux", "kcalc", "somma-2", {"p1": "12+30"})
    ex = Path(r["path"]).with_name("somma-2.esempi.json")
    assert json.loads(ex.read_text()) == {"p1": "12+30"} and stat.S_IMODE(os.stat(ex).st_mode) == 0o600
    assert "12+30" not in Path(r["path"]).read_text()


def test_bad_names_refused(home):
    with pytest.raises(ValueError):
        store.draft_path("linux", "kcalc", "../fuori")


def test_an_invalid_draft_is_not_saved(home):
    d = draft.build(FX["C"], {"name": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}, network=False)
    proc = dict(d["procedure"], trusted=True)            # a field that would widen what Aurora may do
    r = store.save_draft(proc, "linux", "kcalc", "somma-3", {})
    assert r["path"] is None and any("widen" in e for e in r["errors"])
    assert store.list_drafts() == []


def test_the_app_window_builds_offscreen(home, switch, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from desk.app import aurora_desk
    app = QApplication.instance() or QApplication([])
    m = aurora_desk.Main()
    assert m.show_btn.text() == "Mostrami" and not m.end_btn.isEnabled()
    m.close()
    app.processEvents()
