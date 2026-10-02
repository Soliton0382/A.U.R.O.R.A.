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


# what each kind of action needs on the token (Meta's permission names), said when the Graph API refuses
NEEDS = {"metadata": "pages_manage_metadata", "comments": "pages_read_user_content",
         "reply": "pages_manage_engagement", "greeting": "pages_messaging"}


def _call(method: str, path: str, need: str = "", json_body: dict | None = None, **params) -> dict:
    if not PAGE or not TOKEN:
        raise ToolError("AURORA_FACEBOOK_PAGE_ID or AURORA_FACEBOOK_PAGE_TOKEN is empty")
    r = httpx.request(method, f"{GRAPH}/{path}", params={**params, "access_token": TOKEN}, json=json_body, timeout=30)
    data = r.json()
    if "error" in data:
        e = data["error"]
        hint = ""
        if need and (e.get("code") in (10, 200, 190) or "permission" in str(e.get("message", "")).lower()):
            hint = (f" — the page token lacks `{NEEDS[need]}`: add it in Graph API Explorer, take the page token again "
                    "from me/accounts and save it in the plugin's card")
        if e.get("code") == 100 and "does not exist" in str(e.get("message", "")):
            hint = " — AURORA_FACEBOOK_PAGE_ID is not this token's page: `page_info` shows the right id"
        raise ToolError(f"Graph API: {e.get('message', r.status_code)}{hint}")
    return data


@server.tool()
def page_info() -> str:
    """Name, followers, category, description and website of the page (checks that the token and the id agree)."""
    if not TOKEN:
        raise ToolError("AURORA_FACEBOOK_PAGE_TOKEN is empty")
    me = httpx.get(f"{GRAPH}/me", params={"fields": "id", "access_token": TOKEN}, timeout=30).json()
    if me.get("id") and me["id"] != PAGE:
        return f"⚠️ the token is page {me['id']}, AURORA_FACEBOOK_PAGE_ID says {PAGE or '(empty)'}: save {me['id']}"
    d = _call("GET", PAGE, fields="name,followers_count,link,category,about,description,website")
    return (f"{d.get('name')} · {d.get('followers_count', '?')} followers · {d.get('category', '')} · {d.get('link', '')}\n"
            f"about: {d.get('about') or '(empty)'}\ndescription: {d.get('description') or '(empty)'}\n"
            f"website: {d.get('website') or '(empty)'}")


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


@server.tool()
def list_comments(limit: int = 20) -> str:
    """The latest comments on the page's posts, with their ids (to answer them)."""
    d = _call("GET", f"{PAGE}/posts", need="comments", limit=10,
              fields=f"message,comments.limit({max(1, min(limit, 50))}){{id,from,message,created_time}}")
    rows = []
    for p in d.get("data", []):
        for c in (p.get("comments") or {}).get("data", []):
            rows.append(f"[{c.get('created_time', '')[:16]}] {c['id']} · {(c.get('from') or {}).get('name', '?')}: "
                        f"{(c.get('message') or '')[:200]}  (on «{(p.get('message') or '')[:50]}»)")
    return "\n".join(rows[:limit]) or "no comments"


@server.tool()
def reply_comment(comment_id: str, message: str) -> str:
    """Answer a comment as the page (an external action: the owner confirms it)."""
    d = _call("POST", f"{comment_id}/comments", need="reply", message=message)
    return f"answered: comment id {d.get('id')}"


@server.tool()
def update_page_info(about: str = "", description: str = "", website: str = "") -> str:
    """Change the page's short "about", its longer description and its website (an external action)."""
    fields = {k: v for k, v in (("about", about), ("description", description), ("website", website)) if v.strip()}
    if not fields:
        raise ToolError("nothing to change")
    _call("POST", PAGE, need="metadata", **fields)
    return "page updated: " + ", ".join(fields)


@server.tool()
def set_welcome_message(text: str) -> str:
    """The greeting Messenger shows before someone writes to the page (max 160 characters; an external action)."""
    if len(text) > 160:
        raise ToolError(f"{len(text)} characters: Messenger allows 160")
    try:
        _call("POST", "me/messenger_profile", need="greeting", json_body={"greeting": [{"locale": "default", "text": text}]})
    except ToolError as e:
        if "Requires one of the params" not in str(e):
            raise
        # measured on 2 October 2026: Meta no longer takes "greeting" for this kind of page through the API
        raise ToolError("Meta does not accept the welcome message through the API for this page: set it by hand in "
                        "Meta Business Suite → Inbox → Automations → Instant reply (text: " + text + ")") from None
    return "welcome message set"


if __name__ == "__main__":
    server.run("stdio")
