# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C497: Claude Code is looked for where the calls look, not on the PATH of the services."""
from aurora import sys_capabilities as C


def test_the_cli_is_found_by_its_setting_not_by_the_path(cfg, monkeypatch, tmp_path):
    cli = tmp_path / "claude-here"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", "/nonexistent")
    cfg.values["AURORA_CLAUDE_CODE_BIN"] = str(cli)
    line = next(x for x in C.connections(cfg) if x["name"] == "cloud:claude_code")
    assert line["ok"] and line["detail"] == "programma trovato"
    cfg.values["AURORA_CLAUDE_CODE_BIN"] = str(tmp_path / "not-there")
    assert not next(x for x in C.connections(cfg) if x["name"] == "cloud:claude_code")["ok"]
