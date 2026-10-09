# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Command cards (roadmap 74) and updates on systems an installer builds (the Windows VM, 9 Oct: «not a git
repository» at every check, so an update was never proposed there)."""
import json
import subprocess

from aurora import sys_commands as C
from aurora import sys_ethics, sys_update


def git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


def test_linux_commands_and_a_ports_own(cfg):
    assert C.command(cfg, "update") == f"cd {cfg.root} && git pull --ff-only && bash install.sh"
    assert C.by_hand(cfg)                                              # the test root is not a clone
    status = cfg.path("AURORA_STATUS_DIR")
    status.mkdir(parents=True, exist_ok=True)
    src = cfg.root / "clone"
    (src / ".git").mkdir(parents=True)
    (status / "commands.json").write_text(json.dumps({
        "source": str(src), "by_hand": True,
        "update": "Set-Location '{source}'; git pull --ff-only; powershell -ExecutionPolicy Bypass -File Aurora_windows\\install.ps1"}))
    assert C.source(cfg) == src and C.command(cfg, "update").startswith(f"Set-Location '{src}'")
    assert C.command(cfg, "sign").endswith("sys_ethics_sign.py sign")       # not given by the port: Linux's


def test_an_update_with_protected_files_becomes_a_card_and_is_checked(cfg, monkeypatch):
    monkeypatch.setattr(sys_ethics, "code_drift", lambda: {"changed": [], "added": [], "removed": []})
    st = cfg.path("AURORA_STATUS_DIR") / "update"
    st.mkdir(parents=True, exist_ok=True)
    (st / "last_check.json").write_text(json.dumps({"behind": 3, "protected": ["sys/core/aurora/plg_host.py"]}))
    cards = C.cards(cfg, "it")
    assert [c["id"] for c in cards] == ["update"] and "plg_host.py" in cards[0]["text"]
    monkeypatch.setattr(sys_update, "check", lambda c: {"behind": 0})
    assert C.verify(cfg, "update") == {"done": True, "behind": 0, "error": None}


def test_unsigned_protected_code_gets_the_sign_card(cfg, monkeypatch):
    monkeypatch.setattr(sys_ethics, "code_drift", lambda: {"changed": ["sys/core/aurora/plg_host.py", "x.py"],
                                                           "added": [], "removed": []})
    cards = C.cards(cfg, "en")
    assert [c["id"] for c in cards] == ["sign"] and cards[0]["admin"] and "plg_host.py" in cards[0]["text"]
    assert "x.py" not in cards[0]["text"]                                 # only the code of conduct's own files


def test_the_webui_never_applies_an_update_an_installer_must(cfg):
    out = sys_update.apply(cfg)
    assert not out["applied"] and "installer" in out["reason"]


def test_a_port_checks_its_updates_in_the_clone_it_was_built_from(cfg, tmp_path):
    origin, src = tmp_path / "origin", tmp_path / "src"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "a.txt").write_text("1")
    git(origin, "add", "a.txt")
    git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one")
    git(tmp_path, "clone", "-q", str(origin), str(src))
    (origin / "a.txt").write_text("2")
    git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "two")
    status = cfg.path("AURORA_STATUS_DIR")
    status.mkdir(parents=True, exist_ok=True)
    (status / "commands.json").write_text(json.dumps({"source": str(src), "by_hand": True}))
    cfg.values.update(AURORA_UPDATE_REMOTE="origin", AURORA_UPDATE_BRANCH="main")
    info = sys_update.check(cfg)
    assert info.get("behind") == 1 and info["commits"][0]["subject"] == "two", info
