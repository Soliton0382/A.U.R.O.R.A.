# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C226: with the cage asked for (AURORA_PLUGIN_SANDBOX) and bubblewrap missing — a container, a machine without the
package — a plugin ran uncaged. Now it does not run; switching the cage off stays the owner's explicit choice."""
import pytest

from aurora import plg_host, plg_sandbox


def test_no_cage_no_plugin(cfg, tmp_path, monkeypatch):
    folder = tmp_path / "demo"
    folder.mkdir()
    p = plg_host.Plugin("demo", folder, {"name": "demo", "command": ["{python}", "server.py"], "effects": {"*": "read"}})
    host = plg_host.PluginHost(cfg)
    monkeypatch.setattr(plg_sandbox, "available", lambda: False)
    with pytest.raises(RuntimeError, match="no cage"):
        host._params(p)
    cfg.values["AURORA_PLUGIN_SANDBOX"] = False                          # the owner's own choice: then it runs bare
    assert host._params(p).env["AURORA_ENV_FILE"].endswith(".env")


def test_a_plugin_that_cannot_start_is_not_started_again_at_every_question(cfg, tmp_path, monkeypatch):
    """C229: a failed start is remembered FAILED_S (or until its manifest changes)."""
    folder = tmp_path / "broken"
    folder.mkdir()
    p = plg_host.Plugin("broken", folder, {"name": "broken", "command": ["{python}", "server.py"]})
    host = plg_host.PluginHost(cfg)
    starts = []

    def fail(coro):
        coro.close()
        starts.append(1)
        raise RuntimeError("Connection closed")
    monkeypatch.setattr(host, "_run", fail)
    monkeypatch.setattr(plg_host, "_FAILED", {})
    for _ in range(3):
        with pytest.raises(RuntimeError, match="Connection closed"):
            host._tools(p, 1.0)
    assert len(starts) == 1                                           # started once, then remembered
    with pytest.raises(RuntimeError):
        host._tools(p, 2.0)                                           # a new manifest: tried again
    assert len(starts) == 2
