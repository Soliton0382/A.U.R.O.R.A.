# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The per-user layout (docs/MULTIUSER.md, U2): see the plan, move today's data under the admin, or go back.

    python sys/core/script/sys_users_migrate.py plan                 # what would move, nothing is touched (default)
    python sys/core/script/sys_users_migrate.py migrate --yes        # services stopped, a backup of the last 24 h
    python sys/core/script/sys_users_migrate.py rollback --yes       # back to today's layout (admin only)

The admin is created in users.db when missing (AURORA_OWNER_NAME, no password: single-user logs in as today).
Shared data (knowledge, models, plugins, settings) never moves. The migration is run once, when the code reads the
per-user layout (U3); before that Aurora would not find her memory.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_backup, sys_config, sys_users_layout as L  # noqa: E402
from aurora.sys_users import Users  # noqa: E402


def services_running() -> list[str]:
    names = ["aurora-api", "aurora-rem", "aurora-harvester", "aurora-sentinel"]
    out = subprocess.run(["systemctl", "is-active", *names], capture_output=True, text=True).stdout.split()
    return [n for n, s in zip(names, out) if s == "active"]


def admin_id(cfg, create: bool) -> str | None:
    users = Users(cfg)
    a = users.admin()
    if a or not create:
        return a["id"] if a else None
    name = re.sub(r"[^\w.-]+", "", str(cfg["AURORA_OWNER_NAME"] or "admin"))[:40] or "admin"
    return users.add(name, "admin")["id"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", nargs="?", default="plan", choices=["plan", "migrate", "rollback"])
    ap.add_argument("--yes", action="store_true", help="do it (without: the plan only)")
    a = ap.parse_args()
    cfg = sys_config.get()
    admin = admin_id(cfg, create=a.action == "migrate" and a.yes)
    if a.action in ("plan", "migrate"):
        plan = L.migration_plan(cfg, admin or "ADMIN")
        for s in plan:
            print(f"{s['area']:12} {s['files']:6} files {s['bytes'] / 1e6:9.1f} MB  {s['from']}")
        print(f"total: {len(plan)} entries, {sum(s['files'] for s in plan)} files, {sum(s['bytes'] for s in plan) / 1e6:.1f} MB")
    if a.action == "plan" or not a.yes:
        print("(plan only: nothing was moved)" if a.action != "rollback" else "(add --yes to roll back)")
        return 0
    running = services_running()
    if running:
        print(f"STOP: services running ({', '.join(running)}): sudo systemctl stop aurora.target")
        return 1
    last = (sys_backup.status(cfg).get("last") or {}).get("at") or 0
    if time.time() - last > 24 * 3600:
        print("STOP: no backup in the last 24 hours: .venv/bin/python sys/core/script/svc_backup.py run")
        return 1
    print(L.migrate(cfg, admin) if a.action == "migrate" else L.rollback(cfg, admin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
