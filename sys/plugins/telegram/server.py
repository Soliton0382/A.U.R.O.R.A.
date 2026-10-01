# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "telegram": Aurora's Telegram bot (Bot API over HTTPS)."""
from __future__ import annotations

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TOKEN = os.environ.get("AURORA_TELEGRAM_BOT_TOKEN", "")
OWNER = os.environ.get("AURORA_TELEGRAM_OWNER_CHAT_ID", "")
server = MCPServer("telegram", version="1.0")


def _api(method: str, **params) -> dict:
    if not TOKEN:
        raise ToolError("AURORA_TELEGRAM_BOT_TOKEN is empty")
    r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=params, timeout=30)
    data = r.json()
    if not data.get("ok"):
        raise ToolError(f"Telegram {method}: {data.get('description', r.status_code)}")
    return data["result"]


@server.tool()
def get_me() -> str:
    """The bot's own identity (checks that the token works)."""
    me = _api("getMe")
    return f"@{me.get('username')} ({me.get('first_name')}), id {me.get('id')}"


@server.tool()
def get_updates(limit: int = 20) -> str:
    """The latest messages the bot received: chat id, sender, text."""
    rows = []
    for u in _api("getUpdates", limit=max(1, min(limit, 100)), timeout=0):
        m = u.get("message") or u.get("channel_post") or {}
        if m:
            who = (m.get("from") or {}).get("username") or (m.get("chat") or {}).get("title", "?")
            rows.append(f"[{m.get('date')}] chat {m['chat']['id']} @{who}: {m.get('text', '(no text)')}")
    return "\n".join(rows) or "no messages"


@server.tool()
def send_message(text: str, chat_id: str = "") -> str:
    """Send a message; without chat_id it goes to the owner's chat."""
    target = chat_id or OWNER
    if not target:
        raise ToolError("no chat_id and AURORA_TELEGRAM_OWNER_CHAT_ID is empty")
    m = _api("sendMessage", chat_id=target, text=text[:4096])
    return f"sent to chat {target}, message id {m.get('message_id')}"


if __name__ == "__main__":
    server.run("stdio")
