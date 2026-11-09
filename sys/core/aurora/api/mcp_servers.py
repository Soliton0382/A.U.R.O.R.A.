# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧩 The owner's MCP servers (plg_mcp): listed with their tools and state, added from a form, removed. The admin only;
a server added is loaded once signed (sudo aurora-root sign), like every plugin of the owner's."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log, plugin_host
from .users import admin_only

router = APIRouter()


@router.get("/v1/aurora/mcp-servers", dependencies=[Depends(admin_only)])
def servers() -> dict:
    from aurora import plg_mcp
    return {"servers": plg_mcp.listed(plugin_host())}


@router.post("/v1/aurora/mcp-servers", dependencies=[Depends(admin_only)])
async def add(request: Request) -> dict:
    """{"name", "description", "url" | "command": [...], "read": [...], "network": false | "proxy", "hosts": [...],
    "read_tools": [...], "effect", "memory", "chat"} → the manifest written; it waits for the owner's signature."""
    from aurora import plg_mcp
    try:
        m = plg_mcp.manifest(cfg, await request.json())
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    try:
        plg_mcp.save(cfg, m)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: MCP server %s saved (%s); loaded once signed", m["name"], "remote" if m.get("url") else "local")
    return {"saved": m["name"], "sign": "sudo aurora-root sign"}


@router.delete("/v1/aurora/mcp-servers/{name}", dependencies=[Depends(admin_only)])
def remove(name: str) -> dict:
    from aurora import plg_mcp
    if not plg_mcp.remove(cfg, name):
        raise HTTPException(status_code=404, detail="no MCP server of that name")
    log.info("audit: MCP server %s removed", name)
    return {"removed": name}
