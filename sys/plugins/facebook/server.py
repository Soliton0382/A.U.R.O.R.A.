# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "facebook": the owner's page through the Graph API (unversioned endpoints: the oldest
version still served, so the plugin does not break when a version is retired)."""
from __future__ import annotations

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

PAGE = os.environ.get("AURORA_FACEBOOK_PAGE_ID", "")
TOKEN = os.environ.get("AURORA_FACEBOOK_PAGE_TOKEN", "")
GRAPH = "https://graph.facebook.com"
server = MCPServer("facebook", version="1.0")


def _call(method: str, path: str, **params) -> dict:
    if not PAGE or not TOKEN:
        raise ToolError("AURORA_FACEBOOK_PAGE_ID or AURORA_FACEBOOK_PAGE_TOKEN is empty")
    r = httpx.request(method, f"{GRAPH}/{path}", params={**params, "access_token": TOKEN}, timeout=30)
    data = r.json()
    if "error" in data:
        raise ToolError(f"Graph API: {data['error'].get('message', r.status_code)}")
    return data


@server.tool()
def page_info() -> str:
    """Name and followers of the page (checks that the token works)."""
    d = _call("GET", PAGE, fields="name,followers_count,link")
    return f"{d.get('name')} · {d.get('followers_count', '?')} followers · {d.get('link', '')}"


@server.tool()
def list_posts(limit: int = 10) -> str:
    """The latest posts of the page."""
    d = _call("GET", f"{PAGE}/posts", fields="message,created_time,permalink_url", limit=max(1, min(limit, 50)))
    return "\n".join(f"[{p.get('created_time')}] {(p.get('message') or '')[:200]} {p.get('permalink_url', '')}"
                     for p in d.get("data", [])) or "no posts"


@server.tool()
def page_stats(limit: int = 25) -> str:
    """Engagement of the latest posts: reactions, comments, shares per post, totals, averages, the best post."""
    fields = "message,created_time,shares,reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)"
    d = _call("GET", f"{PAGE}/posts", fields=fields, limit=max(1, min(limit, 100)))
    rows, best = [], None
    for p in d.get("data", []):
        r = (p.get("reactions") or {}).get("summary", {}).get("total_count", 0)
        c = (p.get("comments") or {}).get("summary", {}).get("total_count", 0)
        sh = (p.get("shares") or {}).get("count", 0)
        rows.append((p.get("created_time", "")[:10], r, c, sh, (p.get("message") or "")[:80]))
        if best is None or r + c + sh > best[1] + best[2] + best[3]:
            best = rows[-1]
    if not rows:
        return "no posts"
    n = len(rows)
    tot = [sum(x[i] for x in rows) for i in (1, 2, 3)]
    lines = [f"{n} posts: reactions {tot[0]} (avg {tot[0] / n:.1f}), comments {tot[1]} (avg {tot[1] / n:.1f}), "
             f"shares {tot[2]} (avg {tot[2] / n:.1f})", f"best: {best[0]} r{best[1]} c{best[2]} s{best[3]} «{best[4]}»"]
    lines += [f"{d_} r{r} c{c} s{sh} «{m}»" for d_, r, c, sh, m in rows]
    return "\n".join(lines)


@server.tool()
def publish_post(message: str, link: str = "") -> str:
    """Publish a post on the page (an external action: the owner confirms it)."""
    d = _call("POST", f"{PAGE}/feed", message=message, **({"link": link} if link else {}))
    return f"published: post id {d.get('id')}"


if __name__ == "__main__":
    server.run("stdio")
