# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The nightly backup (sys_backup, unit aurora-backup): its state, the snapshots kept, and a backup now."""
from __future__ import annotations

import subprocess

from fastapi import APIRouter, Depends, HTTPException

from .core import cfg, log
from .users import admin_only                      # the machine's backup: the admin's (multi-user)

router = APIRouter()


@router.get("/v1/aurora/backup", dependencies=[Depends(admin_only)])
def backup_state() -> dict:
    from aurora import sys_backup
    st = sys_backup.status(cfg)
    unit = subprocess.run(["systemctl", "show", "-p", "LoadState,ActiveState", "--value", "aurora-backup.service"],
                          capture_output=True, text=True).stdout.split()
    timer = subprocess.run(["systemctl", "show", "-p", "NextElapseUSecRealtime", "--value", "aurora-backup.timer"],
                           capture_output=True, text=True).stdout.strip()
    import json
    nas_f = cfg.path("AURORA_STATUS_DIR") / "backup" / "nas.json"
    try:
        st["nas"] = json.loads(nas_f.read_text()) if nas_f.exists() else None
    except ValueError:
        st["nas"] = None
    return {**st, "installed": bool(unit) and unit[0] == "loaded", "running": len(unit) > 1 and unit[1] == "activating",
            "next": timer or None, "time": cfg["AURORA_BACKUP_TIME"]}


NAS_KEYS = {"AURORA_BACKUP_DIR", "AURORA_NAS_USER", "AURORA_NAS_PASSWORD", "AURORA_NAS_FSTAB"}


def start_retime() -> bool:
    """Saving the backup time moves the timer (aurora-retime, root, installed once by install.sh)."""
    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-retime.service"], capture_output=True, text=True)
    log.info("audit: backup timer moved after a settings change (%s)", "ok" if r.returncode == 0 else r.stderr.strip()[-200:])
    return r.returncode == 0


def start_mount(folder: str) -> bool:
    """Saving the NAS settings mounts the share in the background (aurora-mount reads the new .env itself);
    the result appears in the card (nas.json)."""
    if not folder.startswith("smb://"):
        return False
    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-mount.service"], capture_output=True, text=True)
    log.info("audit: NAS mount started after a settings change (%s)", "ok" if r.returncode == 0 else r.stderr.strip()[-200:])
    return r.returncode == 0


def mount_nas() -> dict:
    """Start aurora-mount (root, installed by the owner once) when the backup folder is on the NAS."""
    if not str(cfg["AURORA_BACKUP_DIR"] or "").startswith("smb://"):
        return {"started": False, "why": "not a NAS folder"}
    r = subprocess.run(["systemctl", "start", "aurora-mount.service"], capture_output=True, text=True, timeout=200)
    log.info("audit: NAS mount requested (%s)", "ok" if r.returncode == 0 else r.stderr.strip()[-200:])
    return {"started": True, "ok": r.returncode == 0, "error": r.stderr.strip()[-300:]}


@router.post("/v1/aurora/backup/mount", dependencies=[Depends(admin_only)])
def backup_mount() -> dict:
    out = mount_nas()
    if out.get("started") and not out["ok"]:
        raise HTTPException(status_code=409, detail=out["error"] or "mount failed: see the backup card")
    return out


@router.post("/v1/aurora/backup/run", dependencies=[Depends(admin_only)])
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
