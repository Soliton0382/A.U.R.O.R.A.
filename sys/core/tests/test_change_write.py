# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""An approved change on code that belongs to another account: written whole, or not at all (C518)."""
import shutil
from types import SimpleNamespace

from aurora import agt_change, sys_tests


def _setup(tmp_path, monkeypatch):
    live, sand = tmp_path / "live", tmp_path / "sandboxes"
    box = sand / "fix1"
    for root, text in ((live, "a = 1\n"), (box, "a = 2\n"), (box / ".base", "a = 1\n")):
        (root / "sys/core/aurora").mkdir(parents=True)
        (root / "sys/core/aurora/a.py").write_text(text)
    cfg = SimpleNamespace(root=live, path=lambda key: sand)
    monkeypatch.setattr(sys_tests, "run_suite", lambda *a, **k: {"ok": True, "summary": "1 passed", "output": ""})
    return live, cfg


def test_the_times_refused_do_not_stop_a_change(tmp_path, monkeypatch):
    live, cfg = _setup(tmp_path, monkeypatch)
    real_stat, real_mode = shutil.copystat, shutil.copymode
    def refusing(real):                                # as on the live code owned by the owner's account
        def call(src, dst, **k):
            if "live" in str(dst):
                raise PermissionError(1, "Operation not permitted")
            return real(src, dst, **k)
        return call
    monkeypatch.setattr(shutil, "copystat", refusing(real_stat))
    monkeypatch.setattr(shutil, "copymode", refusing(real_mode))
    r = agt_change.apply("fix1", lambda *a: None, cfg, restart=False)
    assert r["applied"] is True and (live / "sys/core/aurora/a.py").read_text() == "a = 2\n"


def test_a_write_that_fails_puts_the_live_file_back(tmp_path, monkeypatch):
    live, cfg = _setup(tmp_path, monkeypatch)
    real = shutil.copyfile
    broke = []
    def half(src, dst, **k):                           # the content is written, then the copy breaks (once)
        real(src, dst)
        if "live" in str(dst) and not broke:
            broke.append(dst)
            raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(shutil, "copyfile", half)
    r = agt_change.apply("fix1", lambda *a: None, cfg, restart=False)
    monkeypatch.setattr(shutil, "copyfile", real)
    assert r["applied"] is False and "rolled back" in r["reason"]
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 1\n"


def test_what_the_owner_approved_is_what_is_applied(tmp_path, monkeypatch):
    """C541, 9 Nov: the approval keeps each file's hash; a sandbox changed after the proposal is not applied."""
    live, cfg = _setup(tmp_path, monkeypatch)
    box = tmp_path / "sandboxes" / "fix1"
    seen = agt_change.fingerprint(box, ["sys/core/aurora/a.py"])
    (box / "sys/core/aurora/a.py").write_text("a = 3  # written after the owner looked\n")
    r = agt_change.apply("fix1", lambda *a: None, cfg, restart=False, expect=seen)
    assert r["applied"] is False and "propose it again" in r["reason"]
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 1\n"
    r = agt_change.apply("fix1", lambda *a: None, cfg, restart=False,
                         expect=agt_change.fingerprint(box, ["sys/core/aurora/a.py"]))
    assert r["applied"] is True and (live / "sys/core/aurora/a.py").read_text().startswith("a = 3")
