# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each user's own models step by step (ROADMAP 106, 9 Nov): only when the admin's policy allows it, only providers
the user's account reaches, the admin's choice untouched and still everyone's start."""
import dataclasses
import os
import stat

import pytest

from aurora import mdl_accounts as A, mdl_router as R, mdl_user_roles as U


def users(cfg, monkeypatch):
    monkeypatch.setattr(A, "_admin", lambda c: "boss")
    return dataclasses.replace(cfg, user="anna", base=cfg), dataclasses.replace(cfg, user="boss", base=cfg)


def test_a_user_chooses_their_steps_only_when_the_admin_allows_it(cfg, monkeypatch):
    anna, boss = users(cfg, monkeypatch)
    R.set_assignments(cfg, {"synthesis": {"provider": "local", "model": ""}})
    assert not U.allowed(anna) and not U.allowed(boss)                      # «shared» (the default); the admin never
    with pytest.raises(PermissionError):
        U.set_mine(anna, {"synthesis": {"provider": "local"}})
    A.set_policy(cfg, "own")
    with pytest.raises(ValueError, match="no account of yours"):
        U.set_mine(anna, {"synthesis": {"provider": "openai", "model": "gpt-x"}})
    A.add(cfg, "openai", "user", "anna", key="sk-anna-0002")
    U.set_mine(anna, {"synthesis": {"provider": "openai", "model": "gpt-x"}})
    assert R.assignments(anna)["synthesis"] == {"provider": "openai", "model": "gpt-x"}    # her calls, her model
    assert R.assignments(anna)["route"] == R.assignments(boss)["route"]                   # the rest: the admin's
    assert R.assignments(boss)["synthesis"]["provider"] == "local"                        # the admin's untouched
    assert stat.S_IMODE(os.stat(U._file(anna, "anna")).st_mode) == 0o600
    with pytest.raises(ValueError, match="not a step"):
        U.set_mine(anna, {"forge_write": {"provider": "local"}})                         # the forge: the admin's
    R.set_assignments(cfg, {"route": {"provider": "local", "model": "x"}})                # the admin saves the page:
    assert R.assignments(anna)["synthesis"]["provider"] == "openai"                       # her choice not taken in
    assert "synthesis" not in json_of(cfg)
    A.set_policy(cfg, "shared")                                                           # back to one for all
    assert R.assignments(anna)["synthesis"]["provider"] == "local" and U._file(anna, "anna").exists()   # kept, unused
    A.set_policy(cfg, "own")
    U.set_mine(anna, {"synthesis": None})                                                 # one step back
    assert R.assignments(anna)["synthesis"]["provider"] == "local"
    U.set_mine(anna, {"verify": {"provider": "local"}})
    U.reset(anna)
    assert U.mine(anna) == {}


def json_of(cfg):
    import json
    return {k: v for k, v in json.loads((R._dir(cfg) / "roles.json").read_text()).items() if v.get("provider") != "local"}
