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
