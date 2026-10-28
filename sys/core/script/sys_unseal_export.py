#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The uninstall's «remove everything» keeps the people's documents (usr/) outside; what is sealed in them (health,
calendar, uploads: sys_seal) would never open again once the keys go. Here each sealed file under usr/<name>/ is
opened in place with its user's key, before the keys are destroyed (N64). Run as the services' account, holding
Aurora's key (the uninstall starts it with systemd-run and the sealed credential). Prints how many were opened."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora import sys_config, sys_seal, sys_users_layout as L  # noqa: E402

PURPOSES = ("state", "health", "calendar", "memory")


def main() -> int:
    cfg = sys_config.get()
    base = cfg.base or cfg
    usr = L.usr(base)
    opened, failed = 0, []
    for home in (d for d in usr.iterdir() if d.is_dir()) if usr.is_dir() else []:
        user = home.name if L.migrated(base) else None
        for dirpath, _, files in os.walk(home):
            for name in files:
                f = Path(dirpath) / name
                try:
                    with open(f, "rb") as h:
                        if h.read(len(sys_seal.MAGIC)) != sys_seal.MAGIC:
                            continue
                except OSError:
                    continue
                for purpose in PURPOSES:
                    try:
                        data = sys_seal.read(cfg, f, user, purpose)
                    except (ValueError, OSError):
                        continue
                    f.write_bytes(data)
                    opened += 1
                    break
                else:
                    failed.append(str(f.relative_to(usr)))
    print(f"opened {opened} sealed files" + (f"; not opened: {', '.join(failed[:20])}" if failed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
