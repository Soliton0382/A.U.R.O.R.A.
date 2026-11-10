# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aurora import sys_approvals, sys_disclosure, sys_ethics


@pytest.fixture
def signed(tmp_path, monkeypatch):
    """A fake installation with the protected files, signed by a test key."""
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: (pub, ""))
    for f in sys_ethics.PROTECTED:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text(f"content of {f}\n")
    files = {f: sys_ethics._sha(tmp_path / f) for f in sys_ethics.PROTECTED}
    (tmp_path / sys_ethics.MANIFEST).write_text(json.dumps({"files": files, "signature": key.sign(sys_ethics._canonical(files)).hex()}))
    return tmp_path, key


def test_intact_then_tampered(signed):
    root, _ = signed
    assert sys_ethics.integrity(root) == (True, "intact")
    (root / "sys/core/ethics/CODE.md").write_text("no rules\n")
    ok, reason = sys_ethics.integrity(root)
    assert not ok and "CODE.md" in reason


def test_the_daily_seed_is_data_not_signed_code(signed):
    """C401: the seed's timer rewrites it every day; a manifest signed before still lists it, and that is no drift."""
    root, key = signed
    seed, code_file = root / sys_ethics.DATA_FILES[0], root / "sys/core/aurora/x.py"
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text("[]\n")
    code_file.write_text("x = 1\n")
    code = {f: sys_ethics._sha(root / f) for f in [*sys_ethics.code_files(root), sys_ethics.DATA_FILES[0]]}
    m = json.loads((root / sys_ethics.MANIFEST).read_text())
    m.update(code=code, code_signature=key.sign(sys_ethics._canonical(code)).hex())
    (root / sys_ethics.MANIFEST).write_text(json.dumps(m))
    assert sys_ethics.DATA_FILES[0] not in sys_ethics.code_files(root)
    seed.write_text('[{"question": "new"}]\n')
    assert sys_ethics.code_drift(root) == {"changed": [], "added": [], "removed": []}
    code_file.write_text("x = 2\n")
    assert sys_ethics.code_drift(root)["changed"] == ["sys/core/aurora/x.py"]


def test_the_signature_covers_behaviour_files_and_a_plugins_sub_folders(signed):
    """C558: allowed_signers, *.mjs, the locks, .github and a plugin's sub-folders are signed; what the services write
    (a plugin's .deps/.bin, __pycache__, the daily seed) and Aurora's forged plugins are not — in code_files and in
    unsigned_plugins alike."""
    root, key = signed
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    covered = ["sys/core/webui/vendor/qr/qr.mjs", "sys/core/config/allowed_signers", "requirements.lock", "pyproject.toml",
               ".github/workflows/ci.yml", "sys/plugins/mine/plugin.json", "sys/plugins/mine/lib/helper.py"]
    outside = ["sys/plugins/mine/.deps/segno/__init__.py", "sys/plugins/mine/.bin/tool/usr/bin/tool",
               "sys/plugins/mine/__pycache__/server.cpython-312.pyc", "sys/plugins/mine/lib/__pycache__/h.pyc",
               "sys/plugins/sly/plugin.json", "sys/plugins/sly/sub/a.py", sys_ethics.DATA_FILES[0]]
    for f in covered + outside:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text(f"# {f}\n")
    (root / "sys/plugins/mine/plugin.json").write_text(json.dumps({"name": "mine"}))
    (root / "sys/plugins/sly/plugin.json").write_text(json.dumps({"name": "sly", "forged": {"request": "r"}}))
    files = sys_ethics.code_files(root)
    assert all(f in files for f in covered) and not any(f in files for f in outside)
    code = {f: sys_ethics._sha(root / f) for f in files}
    m = json.loads((root / sys_ethics.MANIFEST).read_text())
    m.update(code=code, code_signature=key.sign(sys_ethics._canonical(code)).hex())
    (root / sys_ethics.MANIFEST).write_text(json.dumps(m))
    sys_ethics._unsigned_cache.clear()
    assert sys_ethics.unsigned_plugins(root, pub) == set()
    assert sys_ethics.code_drift(root, pub) == {"changed": [], "added": [], "removed": []}
    (root / "sys/plugins/mine/.deps/segno/__init__.py").write_text("# reinstalled by plg_deps\n")   # a service's write
    (root / "sys/plugins/sly/sub/a.py").write_text("# Aurora's own, under contract\n")
    sys_ethics._unsigned_cache.clear()
    assert sys_ethics.unsigned_plugins(root, pub) == set()
    assert sys_ethics.code_drift(root, pub) == {"changed": [], "added": [], "removed": []}
    (root / "sys/plugins/mine/lib/helper.py").write_text("# changed in a sub-folder\n")
    sys_ethics._unsigned_cache.clear()
    assert sys_ethics.unsigned_plugins(root, pub) == {"mine"}
    assert sys_ethics.code_drift(root, pub)["changed"] == ["sys/plugins/mine/lib/helper.py"]


def test_a_manifest_signed_by_another_key_is_refused(signed):
    root, _ = signed
    other = Ed25519PrivateKey.generate()
    m = json.loads((root / sys_ethics.MANIFEST).read_text())
    m["signature"] = other.sign(sys_ethics._canonical(m["files"])).hex()
    (root / sys_ethics.MANIFEST).write_text(json.dumps(m))
    assert sys_ethics.integrity(root) == (False, "the manifest signature is not the owner's")


def test_level_b_holds_without_the_owners_exemption(cfg, signed, monkeypatch):
    _, key = signed
    cfg.values["AURORA_CONFIRM_EXTERNAL_ACTIONS"] = False
    cfg.values["AURORA_FORGE_MODE"] = "auto"
    cfg.values["AURORA_AI_DISCLOSURE"] = False
    assert sys_approvals.needs_owner("external", cfg) and sys_approvals.needs_owner("code_change", cfg)
    assert sys_disclosure.mark_text("post", "it", cfg).endswith(cfg["AURORA_AI_DISCLOSURE_IT"])
    ex = cfg.path("AURORA_ETHICS_EXEMPTION")
    ex.parent.mkdir(parents=True, exist_ok=True)
    ex.write_text(key.sign(sys_ethics.exemption_message(cfg.root)).hex())
    sys_ethics._exempt_cached.cache_clear()
    assert sys_ethics.exempt(cfg)                                  # the owner's machine: .env decides
    assert not sys_approvals.needs_owner("external", cfg) and sys_disclosure.mark_text("post", "it", cfg) == "post"
    ex.write_text(Ed25519PrivateKey.generate().sign(sys_ethics.exemption_message(cfg.root)).hex())
    sys_ethics._exempt_cached.cache_clear()
    assert not sys_ethics.exempt(cfg)                              # forged by someone else: refused


def test_level_a_capabilities_are_refused():
    assert sys_ethics.forbidden_capabilities({"capabilities": ["read_logs", "person_lookup", "exploit"]}) == ["exploit", "person_lookup"]
    assert sys_ethics.forbidden_capabilities({"capabilities": ["ip_reputation"]}) == []


@pytest.mark.skipif(os.name == "nt", reason="chmod and root: Windows's ACL test is test_platform_windows (recorded ACLs)")
def test_a_key_the_user_can_write_is_not_trusted(tmp_path):
    pub = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    f = tmp_path / "owner_ed25519.pub"
    f.write_text(pub + "\n")
    key, problem = sys_ethics.owner_public_key(f)                  # owned by the test user, not by root
    assert key == "" and "root" in problem
    key, problem = sys_ethics.owner_public_key(tmp_path / "missing" / "k.pub")
    assert key == "" and "setup" in problem


def test_without_a_trusted_key_nothing_is_intact_or_exempt(cfg, signed, monkeypatch):
    root, key = signed
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: ("", "no owner key"))
    assert sys_ethics.integrity(root) == (False, "no owner key")
    ex = cfg.path("AURORA_ETHICS_EXEMPTION")
    ex.parent.mkdir(parents=True, exist_ok=True)
    ex.write_text(key.sign(sys_ethics.exemption_message(cfg.root)).hex())
    sys_ethics._exempt_cached.cache_clear()
    assert not sys_ethics.exempt(cfg)
