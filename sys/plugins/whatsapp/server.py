# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "whatsapp": Aurora writes to the owner on WhatsApp (WhatsApp Business Cloud API, Meta) — send only.

WhatsApp's rules: a free text reaches the owner only within 24 hours after he wrote to Aurora's business number;
outside that window only an approved template can open the conversation (the default "hello_world" exists in every
new account). Receiving messages needs a public webhook, which Aurora does not expose: not done here.
Sending is an external action: the owner approves it.
"""
from __future__ import annotations

import os
import re

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TOKEN = os.environ.get("AURORA_WHATSAPP_TOKEN", "")
PHONE_ID = os.environ.get("AURORA_WHATSAPP_PHONE_ID", "").strip()
TO = re.sub(r"\D", "", os.environ.get("AURORA_WHATSAPP_TO", ""))
API = "https://graph.facebook.com/v21.0"
server = MCPServer("whatsapp", version="1.0")


def _send(body: dict) -> str:
    if not (TOKEN and PHONE_ID.isdigit() and TO):
        raise ToolError("token, phone number id or your number missing (plugin card)")
    r = httpx.post(f"{API}/{PHONE_ID}/messages", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30,
                   json={"messaging_product": "whatsapp", "to": TO, **body}).json()
    if "error" in r:
        e = r["error"]
        hint = (" — outside the 24-hour window only a template can be sent: whatsapp_send_template"
                if e.get("code") in (131047, 131026) else "")
        raise ToolError(f"WhatsApp: {e.get('message')}{hint}")
    return f"sent: {r['messages'][0]['id']}"


@server.tool()
def whatsapp_send(text: str) -> str:
    """A text message to the owner (within 24 h after his last message to Aurora's number; an external action)."""
    if not text.strip() or len(text) > 4096:
        raise ToolError("a message of 1 to 4096 characters")
    return _send({"type": "text", "text": {"body": text, "preview_url": True}})


@server.tool()
def whatsapp_send_template(name: str = "hello_world", language: str = "en_US") -> str:
    """An approved template (opens the conversation outside the 24-hour window; an external action)."""
    if not re.fullmatch(r"[a-z0-9_]{1,512}", name):
        raise ToolError("a template name: lowercase letters, digits, _")
    return _send({"type": "template", "template": {"name": name, "language": {"code": language}}})


if __name__ == "__main__":
    server.run("stdio")
