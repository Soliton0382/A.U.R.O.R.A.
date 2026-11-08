# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The root command Aurora tells the owner (aurora-root, sys/core/script/sys_root.py, 9 Nov): «sudo aurora-root …» once
it is installed; before that, the one-time setup from Aurora's folder first, said in the same line."""
from __future__ import annotations

from pathlib import Path

SHIM = Path("/usr/local/sbin/aurora-root")
SETUP = "sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup"


def command(args: str, root: Path | str | None = None) -> str:
    where = f"cd {root} && " if root else ""
    if SHIM.exists():
        return f"sudo aurora-root {args}".rstrip()
    return f"{where}{SETUP}" + ("" if args in ("sign", "setup") else f" && sudo aurora-root {args}")
