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


# C556 (audit, 10 Nov): what the owner (and root through him) runs from Aurora's folder, so never the services'
# to write: the venv (its site-packages run in every owner's Python), the installers and the publish command. Only the
# owner writes them (no group write), and the folders that hold them are sticky (the services cannot rename or
# delete a file of the owner's there, so cannot swap one in). Aurora's approved changes never touch them (agt_change).
OWNER_ONLY = (".venv", "install.sh", "uninstall.sh", "sys/core/script/publish.sh")
STICKY = (".", "sys/core/script")


def owner_only(rel: str) -> bool:
    """A path (relative to Aurora's folder, posix) the services must never write."""
    rel = rel.strip("/")
    return any(rel == p or rel.startswith(p + "/") for p in OWNER_ONLY)
