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
try:                                                     # QtWebEngine must come before any QApplication
    import PyQt6.QtWebEngineWidgets  # noqa: F401,E402
except ImportError:
    pass

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


def test_a_second_start_asks_the_first_to_show(home, switch, monkeypatch, tmp_path):
    pytest.importorskip("PyQt6.QtNetwork")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    rt = tmp_path / "rt"
    rt.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(rt))
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication
    from desk.app import aurora_desk, tray
    app = QApplication.instance() or QApplication([])
    m = aurora_desk.Main()
    t = tray.Tray(app, m, QIcon())
    m.tray = t
    assert not m.isVisible()
    assert tray.ask_running_to_show() is True            # what a second start does
    for _ in range(50):
        app.processEvents()
        if m.isVisible():
            break
    assert m.isVisible()
    assert not t.available or t.icon is not None         # offscreen: no tray, the window is the way in
    t.quit()
    app.processEvents()


def test_nobody_running_nothing_to_show(home, monkeypatch, tmp_path):
    pytest.importorskip("PyQt6.QtNetwork")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    rt = tmp_path / "rt2"
    rt.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(rt))
    from PyQt6.QtWidgets import QApplication
    from desk.app import tray
    QApplication.instance() or QApplication([])
    assert tray.ask_running_to_show() is False


def test_the_web_window_loads_only_aurora_s_address():
    """N156: the page may reach Aurora (and ws to it, data:, blob:), nothing else."""
    pytest.importorskip("PyQt6.QtWebEngineWidgets", exc_type=ImportError)
    from PyQt6.QtCore import QUrl
    from desk.app import web
    base = QUrl("http://127.0.0.1:9700/")
    ok = ["http://127.0.0.1:9700/", "http://127.0.0.1:9700/v1/aurora/ask", "ws://127.0.0.1:9700/ws", "data:,x",
          "blob:http://127.0.0.1:9700/abc"]
    no = ["https://example.org/", "http://127.0.0.1:8088/", "http://localhost:9700/", "http://127.0.0.1/",
          "https://127.0.0.1:9700/", "file:///etc/passwd"]
    assert all(web.same_origin(QUrl(u), base) for u in ok)
    assert not any(web.same_origin(QUrl(u), base) for u in no)


def test_what_was_learned_lists_the_general_library_and_the_drafts_with_their_trials(home):
    """C747: what Aurora knows is listed, with every bench trial; nothing is claimed that is not saved."""
    general = Path(__file__).resolve().parents[1] / "desk" / "library"
    d = draft.build(FX["C"], {"name": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}, network=False)
    p = Path(store.save_draft(d["procedure"], "linux", "kcalc", "somma-1", {})["path"])
    store.record_trial(p, True, [{"ok": True}, {"ok": True}])
    store.record_trial(p, False, [{"ok": True}, {"ok": False}])
    got = store.learned(general)
    mine = [e for e in got if e["kind"] == "bozza"]
    assert len(mine) == 1 and mine[0]["program"] == "kcalc" and mine[0]["steps"]
    assert [(t["ok"], t["steps_ok"], t["steps"]) for t in mine[0]["trials"]] == [(True, 2, 2), (False, 1, 2)]
    assert {e["id"] for e in got if e["kind"] == "generale"} >= {"gen:linux/kate/scrivi-e-salva", "gen:linux/kcalc/calcola"}
    assert store.list_drafts() == [p]                                  # the trials file is not a draft
    assert stat.S_IMODE(os.stat(store.trials_path(p)).st_mode) == 0o600


def test_take_away_moves_a_draft_never_a_general_procedure(home):
    d = draft.build(FX["C"], {"name": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}, network=False)
    p = Path(store.save_draft(d["procedure"], "linux", "kcalc", "somma-1", {})["path"])
    store.record_trial(p, True, [{"ok": True}])
    moved = store.remove_draft(p)
    assert not p.exists() and moved.exists() and moved.with_name("somma-1.prove.json").exists()
    assert home in moved.parents and store.list_drafts() == []
    general = Path(__file__).resolve().parents[1] / "desk" / "library" / "linux" / "kcalc" / "calcola.json"
    with pytest.raises(PermissionError):
        store.remove_draft(general)
    assert general.exists()


def test_the_learned_window_builds_offscreen(home, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from desk.app import learned
    app = QApplication.instance() or QApplication([])
    w = learned.Learned(None, Path(__file__).resolve().parents[1] / "desk" / "library")
    assert w.list.count() >= 3 and "Passi" in w.text.toHtml() and not w.remove_btn.isEnabled()
    w.close()
    app.processEvents()


def test_a_click_on_the_tray_opens_aurora_and_the_menu_keeps_the_app_window():
    src = (Path(__file__).resolve().parents[1] / "desk" / "app" / "tray.py").read_text(encoding="utf-8")
    body = src[src.index("def _activated"):src.index("def show(")]
    assert "self._web()" in body and "self.main" not in body
    assert '("Apri", self.show)' in src


def test_web_permissions_use_the_new_signal_and_notifications_reach_the_desktop():
    pytest.importorskip("PyQt6.QtWebEngineWidgets", exc_type=ImportError)
    from PyQt6.QtCore import QUrl
    from desk.app import web
    src = (Path(__file__).resolve().parents[1] / "desk" / "app" / "web.py").read_text(encoding="utf-8")
    assert "self.permissionRequested.connect(self._permission_new)" in src
    assert "setNotificationPresenter(self._notify)" in src and "/usr/bin/notify-send" in src

    class Perm:
        def __init__(self, url, kind):
            self.url, self.kind, self.said = QUrl(url), kind, None

        def origin(self):
            return self.url

        def permissionType(self):
            return self.kind

        def grant(self):
            self.said = "grant"

        def deny(self):
            self.said = "deny"
    from PyQt6.QtWebEngineCore import QWebEnginePermission as P
    page = web.Page.__new__(web.Page)
    page.base = QUrl("http://127.0.0.1:9700/")
    p = Perm("https://example.org/", P.PermissionType.Notifications)
    web.Page._permission_new(page, p)
    assert p.said == "deny"                                   # another site: never asked, never granted
    p = Perm("http://127.0.0.1:9700/", P.PermissionType.Geolocation)
    web.Page._permission_new(page, p)
    assert p.said == "deny"                                   # not in the list: denied
