# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The nightly backup (sys_backup, unit aurora-backup): its state, the snapshots kept, and a backup now."""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

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


@router.get("/v1/aurora/backup/snapshots", dependencies=[Depends(admin_only)])
def backup_snapshots() -> list[dict]:
    """The backup's snapshots, each with whether it can be restored here (sys_formats) and the command that does it:
    a restore stops Aurora and moves the data, so it runs in a terminal (sys_restore.py), never from inside the API."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sys_restore", Path(__file__).resolve().parents[2] / "script" / "sys_restore.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        rows = mod.listing(cfg)
    except Exception as e:  # noqa: BLE001 — the NAS asleep, no key: said on the card
        raise HTTPException(status_code=409, detail=f"{type(e).__name__}: {str(e)[:200]}") from None
    as_it = "sudo " if mod.needs_root(cfg) else ""
    return [{**r, "command": f"sudo aurora-root restore --apply {r['snapshot']}" if as_it else   # C538: root's copy
             f"cd {cfg.root} && .venv/bin/python sys/core/script/sys_restore.py --apply {r['snapshot']}"}
            for r in reversed(rows)]


@router.get("/v1/aurora/backup/holds", dependencies=[Depends(admin_only)])
def backup_holds(path: str, snapshot: str = "latest") -> dict:
    """What a snapshot keeps under a path: names and sizes, nothing opened."""
    from aurora import sys_backup
    try:
        return sys_backup.holds(cfg, path, snapshot)
    except Exception as e:  # noqa: BLE001 — the NAS asleep, no key: said
        raise HTTPException(status_code=409, detail=f"{type(e).__name__}: {str(e)[:200]}") from None


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


# ---- ♻️ a restore from the page (owner, 27 Nov: «non solo da riga di comando ma anche dalla web ui») ----------------
EVD_STATUS = Path("/var/lib/evidentia-api/backup.json")         # Evidentia's backup, said by root: times and counts only
RESTORE_RESULT = Path("/var/lib/aurora-restore/result.json")     # root's, written by sys_restore.py --from-request


@router.get("/v1/aurora/backup/evidentia", dependencies=[Depends(admin_only)])
def backup_evidentia() -> dict:
    """Evidentia's own backup: installed or not, the last run, the copies kept (their times), the command."""
    import json
    from aurora import sys_addons
    if "evidentia" not in sys_addons.installed():
        return {"installed": False}
    try:
        st = json.loads(EVD_STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    return {"installed": True, "last": {k: st.get(k) for k in ("ok", "at", "files", "bytes", "error")} if st else None,
            "snapshots": list(st.get("snapshots") or []), "command": "sudo aurora-root restore --evidentia <copia>"}


@router.get("/v1/aurora/backup/restore", dependencies=[Depends(admin_only)])
def restore_state() -> dict:
    """The last restore asked from the page, as root wrote it (none: {})."""
    import json
    try:
        return json.loads(RESTORE_RESULT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.post("/v1/aurora/backup/restore", dependencies=[Depends(admin_only)])
async def restore_ask(request: Request) -> dict:
    """{kind: aurora|evidentia, snapshot, parts?, users?, password, code}: the admin's password and code again, then one
    request for root (aurora-restore). Aurora stops while it runs: the page waits for her and reads the result."""
    import json
    import os
    import re
    import time
    from aurora import sys_backup_parts
    from aurora.sys_users_groups import NAME
    from .core_guard import confirm_again
    from .core import me
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="a JSON object")
    confirm_again(request, body)
    kind, snap = body.get("kind"), str(body.get("snapshot", ""))
    if kind not in ("aurora", "evidentia") or not re.fullmatch(r"latest|\d{8}-\d{6}", snap):
        raise HTTPException(status_code=422, detail="kind aurora or evidentia, and a snapshot's name")
    try:
        parts = list(sys_backup_parts.chosen(",".join(body.get("parts") or []))) if body.get("parts") else []
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    users = [str(u) for u in body.get("users") or []]
    if any(not NAME.match(u) for u in users) or (kind == "evidentia" and parts):
        raise HTTPException(status_code=422, detail="users by name; Evidentia's archives come back whole, all or by user")
    if restore_state().get("running") and time.time() - float(restore_state().get("at") or 0) < 6 * 3600:
        raise HTTPException(status_code=409, detail="a restore is already running")
    folder = cfg.path("AURORA_STATUS_DIR") / "backup"
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "restore-request.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"kind": kind, "snapshot": snap, "parts": parts, "users": users, "at": time.time(), "by": me() or ""}, f)
    tmp.replace(folder / "restore-request.json")
    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-restore.service"], capture_output=True, text=True)
    if r.returncode != 0:
        (folder / "restore-request.json").unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="the restore unit is not installed yet: run ./install.sh (or "
                                                    "sudo aurora-root sign) once")
    log.info("audit: restore asked from the page by %s: %s %s parts=%s users=%s", me() or "?", kind, snap, parts, users)
    return {"started": True}
