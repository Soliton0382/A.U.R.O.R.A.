# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "astro" (ROADMAP 79 step 0): the person's astrophotography equipment, read only — the profile of the latest
inventory (ast_inventory), the integrated darks' library of this machine, the files of the astro folder. No network."""
from __future__ import annotations

from aurora import ast_inventory, sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("astro", version="1.0")


@server.tool()
def astro_profile() -> str:
    """L'attrezzatura per l'astrofotografia (telescopio, montatura, camere con la scala in "/px, guida PHD2, focheggiatore,
    filtri, plate solving, sito arrotondato, software, integrated dark) e cosa conviene controllare."""
    return ast_inventory.text(ast_inventory.profile(sys_config.get()))


@server.tool()
def astro_darks() -> str:
    """The integrated darks of this machine: exposure, gain, offset, frames, date of each; which exposures match the camera
    as N.I.N.A. sets it."""
    cfg = sys_config.get()
    lib = ast_inventory.darks_library(cfg)
    if not lib["darks"]:
        return lib["error"] or "Nessuna cartella di dark integrati indicata (AURORA_ASTRO_DARKS_DIR, pagina 🔭 Astro)."
    p = ast_inventory.profile(cfg)
    lines = [f"Integrated dark in {lib['folder']}: {len(lib['darks'])}"]
    for d in lib["darks"]:
        lines.append(f"- {d['file']}: {d.get('exposure_s', '?'):g} s, gain {d.get('gain', '?')}, offset {d.get('offset', '?')}, "
                     f"{d.get('frames') or '?'} pose, {d.get('date') or '?'}" + (" (vecchio)" if d["old"] else ""))
    if p:
        m = ast_inventory.darks_for(lib, p["rig"])
        lines.append(f"Per gain {m['gain']} e offset {m['offset']} (N.I.N.A.): {', '.join(f'{x:g} s' for x in m['match']) or 'nessuno'}")
    return "\n".join(lines)


@server.tool()
def astro_files() -> str:
    """The files of the astro folder: the inventories and the manuals and notes added in the 🔭 Astro page."""
    cfg = sys_config.get()
    d = ast_inventory.folder(cfg)
    inv = {f.name for f in ast_inventory.inventories(cfg)}
    rows = [f"- {f.name} ({f.stat().st_size // 1024} KB){' — inventario' if f.name in inv else ''}"
            for f in sorted(d.iterdir()) if f.is_file() and f.name != "darks.json"]
    return "\n".join(rows) or "La cartella astro è vuota."


if __name__ == "__main__":
    server.run("stdio")
