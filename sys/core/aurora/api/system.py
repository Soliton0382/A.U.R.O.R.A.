# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Status, features, services, settings (.env through the schema)."""
from __future__ import annotations

import httpx
import os

from aurora import sys_config, sys_log
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log

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
def settings() -> dict:
    schema = sys_config.load_schema()
    current = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
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
    env = sys_config.env_file_path()
    lines = env.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if k in changes and not line.lstrip().startswith("#"):
            lines[i] = f"{k}={changes[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    tmp = env.with_name(env.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # secrets inside: owner only
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, env)
    restart = sorted({svc for k in changes for svc in specs[k]["services"]})
    log.info("audit: settings changed: %s; services to restart: %s", ", ".join(sorted(changes)), ", ".join(restart))
    sys_log.trace("api", "settings.change", {"keys": sorted(changes), "restart": restart})
    from .backup import NAS_KEYS, start_mount             # the backup plugin saved with a NAS folder: mount it now
    mounting = bool(NAS_KEYS & set(changes)) and start_mount(str(changes.get("AURORA_BACKUP_DIR", cfg["AURORA_BACKUP_DIR"])))
    return {"changed": sorted(changes), "restart": restart, "mounting": mounting}
