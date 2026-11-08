# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C512: the sentinel asks whether any run is working; another user's run counts, and nothing of it is told."""
import importlib
import sys

from aurora import sys_config


def test_another_users_run_counts_as_busy(cfg, monkeypatch):
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):                                                     # the app's own order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import core, runs
    monkeypatch.setattr(core, "_runs", {})
    monkeypatch.setattr(runs, "_runs", core._runs)
    assert runs.runs_busy() == {"open": 0}
    core._runs["r1"] = {"id": "r1", "user": "demo", "done": False, "question": "a secret question"}
    core._runs["r2"] = {"id": "r2", "user": "admin", "done": True, "question": "another"}
    out = runs.runs_busy()
    assert out == {"open": 1} and "secret" not in str(out)
