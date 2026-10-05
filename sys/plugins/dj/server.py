# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "dj": Aurora's DJ from the chat — the styles, the user's tracks, a remix or a mix made (aurora.aud_dj).

The tracks and the mixes are the user's AURORA_MUSIC_DIR (usr/<name>/music, mixes in mixes/); the cage lets this
plugin write there only, with no network. The DJ page of the WebUI does the same through the API.
"""
from __future__ import annotations

import re
import time

from aurora import aud_dj, sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
MUSIC = cfg.path("AURORA_MUSIC_DIR")
AUDIO = re.compile(r"\.(mp3|wav|flac|ogg|m4a|aac|opus|webm)$", re.I)
server = MCPServer("dj", version="1.0")


@server.tool()
def dj_styles() -> str:
    """The styles the DJ knows, with their tempo."""
    return "\n".join(f"- {s['id']}: {s['label']}" + (f" ({s['bpm']} BPM)" if s["bpm"] else "") for s in aud_dj.styles("it"))


@server.tool()
def dj_tracks() -> str:
    """The user's tracks (in the DJ page) and the mixes already made."""
    tracks = sorted(f.name for f in MUSIC.glob("*") if f.is_file() and AUDIO.search(f.name)) if MUSIC.is_dir() else []
    mixes = sorted(f.name for f in (MUSIC / "mixes").glob("*.mp3")) if (MUSIC / "mixes").is_dir() else []
    return (f"Brani: {', '.join(tracks) or 'nessuno (caricali nella pagina 🎧 DJ)'}\n"
            f"Mix fatti: {', '.join(mixes) or 'nessuno'}")


@server.tool()
def dj_make(tracks: list[str], style: str) -> str:
    """Remix one track, or mix several, in a style (see dj_styles); names as dj_tracks lists them. Takes a minute or two."""
    paths = []
    for name in tracks[:12]:
        f = MUSIC / name
        if "/" in name or not AUDIO.search(name) or not f.is_file():
            raise ToolError(f"no track {name!r}: see dj_tracks")
        paths.append(f)
    if style not in aud_dj.STYLES:
        raise ToolError(f"style: one of {', '.join(aud_dj.STYLES)}")
    stem = re.sub(r"[^\w-]+", "-", f"{paths[0].stem}-{style}".lower()).strip("-")[:60]
    out = MUSIC / "mixes" / f"{stem}-{time.strftime('%Y%m%d-%H%M')}.mp3"
    r = aud_dj.make(paths, style, out, seconds=float(cfg["AURORA_DJ_MAX_MINUTES"]) * 60)
    t = r["tracks"][0]
    return (f"Fatto: {r['file']} ({r['seconds']:.0f} s, {t['bpm']} BPM, tonalità {t['key']}"
            + ("" if t["steady"] else ", il brano originale non ha un battito regolare: tenuto nel suo tempo")
            + "). Lo trovi nella pagina 🎧 DJ.")


if __name__ == "__main__":
    server.run("stdio")
