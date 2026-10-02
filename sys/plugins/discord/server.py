# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "discord": one channel of the owner's Discord server, through a bot (REST API v10, no gateway): read the
latest messages, write one. Writing is an external action: the owner approves it, and it carries the AI line.
Reading message text needs the bot's "Message Content Intent" (Developer Portal → Bot).
"""
from __future__ import annotations

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TOKEN = os.environ.get("AURORA_DISCORD_BOT_TOKEN", "")
CHANNEL = os.environ.get("AURORA_DISCORD_CHANNEL_ID", "").strip()
API = "https://discord.com/api/v10"
server = MCPServer("discord", version="1.0")


def _call(method: str, path: str, **kw):
    if not TOKEN or not CHANNEL.isdigit():
        raise ToolError("bot token or channel id missing (plugin card)")
    r = httpx.request(method, f"{API}/{path}", headers={"Authorization": f"Bot {TOKEN}", "User-Agent": "Aurora (1.0)"},
                      timeout=30, **kw)
    if r.status_code in (401, 403):
        raise ToolError(f"Discord refused ({r.status_code}): the bot must be in the server and see the channel")
    r.raise_for_status()
    return r.json()


@server.tool()
def discord_read(limit: int = 20) -> str:
    """The latest messages of the channel (author, time, text)."""
    msgs = _call("GET", f"channels/{CHANNEL}/messages", params={"limit": max(1, min(limit, 100))})
    rows = [f"[{m['timestamp'][:16].replace('T', ' ')}] {m['author'].get('global_name') or m['author']['username']}: "
            f"{(m.get('content') or '(no text: enable Message Content Intent)')[:400]}" for m in reversed(msgs)]
    return "\n".join(rows) or "no messages"


@server.tool()
def discord_send(message: str) -> str:
    """Write a message in the channel (an external action: the owner confirms it)."""
    if not message.strip() or len(message) > 2000:
        raise ToolError("a message of 1 to 2000 characters")
    m = _call("POST", f"channels/{CHANNEL}/messages", json={"content": message, "allowed_mentions": {"parse": []}})
    return f"sent: message {m.get('id')}"


if __name__ == "__main__":
    server.run("stdio")
