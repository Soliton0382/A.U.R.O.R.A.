# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "mastodon": the owner's account on a Mastodon instance (REST API over HTTPS)."""
from __future__ import annotations

import os
import re

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

URL = os.environ.get("AURORA_MASTODON_URL", "").rstrip("/")
TOKEN = os.environ.get("AURORA_MASTODON_TOKEN", "")
server = MCPServer("mastodon", version="1.0")


def _api(method: str, path: str, **kw):
    if not URL.startswith("https://") or not TOKEN:
        raise ToolError("AURORA_MASTODON_URL (https://...) and AURORA_MASTODON_TOKEN are needed")
    r = httpx.request(method, f"{URL}{path}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30, **kw)
    if r.status_code >= 400:
        raise ToolError(f"Mastodon {r.status_code}: {r.text[:200]}")
    return r.json()


@server.tool()
def account_stats(limit: int = 20) -> str:
    """Followers and the engagement of the latest posts (favourites, boosts, replies)."""
    me = _api("GET", "/api/v1/accounts/verify_credentials")
    posts = _api("GET", f"/api/v1/accounts/{me['id']}/statuses", params={"limit": max(1, min(limit, 40)), "exclude_replies": True})
    rows = [(p["created_at"][:10], p["favourites_count"], p["reblogs_count"], p["replies_count"],
             re.sub(r"<[^>]+>", "", p["content"])[:80]) for p in posts]
    head = f"@{me['acct']}: {me['followers_count']} followers, {me['statuses_count']} posts"
    if not rows:
        return head
    n = len(rows)
    best = max(rows, key=lambda r: r[1] + r[2] + r[3])
    return "\n".join([head, f"last {n}: favourites {sum(r[1] for r in rows)}, boosts {sum(r[2] for r in rows)}, "
                      f"replies {sum(r[3] for r in rows)}", f"best: {best[0]} f{best[1]} b{best[2]} r{best[3]} «{best[4]}»"]
                     + [f"{d} f{f} b{b} r{r} «{t}»" for d, f, b, r, t in rows])


@server.tool()
def post_status(status: str) -> str:
    """Publish a post (an external action: the owner confirms it)."""
    p = _api("POST", "/api/v1/statuses", data={"status": status[:500], "visibility": "public"})
    return f"published {p.get('url')}"


if __name__ == "__main__":
    server.run("stdio")
