# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The GitHub plugin's program is installed by the installer, pinned and checked (found 8 Oct 2026: nothing installed
it, a fresh installation had the plugin broken)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "sys/core/script/sys_github_mcp_install.sh"


def test_the_installer_installs_the_github_plugin_s_program_pinned_and_checked():
    s = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'^VERSION="\d+\.\d+\.\d+"$', s, re.M)
    assert "sha256sum -c" in s and len(re.findall(r'SHA="[0-9a-f]{64}"', s)) == 2
    assert "bash sys/core/script/sys_github_mcp_install.sh" in (ROOT / "install.sh").read_text(encoding="utf-8")
    m = json.loads((ROOT / "sys/plugins/github/plugin.json").read_text(encoding="utf-8"))
    assert m["command"][0] == "{root}/sys/runtime/github-mcp-server/github-mcp-server"
    assert all("sys_github_mcp_install.sh" in m["setup"][lang] for lang in ("it", "en"))
