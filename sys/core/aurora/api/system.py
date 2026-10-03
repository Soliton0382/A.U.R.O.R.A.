# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Status, features, services, settings (.env through the schema)."""
from __future__ import annotations

import httpx

from aurora import sys_config, sys_log
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import _admin, auth, cfg, log, user_of

router = APIRouter()


# ---- status and settings -------------------------------------------------------------------
@router.get("/v1/aurora/status", dependencies=[Depends(auth)])
def status() -> dict:
    import httpx
    from aurora.sol_reader import VaultReader
    out = {"vault": VaultReader(cfg).count()}
    for name, url in (("models", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
                      ("llm", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")):
        try:
            out[name] = httpx.get(url, timeout=3).json()
        except httpx.HTTPError as e:
            out[name] = {"status": "down", "error": str(e)}
    return out


@router.get("/v1/aurora/settings", dependencies=[Depends(auth)])
def settings(request: Request) -> dict:
    """The settings as the asking user sees them: the machine's, and their own (U3: their usr/<name>/.env)."""
    from aurora import sys_user_config, sys_users_layout
    schema = sys_config.load_schema()
    current = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
    user = user_of(request)
    if user and sys_users_layout.migrated(cfg):
        own = sys_config.parse_env(sys_user_config.env_path(cfg, user).read_text(encoding="utf-8")) \
            if sys_user_config.env_path(cfg, user).is_file() else {}
        current.update({s["key"]: own.get(s["key"], s["recommended"]) for s in schema["settings"] if s.get("scope") == "user"})
    items = []
    for s in schema["settings"]:
        value = current.get(s["key"], "")
        items.append({**s, "value": ("••••••" if s.get("secret") and value else value)})
    return {"categories": schema["categories"], "settings": items}


@router.put("/v1/aurora/settings", dependencies=[Depends(auth)])
async def update_settings(request: Request) -> dict:
    changes: dict = await request.json()
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    problems = []
    for key, value in changes.items():
        if key not in specs:
            problems.append(f"{key}: not in the settings schema")
            continue
        try:
            sys_config.convert(specs[key], str(value))
        except ValueError as e:
            problems.append(f"{key}: {e}")
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    from aurora import sys_user_config, sys_users_layout, sys_users_mode
    user, admin = user_of(request), _admin()
    if "AURORA_USER_MODE" in changes and str(changes["AURORA_USER_MODE"]) != sys_users_mode.current(cfg):
        try:                                                 # single ↔ multi: what it does, refused or confirmed
            sys_users_mode.switch(cfg, str(changes["AURORA_USER_MODE"]), user, admin,
                                  confirm=request.query_params.get("confirm") == "purge")
        except sys_users_mode.ModeError as e:
            raise HTTPException(status_code=409, detail={"message": str(e), "plan": e.plan}) from None
    if user and sys_users_layout.migrated(cfg):              # U3: a user's own settings go to their usr/<name>/.env
        mine = {k: str(v) for k, v in changes.items() if specs[k].get("scope") == "user"}
        machine = {k: str(v) for k, v in changes.items() if k not in mine}
        if machine and user != admin:
            raise HTTPException(status_code=403, detail="only the admin changes the machine's settings")
        if mine:
            sys_user_config.write(cfg, user, mine)
    else:
        machine = {k: str(v) for k, v in changes.items()}
    if machine:
        sys_config.write_env(sys_config.env_file_path(), machine)
    restart = sorted({svc for k in changes for svc in specs[k]["services"]})
    log.info("audit: settings changed: %s; services to restart: %s", ", ".join(sorted(changes)), ", ".join(restart))
    sys_log.trace("api", "settings.change", {"keys": sorted(changes), "restart": restart})
    from .backup import NAS_KEYS, start_mount             # the backup plugin saved with a NAS folder: mount it now
    mounting = bool(NAS_KEYS & set(changes)) and start_mount(str(changes.get("AURORA_BACKUP_DIR", cfg["AURORA_BACKUP_DIR"])))
    return {"changed": sorted(changes), "restart": restart, "mounting": mounting}
