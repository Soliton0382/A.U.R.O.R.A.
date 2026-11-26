#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's API on a unix socket (no network port): sys/status/evidentia.sock, group-readable so that
Aurora's own local route can reach it. Run by the unit evidentia-api (evd_root.py), or by hand for a try."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from evidentia import config  # noqa: E402

SOCK = Path(os.environ.get("EVD_SOCKET") or "/var/lib/evidentia-api/evidentia.sock")   # set by its unit

if __name__ == "__main__":
    import grp
    import socket
    SOCK.parent.mkdir(parents=True, exist_ok=True)
    if SOCK.exists():
        SOCK.unlink()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(SOCK))
    os.chmod(SOCK, 0o660)                            # its owner and one group (Aurora's), nobody else
    group = os.environ.get("EVD_SOCKET_GROUP") or config.load()["EVD_SOCKET_GROUP"]
    try:
        os.chown(SOCK, -1, grp.getgrnam(group).gr_gid)
    except KeyError:                                 # by hand before evd_root.py made the group: Aurora's, as before
        os.chown(SOCK, -1, grp.getgrnam("aurora").gr_gid)
    from evidentia.api import app
    uvicorn.run(app, fd=s.fileno(), log_level="info", access_log=False)
