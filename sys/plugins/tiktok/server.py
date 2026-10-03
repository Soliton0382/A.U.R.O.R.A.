# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "tiktok": Aurora's videos on TikTok (Content Posting API, direct post of a local file).

Until TikTok audits the owner's app, every post can only be private (SELF_ONLY: seen by the account alone) and the
account must be private: the plugin reads the privacy levels TikTok allows and never asks for more. The access token
(24 h) is made from the refresh token (365 days) at each call. Posting is an external action: the owner approves.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API = "https://open.tiktokapis.com/v2"
KEY = os.environ.get("AURORA_TIKTOK_CLIENT_KEY", "")
SECRET = os.environ.get("AURORA_TIKTOK_CLIENT_SECRET", "")
REFRESH = os.environ.get("AURORA_TIKTOK_REFRESH_TOKEN", "")
MAX_BYTES = 64 * 2**20                                   # one chunk: TikTok takes up to 64 MB in a single part
cfg = sys_config.get()
server = MCPServer("tiktok", version="1.0")


def _token() -> str:
    if not (KEY and SECRET and REFRESH):
        raise ToolError("TikTok is not authorized yet: client key, secret and the authorization (plugin card, steps 1-4)")
    r = httpx.post(f"{API}/oauth/token/", data={"client_key": KEY, "client_secret": SECRET, "grant_type": "refresh_token",
                                                "refresh_token": REFRESH}, timeout=30).json()
    if "access_token" not in r:
        raise ToolError(f"TikTok refused the refresh token ({r.get('error_description') or r.get('error')}): authorize again")
    return r["access_token"]


def _post(path: str, token: str, body: dict) -> dict:
    r = httpx.post(f"{API}/{path}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                   json=body, timeout=60).json()
    err = r.get("error") or {}
    if err.get("code") not in (None, "ok"):
        raise ToolError(f"TikTok: {err.get('code')}: {err.get('message', '')}")
    return r.get("data") or {}


def _video(name: str) -> Path:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ToolError("give the video's file name only")
    for key in ("AURORA_UPLOADS_DIR", "AURORA_IMAGE_DIR", "AURORA_DOCUMENTS_DIR"):
        # never the owner's papers (his documents and patents): they are not Aurora's to publish
        found = next((p for p in cfg.path(key).rglob(name) if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".webm")
                      and "papers" not in p.relative_to(cfg.path(key)).parts), None)
        if found:
            return found
    raise ToolError(f"no video named {name}")


@server.tool()
def tiktok_account() -> str:
    """The authorized account: name, and the privacy levels TikTok allows now (only SELF_ONLY until the app's audit)."""
    d = _post("post/publish/creator_info/query/", _token(), {})
    return (f"@{d.get('creator_username')} ({d.get('creator_nickname')}) · privacy allowed: "
            f"{', '.join(d.get('privacy_level_options', []))} · max video {d.get('max_video_post_duration_sec')} s")


@server.tool()
def tiktok_post_video(video: str, title: str) -> str:
    """Post one of Aurora's videos (file name, e.g. one she made) with its title (an external action: the owner
    confirms it). Public only if TikTok allows it for this app; otherwise visible to the account alone."""
    f = _video(video)
    size = f.stat().st_size
    if size > MAX_BYTES:
        raise ToolError(f"{size / 2**20:.0f} MB: more than the 64 MB of one part")
    token = _token()
    allowed = _post("post/publish/creator_info/query/", token, {}).get("privacy_level_options", [])
    privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in allowed else "SELF_ONLY"
    init = _post("post/publish/video/init/", token, {
        "post_info": {"title": title[:2200], "privacy_level": privacy, "is_aigc": True},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}})
    r = httpx.put(init["upload_url"], content=f.read_bytes(), timeout=600,
                  headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if r.status_code >= 300:
        raise ToolError(f"upload refused: HTTP {r.status_code} {r.text[:200]}")
    st = _post("post/publish/status/fetch/", token, {"publish_id": init["publish_id"]})
    return (f"sent to TikTok ({privacy}{', visible only to the account until the app is audited' if privacy == 'SELF_ONLY' else ''})"
            f": publish id {init['publish_id']}, status {st.get('status')}")


if __name__ == "__main__":
    server.run("stdio")
