# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A change from a sandbox is what was done in the sandbox, never a revert of what moved in the live code (C145)."""
import shutil

from aurora import agt_change


def _tree(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


def test_only_the_files_changed_in_the_sandbox_count_and_a_live_change_is_a_conflict(tmp_path):
    live, box = tmp_path / "live", tmp_path / "box"
    _tree(live, {"sys/core/aurora/a.py": "a = 1\n", "sys/core/aurora/b.py": "b = 1\n"})
    shutil.copytree(live / "sys/core", box / "sys/core")
    shutil.copytree(box / "sys/core", box / ".base/sys/core")            # as the self plugin makes a sandbox
    (live / "sys/core/aurora/b.py").write_text("b = 2  # an update after the sandbox was made\n")
    (box / "sys/core/aurora/a.py").write_text("a = 10  # the repair\n")
    files = agt_change.changed_files(box, live)
    assert files == ["sys/core/aurora/a.py"]                              # b.py is not reverted to its old text
    assert agt_change.conflicts(box, live, files) == []
    (live / "sys/core/aurora/a.py").write_text("a = 3  # the live code moved on here too\n")
    assert agt_change.conflicts(box, live, files) == ["sys/core/aurora/a.py"]


def test_an_older_sandbox_without_its_base_is_compared_with_the_live_code(tmp_path):
    live, box = tmp_path / "live", tmp_path / "box"
    _tree(live, {"sys/core/aurora/a.py": "a = 1\n"})
    _tree(box, {"sys/core/aurora/a.py": "a = 2\n"})
    assert agt_change.changed_files(box, live) == ["sys/core/aurora/a.py"] and agt_change.conflicts(box, live, ["x"]) == []
