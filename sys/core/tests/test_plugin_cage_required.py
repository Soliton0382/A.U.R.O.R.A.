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
