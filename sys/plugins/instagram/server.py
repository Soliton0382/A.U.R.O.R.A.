# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "instagram": the Instagram professional account linked to the owner's Facebook page (Graph API, the page's
token: no other key).

Publishing a photo: Instagram fetches the picture from a public address and takes JPEG only. Aurora's pictures are on
this computer, so the picture is converted to JPEG and uploaded to the Facebook page as an unpublished photo (nobody
sees it there), and Instagram takes it from Meta's own servers. Publishing is an external action: the owner approves.
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

PAGE = os.environ.get("AURORA_FACEBOOK_PAGE_ID", "")
TOKEN = os.environ.get("AURORA_FACEBOOK_PAGE_TOKEN", "")
GRAPH = "https://graph.facebook.com/v21.0"
cfg = sys_config.get()
server = MCPServer("instagram", version="1.0")


def _call(method: str, path: str, files=None, **params) -> dict:
    if not PAGE or not TOKEN:
        raise ToolError("the Facebook page is not set: Instagram goes through it (facebook plugin)")
    r = httpx.request(method, f"{GRAPH}/{path}", params={**params, "access_token": TOKEN}, files=files, timeout=120)
    data = r.json()
    if "error" in data:
        e = data["error"]
        hint = (" — the page token needs instagram_basic and instagram_content_publish (Graph API Explorer, then "
                "me/accounts again)") if e.get("code") in (10, 200) else ""
        raise ToolError(f"Graph API: {e.get('message', r.status_code)}{hint}")
    return data


def _account() -> str:
    d = _call("GET", PAGE, fields="instagram_business_account")
    ig = (d.get("instagram_business_account") or {}).get("id")
    if not ig:
        raise ToolError("no Instagram professional account is linked to the Facebook page: Instagram app → "
                        "Settings → Account type → professional, then Facebook page → Settings → Linked accounts")
    return ig


def _picture(name: str) -> Path:
    """A picture of Aurora's (dreams and generations, the chat's files, the documents), by its file name only."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ToolError("give the picture's file name only")
    for key in ("AURORA_IMAGE_DIR", "AURORA_UPLOADS_DIR", "AURORA_DOCUMENTS_DIR"):
        # never the owner's papers (his documents and patents): they are not Aurora's to publish
        found = next((p for p in cfg.path(key).rglob(name) if p.is_file()
                      and "papers" not in p.relative_to(cfg.path(key)).parts), None)
        if found:
            return found
    raise ToolError(f"no picture named {name}")


@server.tool()
def ig_account() -> str:
    """The linked Instagram account: name, followers, posts (checks that everything is connected)."""
    d = _call("GET", _account(), fields="username,name,followers_count,media_count")
    return f"@{d.get('username')} · {d.get('followers_count', '?')} followers · {d.get('media_count', '?')} posts"


@server.tool()
def ig_recent(limit: int = 10) -> str:
    """The latest posts with likes and comments."""
    d = _call("GET", f"{_account()}/media", fields="caption,timestamp,like_count,comments_count,permalink",
              limit=max(1, min(limit, 50)))
    return "\n".join(f"[{m.get('timestamp', '')[:16]}] ♥{m.get('like_count', 0)} 💬{m.get('comments_count', 0)} "
                     f"{(m.get('caption') or '')[:120]} {m.get('permalink', '')}" for m in d.get("data", [])) or "no posts"


@server.tool()
def ig_publish_photo(picture: str, caption: str) -> str:
    """Publish one of Aurora's pictures (file name, e.g. a dream) with its caption (an external action: the owner
    confirms it)."""
    from PIL import Image
    src = _picture(picture)
    buf = io.BytesIO()
    with Image.open(src) as im:
        im.convert("RGB").save(buf, "JPEG", quality=92)        # Instagram takes JPEG only
    photo = _call("POST", f"{PAGE}/photos", files={"source": ("picture.jpg", buf.getvalue(), "image/jpeg")},
                  published="false")
    url = max(_call("GET", photo["id"], fields="images")["images"], key=lambda i: i["width"])["source"]
    ig = _account()
    box = _call("POST", f"{ig}/media", image_url=url, caption=caption[:2200])
    for _ in range(20):                                        # Meta processes the picture before it can be published
        if _call("GET", box["id"], fields="status_code").get("status_code") == "FINISHED":
            break
        time.sleep(3)
    post = _call("POST", f"{ig}/media_publish", creation_id=box["id"])
    return f"published on Instagram: media id {post.get('id')}"


if __name__ == "__main__":
    server.run("stdio")
