# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Astro (ROADMAP 79 step 0; owner, 16 Oct: «una parte nel menù chiamata astro… lo script da usare, il comando da
utilizzare e dove si trova il file txt che Aurora deve digerire»): the inventory script to download, the command, the
files of the person's astro folder (inventories, manuals, notes) added and removed, and the equipment's profile read
from the latest inventory (ast_inventory) with the darks' library of this machine. Each person's own folder."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log, me

router = APIRouter()
SCRIPT = Path(__file__).resolve().parents[3] / "plugins" / "astro" / "astro_inventory.ps1"   # sys/plugins/astro
COMMAND = "powershell -ExecutionPolicy Bypass -File .\\astro_inventory.ps1"
NAME = re.compile(r"^[\w .()+-]{1,120}\.(txt|md|pdf|csv|json|xml|log)$", re.I)
MAX_BYTES = 50 * 1024 * 1024


@router.get("/v1/aurora/astro", dependencies=[Depends(auth)])
def astro() -> dict:
    from aurora import ast_inventory as A
    d = A.folder(cfg)
    inv = {f.name for f in A.inventories(cfg)}
    files = [{"name": f.name, "bytes": f.stat().st_size, "inventory": f.name in inv, "modified": f.stat().st_mtime}
             for f in sorted(d.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
             if f.is_file() and f.name != "darks.json"]                  # Aurora's own snapshot of the darks
    p = A.profile(cfg)
    try:
        where = str(d.relative_to(cfg.root))
    except ValueError:
        where = str(d)
    return {"profile": p, "text": A.text(p), "files": files, "folder": where, "command": COMMAND,
            "script": SCRIPT.name, "darks_dir": str(cfg["AURORA_ASTRO_DARKS_DIR"] or "")}


@router.get("/v1/aurora/astro/script", dependencies=[Depends(auth)])
def astro_script(as_json: bool = False):
    """The inventory script, to run on the astrophotography PC (read only there); as_json: {name, text}, for the page's
    call() (sent again with its key when the phone wakes up, C199)."""
    if as_json:
        return {"name": SCRIPT.name, "text": SCRIPT.read_text(encoding="utf-8")}
    return FileResponse(SCRIPT, media_type="text/plain", filename=SCRIPT.name)


@router.post("/v1/aurora/astro/files", dependencies=[Depends(auth)])
async def astro_add(request: Request) -> dict:
    """The body is the file; its name in X-File-Name: an inventory (.txt) or a manual, a note (.pdf, .md…)."""
    from aurora import ast_inventory as A
    name = Path(str(request.headers.get("x-file-name", ""))).name
    if not NAME.match(name):
        raise HTTPException(status_code=422, detail="a .txt, .md, .pdf, .csv, .json, .xml or .log file, with a plain name")
    raw = await request.body()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="from 1 byte to 50 MB")
    f = A.folder(cfg) / name
    f.write_bytes(raw)
    log.info("audit: %s added %s to the astro folder (%d bytes)", me(), name, len(raw))
    return {"name": name, "bytes": len(raw), "inventory": raw[:80].decode("utf-8-sig", "replace").startswith(A.HEADER)}


@router.delete("/v1/aurora/astro/files/{name}", dependencies=[Depends(auth)])
def astro_remove(name: str) -> dict:
    from aurora import ast_inventory as A
    f = A.folder(cfg) / Path(name).name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    f.unlink()
    log.info("audit: %s removed %s from the astro folder", me(), f.name)
    return {"removed": f.name}
