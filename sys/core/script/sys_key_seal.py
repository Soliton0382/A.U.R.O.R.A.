#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""As root, from the units' installer (N64): Aurora's own key sealed by systemd for her services only
(sys_keyring.seal_host). Exit 0 when the key is sealed (now or before), 3 when this system cannot seal it (no
systemd-creds: the key stays a file of the services' account, mode 600)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora import sys_backup, sys_config, sys_keyring  # noqa: E402,F401


def main() -> int:
    cfg = sys_config.get()
    if not shutil.which("systemd-creds"):
        print("  Aurora's key: a file of her account (no systemd-creds here)")
        return 3
    print(f"  Aurora's key: {sys_keyring.seal_host(cfg)}")
    import os
    import pwd
    from aurora import sys_backup_crypto  # noqa: F401 - after sys_backup (it is read back by it)
    who = os.environ.get("SUDO_USER", "")
    home = Path(pwd.getpwnam(who).pw_dir) if who and who != "root" else None
    print(f"  the backup's key: {sys_backup_crypto.seal_host(cfg, home)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
