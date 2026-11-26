# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Groups and access (27 Nov): the admin always may; a plugin open by default, an add-on the admin's; a rule lets in
everyone, the users listed or the members of the groups listed; a removed group leaves every rule; bad names refused;
Evidentia cannot be opened to others while it keeps one archive."""
from pathlib import Path

import pytest

from aurora import sys_users_groups as G


def test_defaults_and_the_admin(cfg):
    assert G.may_use(cfg, "anna", "plugin:weather", "boss") and not G.may_use(cfg, "anna", "addon:evidentia", "boss")
    assert G.may_use(cfg, "boss", "addon:evidentia", "boss") and not G.may_use(cfg, None, "plugin:weather", "boss")


def test_by_user_by_group_and_for_everyone(cfg):
    G.set_group(cfg, "legale", ["anna", "bruno"])
    G.set_access(cfg, "plugin:email", False, ["carla"], ["legale"])
    assert G.may_use(cfg, "anna", "plugin:email", "boss") and G.may_use(cfg, "carla", "plugin:email", "boss")
    assert not G.may_use(cfg, "dario", "plugin:email", "boss")
    G.set_access(cfg, "plugin:email", True, [], [])
    assert G.may_use(cfg, "dario", "plugin:email", "boss")
    assert G.groups_of(cfg, "anna") == ["legale"]


def test_a_removed_group_leaves_the_rules_and_bad_input_is_refused(cfg):
    G.set_group(cfg, "ricerca", ["anna"])
    G.set_access(cfg, "plugin:notes", False, [], ["ricerca"])
    G.set_group(cfg, "ricerca", None)
    assert G.load(cfg)["access"]["plugin:notes"]["groups"] == [] and not G.may_use(cfg, "anna", "plugin:notes", "boss")
    with pytest.raises(ValueError):
        G.set_group(cfg, "Bad Name", [])
    with pytest.raises(ValueError):
        G.set_access(cfg, "nessuna_funzione", True, [], [])
    with pytest.raises(ValueError):
        G.set_access(cfg, "plugin:notes", False, [], ["nessuno"])


def test_the_agent_and_the_routes_use_the_rules():
    root = Path(__file__).resolve().parents[1]
    loop = (root / "aurora" / "agt_loop.py").read_text(encoding="utf-8")
    assert 'sys_users_groups.may_use_now(self.cfg, f"plugin:{p.name}")' in loop
    api = (root.parent / "evidentia" / "addon" / "api_evidentia.py").read_text(encoding="utf-8")
    assert 'USE = may_use("addon:evidentia")' in api and api.count("Depends(USE)") == 10   # + the NAS (2) and people (1), 27 Nov
    users = (root / "aurora" / "api" / "users.py").read_text(encoding="utf-8")
    assert "sys_addons.PER_USER.get(name, True)" in users          # one archive: not opened to others yet
