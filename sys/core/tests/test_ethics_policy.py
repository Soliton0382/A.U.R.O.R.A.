# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Level B per user (N138): the admin proposes, root signs; only rules 7 and 9, only for the users named."""
import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aurora import sys_approvals, sys_ethics


@pytest.fixture
def root(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: (pub, ""))
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: False)
    (tmp_path / "sys/core/ethics").mkdir(parents=True)
    sys_ethics._policy_cached.cache_clear()

    KEY[:] = [key]
    return tmp_path


KEY = []


def sign(root):
    """What `aurora-root sign` does here: the code list, with the policy as it is now, signed."""
    code = {sys_ethics.POLICY: sys_ethics._sha(root / sys_ethics.POLICY)} if (root / sys_ethics.POLICY).exists() else {}
    (root / sys_ethics.MANIFEST).write_text(json.dumps({"files": {}, "signature": "", "code": code,
                                                        "code_signature": KEY[0].sign(sys_ethics._canonical(code)).hex()}))


def _cfg(root, user):
    return SimpleNamespace(root=root, user=user)


class _Cfg(dict):
    """A user's configuration: their settings, their name, the installation's folder."""
    def __init__(self, root, user, confirm=True):
        super().__init__(AURORA_CONFIRM_EXTERNAL_ACTIONS=confirm, AURORA_SOCIAL_AUTONOMY=False)
        self.root, self.user = root, user


def test_a_proposal_holds_nothing_until_root_signs_it(root):
    sys_ethics.propose_policy({"lab": ["level_b"]}, root)
    assert not sys_ethics.lifted("confirm_external", _cfg(root, "lab"))      # proposed, not signed
    sign(root)
    assert sys_ethics.lifted("confirm_external", _cfg(root, "lab"))
    assert sys_ethics.lifted("private_cloud", _cfg(root, "lab"))
    assert not sys_ethics.lifted("confirm_external", _cfg(root, "office"))   # only the users named


def test_a_change_after_the_signature_voids_every_lift(root):
    sys_ethics.propose_policy({"lab": ["level_b"]}, root)
    sign(root)
    sys_ethics.propose_policy({"lab": ["level_b"], "other": ["level_b"]}, root)
    assert not sys_ethics.lifted("confirm_external", _cfg(root, "lab"))      # level B holds again until signed
    assert sys_ethics.proposed_policy(root) == {"lab": ["level_b"], "other": ["level_b"]}


def test_only_the_ceiling_of_rules_7_and_9_never_6_8_or_level_a(root):
    sys_ethics.propose_policy({"lab": ["level_b", "self_change", "malware"]}, root)
    sign(root)
    assert sys_ethics.signed_policy(root) == {"lab": ["level_b"]}
    for rule in ("self_change", "disclosure", "malware"):
        assert not sys_ethics.lifted(rule, _cfg(root, "lab"))


def test_odd_names_are_dropped(root):
    assert sys_ethics.propose_policy({"../x": ["level_b"], "": ["level_b"], "ok": "level_b", "no": ["private_cloud"]}, root) == {}


def test_the_machine_exemption_lifts_the_ceiling_for_everyone(root, monkeypatch):
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: True)
    assert sys_ethics.lifted("confirm_external", _cfg(root, "anyone"))
    assert not sys_ethics.lifted("self_change", _cfg(root, "anyone"))       # rule 8 is the exemption's, not lifted()


def test_lifted_the_users_own_autonomy_decides(root):
    sys_ethics.propose_policy({"lab": ["level_b"]}, root)
    sign(root)
    assert sys_approvals.needs_owner("external", _Cfg(root, "lab", confirm=False)) is False   # 🚀 and lifted: alone
    assert sys_approvals.needs_owner("external", _Cfg(root, "lab", confirm=True)) is True     # lifted but 🤝: asks
    assert sys_approvals.needs_owner("external", _Cfg(root, "office", confirm=False)) is True  # 🚀 under the ceiling
    assert sys_approvals.needs_owner("code_change", _Cfg(root, "lab", confirm=False)) is True  # rule 8: the machine's


def test_the_external_area_is_each_users_own():
    from aurora import sys_autonomy
    assert sys_autonomy.AREAS["external"][0] == "user"


def test_the_policy_is_local_and_signed_with_the_code():
    assert "/local/" in sys_ethics.POLICY
    assert sys_ethics._is_code(sys_ethics.POLICY, set())
