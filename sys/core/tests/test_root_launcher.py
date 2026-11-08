# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-root (sys_root.py, 9 Nov): root signs, copies and installs only the bytes the owner signed, from root's own
folder; what changed is asked first; a link in the code base is refused."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import sys_root as R  # noqa: E402
from aurora import sys_ethics  # noqa: E402


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    root = tmp_path / "aurora"
    for f in (*sys_ethics.PROTECTED, "sys/core/aurora/x.py", "sys/core/script/sys_root.py",
              "sys/deploy/systemd/install.sh", "sys/deploy/systemd/aurora-api.service", "install.sh"):
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {f}\n")
    (root / "sys/deploy/systemd/install.sh").write_text('#!/usr/bin/env bash\ncp "$AURORA_DEPLOY/aurora-api.service" '
                                                         '"$INSTALL_ROOT/installed.service"\n')
    key = Ed25519PrivateKey.generate()
    pem = tmp_path / "owner_ed25519"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(sys_ethics, "PRIVATE_KEY", pem)
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: (pub, ""))
    monkeypatch.setattr(R, "REPO", root)
    monkeypatch.setattr(R, "LIB", tmp_path / "lib" / "aurora")
    monkeypatch.setattr(R, "CONF", tmp_path / "etc" / "root.conf")
    monkeypatch.setattr(R, "SHIM", tmp_path / "sbin" / "aurora-root")
    (tmp_path / "sbin").mkdir()
    import types
    monkeypatch.setitem(sys.modules, "sys_root_sync", types.SimpleNamespace(never_list=lambda: [], write_never=lambda n: None))
    return root


def test_signs_what_changed_then_copies_only_the_signed_bytes(repo):
    snap = R.snapshot()
    assert R.drift(snap)["unsigned"]                                   # nothing signed yet
    assert R.sign(snap, yes=True)
    assert not any(R.drift(R.snapshot())[k] for k in ("changed", "added", "removed"))
    assert R.sync_lib(R.snapshot()) == 8                               # the package (7) and the launcher, nothing else
    assert not (R.LIB / "install.sh").exists() and not (R.LIB / "sys/deploy").exists()
    assert (R.LIB / "sys/core/aurora/x.py").read_text() == "# sys/core/aurora/x.py\n"
    assert R.CONF.read_text() == f"{repo}\n" and "sys_root.py" in R.SHIM.read_text()
    (repo / "sys/core/aurora/x.py").write_text("changed by the services' account\n")
    d = R.drift(R.snapshot())
    assert d["changed"] == ["sys/core/aurora/x.py"] and not d["protected"]
    with pytest.raises(SystemExit):
        R.sync_lib(R.snapshot())                                       # not as signed: root's copy left as it was
    assert (R.LIB / "sys/core/aurora/x.py").read_text() == "# sys/core/aurora/x.py\n"


def test_an_install_runs_from_roots_copy_and_waits_for_the_signature(repo, monkeypatch):
    R.sign(R.snapshot(), yes=True)
    (repo / "sys/deploy/systemd/aurora-api.service").write_text("[Service]\nUser=root\n")    # planted
    monkeypatch.setattr(R.sys.stdin, "isatty", lambda: False)
    assert R.install("systemd", [], yes=False) == 1                    # nobody said yes: nothing installed
    assert not (repo / "installed.service").exists()
    assert R.install("systemd", [], yes=True) == 0                     # the owner signs what he saw, then it runs
    assert (repo / "installed.service").read_text() == "[Service]\nUser=root\n"


def test_a_link_in_the_code_base_is_refused(repo, tmp_path):
    secret = tmp_path / "shadow"
    secret.write_text("root's")
    (repo / "sys/core/aurora/y.py").symlink_to(secret)
    with pytest.raises(SystemExit):
        R.snapshot()


def test_root_never_writes_through_a_link(repo, tmp_path):
    target = tmp_path / "victim"
    target.write_text("intact")
    (repo / sys_ethics.MANIFEST).symlink_to(target)
    R.sign(R.snapshot(), yes=True)                                     # the manifest written beside, by a rename
    assert target.read_text() == "intact" and not (repo / sys_ethics.MANIFEST).is_symlink()
    assert json.loads((repo / sys_ethics.MANIFEST).read_text())["code_signature"]
