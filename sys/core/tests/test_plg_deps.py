# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugins that bring their program (plg_deps, ROADMAP 101): into the plugin's own folder, checked, removed whole."""
import contextlib
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import plg_deps

RUN = Path(__file__).resolve().parents[1] / "script" / "plg_run.py"
BLOB = b"#!/bin/sh\necho hello\n"


def _manifest(sha=hashlib.sha256(BLOB).hexdigest(), python=()):
    return {"install": {"python": list(python), "programs": [{"name": "tool", "url": "https://x/tool", "sha256": sha}]}}


class _Resp:
    def raise_for_status(self):
        pass

    def iter_bytes(self, n):
        yield BLOB


def _fake_web(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: contextlib.nullcontext(_Resp()))


def test_a_program_checked_installed_and_removed_whole(tmp_path, monkeypatch):
    _fake_web(monkeypatch)
    m = _manifest()
    assert plg_deps.state(tmp_path, m)["installed"] is False
    st = plg_deps.install(tmp_path, m)
    assert st["installed"] and (tmp_path / ".bin" / "tool").read_bytes() == BLOB and st["bytes"] > len(BLOB)
    assert plg_deps.uninstall(tmp_path) > 0 and sorted(p.name for p in tmp_path.iterdir()) == []


def test_a_wrong_checksum_installs_nothing(tmp_path, monkeypatch):
    _fake_web(monkeypatch)
    with pytest.raises(RuntimeError, match="SHA-256"):
        plg_deps.install(tmp_path, _manifest(sha="0" * 64))
    assert sorted(p.name for p in tmp_path.iterdir()) == []                 # nothing left behind


def test_the_libraries_go_with_their_hashes_into_the_plugin_folder(tmp_path, monkeypatch):
    seen = {}

    def pip(cmd, **k):
        seen["cmd"] = cmd
        target = Path(cmd[cmd.index("--target") + 1])
        (target / "demo_lib").mkdir(parents=True)
        (target / "demo_lib" / "__init__.py").write_text("VALUE = 42\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(plg_deps.subprocess, "run", pip)
    m = {"install": {"python": ["demo-lib==1.0 --hash=sha256:" + "a" * 64]}}
    st = plg_deps.install(tmp_path, m)
    assert "--require-hashes" in seen["cmd"] and str(tmp_path) in seen["cmd"][seen["cmd"].index("--target") + 1]
    assert st["installed"] and (tmp_path / ".deps" / "demo_lib").is_dir()
    monkeypatch.undo()                                 # the real subprocess again, for the launcher
    # the launcher puts them first, in the plugin's process only
    (tmp_path / "helper.py").write_text("PLUS = 1\n")                 # a sibling module of the plugin (C309)
    (tmp_path / "server.py").write_text("import demo_lib, helper\nprint(demo_lib.VALUE + helper.PLUS - 1)\n")
    out = subprocess.run([sys.executable, str(RUN), "server.py"], cwd=tmp_path, capture_output=True, text=True)
    assert out.stdout.strip() == "42"
    with pytest.raises(ImportError):
        import demo_lib  # noqa: F401 — never in Aurora's own process


def test_a_plugin_without_needs_is_installed_as_it_is(tmp_path):
    st = plg_deps.state(tmp_path, {"command": ["{python}", "server.py"]})
    assert st["installed"] and not st["wanted"]


def test_the_qr_plugin_declares_a_pinned_hashed_library():
    import json
    m = json.loads((Path(__file__).resolve().parents[2] / "plugins" / "qr" / "plugin.json").read_text())
    req = plg_deps.needs(m)["python"]
    assert req and all("==" in r and "--hash=sha256:" in r for r in req)
    assert m["command"][1].endswith("sys/core/script/plg_run.py")
