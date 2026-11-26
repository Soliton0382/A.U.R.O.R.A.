# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""evd_root's walk of the archive's folders (run by root): never led out of the tree by a link."""
import importlib.util
import os
import stat
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "evd_root.py"


def _load():
    spec = importlib.util.spec_from_file_location("evd_root", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_folder_swapped_for_a_link_during_the_walk_is_not_followed(tmp_path, monkeypatch):
    """Audit E7 (B22): os.walk went by path; a folder replaced by a link between the listing and the descent took
    root's fchown and fchmod outside the tree."""
    root = _load()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x")
    os.chmod(outside / "secret", 0o600)
    top = tmp_path / "data"
    (top / "sub").mkdir(parents=True)
    (top / "sub" / "f").write_text("y")
    (top / "link").symlink_to(outside)
    real = root._fix

    def swap(p, st, gid, dir_fd=None):                  # the service's move, right after the folder is fixed
        real(p, st, gid, dir_fd)
        if p == "sub":
            os.rename(top / "sub", tmp_path / "moved")
            (top / "sub").symlink_to(outside)
    monkeypatch.setattr(root, "_fix", swap)
    root.own(top, os.getgid())
    assert stat.S_IMODE((outside / "secret").stat().st_mode) == 0o600            # untouched: never reached
    assert stat.S_IMODE((top / "link").lstat().st_mode) == 0o777 and (outside / "secret").exists()
