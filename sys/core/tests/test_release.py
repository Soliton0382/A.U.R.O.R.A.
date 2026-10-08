# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Releases (owner, 2026-10-08: «manca anche la questione delle release»): a version's section of CHANGELOG.md from the
published history since the last tag, pyproject.toml set, a lower or repeated version refused; release.yml finds the
section; the workflows are valid and run what exists."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")              # pyyaml comes with the lock, not asked by Aurora itself

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "sys" / "core" / "script" / "dev_changelog.py"


def _git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                           "-c", "tag.gpgsign=false", *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "Aurora"
    (root / "sys" / "core" / "script").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "sys" / "core" / "script" / SCRIPT.name)
    (root / "pyproject.toml").write_text('[project]\nname = "aurora"\nversion = "0.1.0"\n', encoding="utf-8")
    mirror = tmp_path / "Aurora_git"
    mirror.mkdir()
    _git(mirror, "init", "-q", "-b", "main")
    for msg in ("first public version", "C1 a fix"):
        (mirror / "f").write_text(msg)
        _git(mirror, "add", "f")
        _git(mirror, "commit", "-q", "-m", msg)
    return root, mirror


def _run(root, mirror, version, msg="the release"):
    return subprocess.run([sys.executable, str(root / "sys/core/script/dev_changelog.py"), str(mirror), version, msg],
                          capture_output=True, text=True)


def _notes(text: str, tag: str) -> str:
    """What release.yml does (the same expression)."""
    m = re.search(rf"^## {re.escape(tag)}\b.*?$(.*?)(?=^## v|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def test_a_version_is_the_history_since_the_last_tag(setup):
    root, mirror = setup
    r = _run(root, mirror, "0.2.0", "calendar")
    assert r.returncode == 0, r.stderr
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert 'version = "0.2.0"' in (root / "pyproject.toml").read_text()
    notes = _notes(text, "v0.2.0")
    assert "calendar" in notes and "C1 a fix" in notes and "first public version" in notes and "first tagged" in notes
    _git(mirror, "tag", "v0.2.0")
    (mirror / "f").write_text("later")
    _git(mirror, "commit", "-qam", "C2 after the tag")
    assert _run(root, mirror, "0.3.0", "more").returncode == 0
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    new = _notes(text, "v0.3.0")
    assert "C2 after the tag" in new and "C1 a fix" not in new and "since v0.2.0" in new
    assert "C1 a fix" in _notes(text, "v0.2.0") and text.index("## v0.3.0") < text.index("## v0.2.0")


def test_a_version_not_above_or_already_tagged_is_refused(setup):
    root, mirror = setup
    assert _run(root, mirror, "0.1.0").returncode != 0
    assert _run(root, mirror, "0.0.9").returncode != 0
    assert _run(root, mirror, "1.0").returncode != 0
    _git(mirror, "tag", "v0.5.0")
    r = _run(root, mirror, "0.5.0")
    assert r.returncode != 0 and "already" in (r.stderr + r.stdout)
    assert 'version = "0.1.0"' in (root / "pyproject.toml").read_text() and not (root / "CHANGELOG.md").exists()


def test_the_workflows_are_valid_and_the_release_checks_the_signature():
    wf = ROOT / ".github" / "workflows"
    ports, rel = (yaml.safe_load((wf / f).read_text(encoding="utf-8")) for f in ("ports.yml", "release.yml"))
    on = ports.get("on") or ports.get(True)                       # YAML 1.1 reads a bare `on` as True
    assert "workflow_dispatch" in on and on["push"]["tags"] == ["v*"]
    assert {m["port"] for m in ports["jobs"]["port"]["strategy"]["matrix"]["include"]} == {"Aurora_mac", "Aurora_windows"}
    steps = "\n".join(s.get("run", "") for s in rel["jobs"]["release"]["steps"])
    assert "verify-tag" in steps and "allowed_signers" in steps and "CHANGELOG.md" in steps
    assert (ROOT / "sys/core/config/allowed_signers").exists()
    assert rel["permissions"] == {"contents": "write"} and ports["permissions"] == {"contents": "read"}
