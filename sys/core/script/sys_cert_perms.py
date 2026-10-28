# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's certificate readable by the services' account (U6; owner, 28 Oct: «i certificati li copia il mio mini PC
con il mio utente quindi dobbiamo prevedere questa eccezione»).

Run by root (aurora-certs.service, started by aurora-certs.path when the files change), from root's own copy of the
code (sys_root_sync). The files come from the owner's own machine, written as the owner with whatever mode it gives
them (the key often 0600): each is opened without following a link, must be a regular file with one name, owned by
the owner of the installation; then its group becomes the services' and its mode 0640 — on the open file, so a name
changed meanwhile cannot point root elsewhere. Then Caddy reloads. Usage: sys_cert_perms.py <file> [<file>…]
"""
from __future__ import annotations

import grp
import os
import stat
import subprocess
import sys
from pathlib import Path

GROUP = "aurora"


def fix(path: str, owner_uid: int, gid: int) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        return f"{path}: not opened ({e.strerror})"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != owner_uid:
            return f"{path}: refused (not a plain file of the installation's owner)"
        os.fchown(fd, -1, gid)
        os.fchmod(fd, 0o640)
        return f"{path}: group {GROUP}, 0640"
    finally:
        os.close(fd)


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) < 2:
        print("usage (root): sys_cert_perms.py <file>…")
        return 2
    root = Path(os.environ.get("INSTALL_ROOT") or Path(__file__).resolve().parents[3])
    owner_uid, gid = root.stat().st_uid, grp.getgrnam(GROUP).gr_gid
    for f in sys.argv[1:]:
        print(fix(f, owner_uid, gid))
    subprocess.run(["systemctl", "try-reload-or-restart", "aurora-https.service"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
