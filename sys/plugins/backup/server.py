# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "backup": where the owner's data is copied every night, and how the last copies went, read only.
The settings of its card (folder, NAS user and password, mount at every start, time, retention) are saved by the API,
which mounts a NAS folder by itself (aurora-mount); the backup runs from its own unit (svc_backup.py)."""
from __future__ import annotations

import json
import time

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("backup", version="1.0")


def _read(name: str):
    f = cfg.path("AURORA_STATUS_DIR") / "backup" / name
    try:
        return json.loads(f.read_text()) if f.exists() else None
    except ValueError:
        return None


@server.tool()
def backup_status() -> str:
    """Where the backup goes, the last run (files, size, what was new, copies checked) and the NAS mount."""
    folder = str(cfg["AURORA_BACKUP_DIR"] or "")
    if not folder:
        return "Nessun backup configurato: scegli la cartella nella scheda del plugin backup."
    rows = [f"Cartella: {folder.split('://')[0] + '://…' if '://' in folder else folder} · ogni notte alle "
            f"{cfg['AURORA_BACKUP_TIME']}"]
    nas = _read("nas.json")
    if folder.startswith("smb://"):
        rows.append("NAS: " + ("montato ✅" if nas and nas.get("ok") else f"non montato ⚠️ {(nas or {}).get('error', '')}"))
    last = _read("last.json")
    if last:
        hours = (time.time() - last["at"]) / 3600
        rows.append(f"Ultimo backup {hours:.0f} h fa: {last['files']} file, {last['bytes'] / 1e9:.1f} GB, "
                    f"{last['bytes_written'] / 1e9:.2f} GB nuovi, {last['checked_blobs']} parti verificate, "
                    f"{last['seconds']:.0f} s" + (" ⚠️ più di un giorno fa" if hours > 30 else ""))
    else:
        rows.append("Nessun backup ancora fatto.")
    return "\n".join(rows)


if __name__ == "__main__":
    server.run("stdio")
