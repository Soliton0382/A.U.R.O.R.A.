# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C749: the phone app is built and signed with the real key only from the owner's signed sources, with tools and a
key nobody else may write — an Aurora misled could otherwise change the app or a program of its build."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _build(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("app_build", ROOT / "sys" / "app" / "build.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    app = tmp_path / "sys" / "app"
    (app / "android" / "java").mkdir(parents=True)
    (app / "android" / "java" / "Main.java").write_text("class Main {}")
    (app / "build.py").write_text("# build")
    for d in ("tools/jdk/bin", "tools/sdk/build-tools", "keys"):
        (app / d).mkdir(parents=True)
    (app / "tools" / "jdk" / "bin" / "javac").write_text("#!/bin/sh")
    (app / "keys" / "aurora-app.jks").write_text("k")
    os.chmod(app / "keys", 0o700)
    os.chmod(app / "keys" / "aurora-app.jks", 0o600)
    for d in (app / "tools", app / "tools" / "jdk", app / "tools" / "jdk" / "bin", app / "tools" / "sdk",
              app / "tools" / "sdk" / "build-tools"):
        os.chmod(d, 0o755)
    os.chmod(app / "tools" / "jdk" / "bin" / "javac", 0o755)
    monkeypatch.setattr(b, "ROOT", app)
    monkeypatch.setattr(b, "APP", app / "android")
    monkeypatch.setattr(b, "TOOLS", app / "tools")
    monkeypatch.setattr(b, "KEYS", app / "keys")
    from aurora import sys_ethics
    signed = {f"sys/app/{r}": sys_ethics._sha(app / r) for r in ("build.py", "android/java/Main.java")}
    (tmp_path / sys_ethics.MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / sys_ethics.MANIFEST).write_text(json.dumps({"code": signed, "code_signature": "ok"}))
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: ("pub", ""))
    monkeypatch.setattr(sys_ethics, "_verify", lambda msg, sig, pub: sig == "ok")
    return b, app


def test_signed_sources_and_own_tools_are_trusted(tmp_path, monkeypatch):
    b, app = _build(tmp_path, monkeypatch)
    assert b.trusted() == []


def test_a_changed_source_or_a_writable_tool_stops_the_build(tmp_path, monkeypatch):
    b, app = _build(tmp_path, monkeypatch)
    (app / "android" / "java" / "Main.java").write_text("class Main { /* changed by someone */ }")
    assert any("Main.java is not the signed one" in p for p in b.trusted())
    b, app = _build(tmp_path / "again", monkeypatch)
    os.chmod(app / "tools" / "jdk" / "bin" / "javac", 0o775)                       # the group may write a program
    assert any("tools/jdk is writable by others" in p for p in b.trusted())
    b, app = _build(tmp_path / "third", monkeypatch)
    os.chmod(app / "keys" / "aurora-app.jks", 0o640)                               # the key readable by the group
    assert any("keys is writable by others or not yours" in p for p in b.trusted())


def test_the_app_s_sources_are_under_the_owner_s_signature():
    from aurora import sys_ethics
    assert "sys/app/build.py" in sys_ethics.CODE_PATTERNS and "sys/app/android/**/*" in sys_ethics.CODE_PATTERNS
