# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C280: a benchmark's models travel with its questions; the owner's choice (roles.json) never changes."""
import contextvars
import json

import pytest

from aurora import mdl_router, sys_config, sys_context

from conftest import write_env


@pytest.fixture
def cfg(tmp_path):
    return sys_config.load(write_env(tmp_path), check_root=False)


def test_a_requests_roles_hold_in_its_run_only_and_are_never_written(cfg):
    mdl_router.set_assignments(cfg, {"agent": {"provider": "claude_code", "model": "haiku"}})
    bench = mdl_router.check_roles({r: {"provider": "local", "model": ""} for r in mdl_router.ROLES})
    seen = {}
    token = mdl_router.RUN_ROLES.set(bench)
    try:                                   # the run's thread copies the request's context (sys_context.start)
        t = sys_context.start(lambda: seen.update(agent=mdl_router.assignments(cfg)["agent"]["provider"]))
        t.join()
        mdl_router.set_assignments(cfg, {"rem": {"provider": "local", "model": ""}})     # a save during the run
    finally:
        mdl_router.RUN_ROLES.reset(token)
    assert seen["agent"] == "local"                                                    # the benchmark's target
    assert mdl_router.assignments(cfg)["agent"] == {"provider": "claude_code", "model": "haiku"}   # the owner's
    saved = json.loads((cfg.path("AURORA_STATUS_DIR") / "models" / "roles.json").read_text())
    assert saved["agent"]["provider"] == "claude_code"                                 # never the run's roles
    other = contextvars.Context().run(lambda: mdl_router.assignments(cfg)["agent"]["provider"])
    assert other == "claude_code"                                                      # the owner's chat meanwhile


def test_unknown_roles_or_providers_are_refused(cfg):
    with pytest.raises(ValueError):
        mdl_router.check_roles({"agent": {"provider": "nobody"}})
    with pytest.raises(ValueError):
        mdl_router.check_roles({"nothing": {"provider": "local"}})
