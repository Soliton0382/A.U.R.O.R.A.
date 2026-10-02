# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The nightly backup (sys_backup, unit aurora-backup): its state, the snapshots kept, and a backup now."""
from __future__ import annotations

import subprocess

from fastapi import APIRouter, Depends, HTTPException

from .core import auth, cfg, log

router = APIRouter()


@router.get("/v1/aurora/backup", dependencies=[Depends(auth)])
def backup_state() -> dict:
    from aurora import sys_backup
    st = sys_backup.status(cfg)
    unit = subprocess.run(["systemctl", "show", "-p", "LoadState,ActiveState", "--value", "aurora-backup.service"],
                          capture_output=True, text=True).stdout.split()
    timer = subprocess.run(["systemctl", "show", "-p", "NextElapseUSecRealtime", "--value", "aurora-backup.timer"],
                           capture_output=True, text=True).stdout.strip()
    return {**st, "installed": bool(unit) and unit[0] == "loaded", "running": len(unit) > 1 and unit[1] == "activating",
            "next": timer or None, "time": cfg["AURORA_BACKUP_TIME"]}


@router.post("/v1/aurora/backup/run", dependencies=[Depends(auth)])
def backup_now() -> dict:
    """Start the backup unit now (polkit lets the service user start aurora units); the result comes as a notification."""
    from aurora import sys_backup
    st = sys_backup.status(cfg)
    if not st["configured"]:
        raise HTTPException(status_code=409, detail=st["problem"] or "backup not configured")
    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-backup.service"], capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(status_code=409, detail="the backup unit is not installed: run sys_install_services.py and "
                                                    "sys/deploy/systemd/install.sh after setting AURORA_BACKUP_DIR")
    log.info("audit: owner started a backup now")
    return {"started": True}
