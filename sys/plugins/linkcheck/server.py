# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "linkcheck": a link's reputation before it is opened (aurora/sec_linkcheck: the services the owner ticks).

The same check runs by itself before every page Aurora opens and every agent's tool call that carries a link; this
tool lets Aurora — or the owner, in chat — ask about a link without opening it."""
from __future__ import annotations

from aurora import sec_linkcheck, sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("linkcheck", version="1.0")


@server.tool()
def check_link(url: str) -> str:
    """The reputation of a link (http or https), from the services ticked in this plugin's card, without opening it:
    the verdict (clean, suspicious, malicious, unknown), whether Aurora would refuse it, and each service's reason."""
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ToolError("only http or https links")
    v = sec_linkcheck.check(url, sys_config.get())
    head = ("⛔ " + sec_linkcheck.refusal(v)) if v["blocked"] else f"Reputazione: {v['level']} (Aurora lo aprirebbe)."
    return head + "\n" + "\n".join(f"- {r}" for r in v["reasons"]) + \
        f"\nControllato da: {', '.join(v['checked'])}" + (" (verdetto di oggi, dalla memoria)" if v.get("cached") else "")


if __name__ == "__main__":
    server.run("stdio")
