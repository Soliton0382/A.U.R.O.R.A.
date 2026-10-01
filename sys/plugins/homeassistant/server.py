# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "homeassistant": the owner's home automation (REST API; HTTPS recommended)."""
from __future__ import annotations

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

URL = os.environ.get("AURORA_HA_URL", "").rstrip("/")
TOKEN = os.environ.get("AURORA_HA_TOKEN", "")
server = MCPServer("homeassistant", version="1.0")


def _api(method: str, path: str, **kw):
    if not URL or not TOKEN:
        raise ToolError("AURORA_HA_URL and AURORA_HA_TOKEN are needed")
    r = httpx.request(method, f"{URL}/api{path}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30, **kw)
    if r.status_code >= 400:
        raise ToolError(f"Home Assistant {r.status_code}: {r.text[:200]}")
    return r.json()


@server.tool()
def states(filter: str = "", limit: int = 60) -> str:
    """Devices and sensors with their state; `filter` keeps entity ids or names containing it."""
    rows = []
    for s in _api("GET", "/states"):
        name = s.get("attributes", {}).get("friendly_name", "")
        if filter and filter.lower() not in s["entity_id"].lower() and filter.lower() not in name.lower():
            continue
        unit = s.get("attributes", {}).get("unit_of_measurement", "")
        rows.append(f"{s['entity_id']} ({name}): {s['state']} {unit}".strip())
    return "\n".join(rows[:max(1, min(limit, 500))]) or "no entity"


@server.tool()
def call_service(domain: str, service: str, entity_id: str, data: dict | None = None) -> str:
    """Run a service on a device (e.g. light.turn_off on light.kitchen): an external action, confirmed by the owner."""
    out = _api("POST", f"/services/{domain}/{service}", json={"entity_id": entity_id, **(data or {})})
    return f"{domain}.{service} on {entity_id}: {len(out)} states changed"


if __name__ == "__main__":
    server.run("stdio")
