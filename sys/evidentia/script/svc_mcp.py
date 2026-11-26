#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's MCP server on stdio, for a client that starts it (Aurora's «Server MCP»): run with -I, so that
nothing of the caller's environment (PYTHONPATH, user site) reaches it; it adds only its own code to the path.

    <project>/.venv/bin/python -I <project>/sys/evidentia/script/svc_mcp.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia.mcp_server import _register_prompts, server  # noqa: E402

if __name__ == "__main__":
    _register_prompts()                              # the agents' cards, as prompts (asked of the API)
    server.run("stdio")
