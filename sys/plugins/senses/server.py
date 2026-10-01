# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "senses": Aurora sees through the camera and hears through the microphone of this machine."""
from __future__ import annotations

from aurora import sns_av, sys_config
from aurora.mdl_llm import LLM
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("senses", version="1.0")


@server.tool()
def devices() -> str:
    """Cameras and microphones connected to this machine, and which ones Aurora uses (settings)."""
    found = sns_av.devices()
    lines = [f"camera {c['id']}: {c['name']}" for c in found["cameras"]]
    lines += [f"microphone {m['id']}: {m.get('name', '')}" for m in found["microphones"]]
    lines.append(f"in use: camera {cfg['AURORA_SENSES_CAMERA']}, microphone {cfg['AURORA_SENSES_MIC']}")
    return "\n".join(lines)


@server.tool()
def look(instruction: str = "Descrivi in italiano cosa vedi, in modo preciso e breve.") -> str:
    """Take one photo with the chosen camera and describe it with Aurora's own vision."""
    try:
        jpeg = sns_av.photo(cfg)
    except RuntimeError as e:
        raise ToolError(str(e))
    return LLM(cfg).see(jpeg, instruction)


@server.tool()
def listen(seconds: float = 5.0) -> str:
    """Record from the chosen microphone for a few seconds and transcribe locally (Whisper, CPU)."""
    try:
        audio = sns_av.record(seconds, cfg)
    except RuntimeError as e:
        raise ToolError(str(e))
    r = sns_av.transcribe(audio, str(cfg["AURORA_LANG_DEFAULT"])[:2], cfg)
    return r["text"] if r["clear"] else f"no clear speech in {r['audio_s']} s (heard only: {r['text'][:80]!r})"


if __name__ == "__main__":
    server.run("stdio")
