# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "twitch": who is live on Twitch and what is streamed (Helix API, an app token: client id and secret, no
user login) — read only. The owner's favourite channels in AURORA_TWITCH_CHANNELS.
"""
from __future__ import annotations

import os
import time

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

CID = os.environ.get("AURORA_TWITCH_CLIENT_ID", "")
SECRET = os.environ.get("AURORA_TWITCH_CLIENT_SECRET", "")
FAVOURITES = [c.strip().lower() for c in os.environ.get("AURORA_TWITCH_CHANNELS", "").split(",") if c.strip()]
API = "https://api.twitch.tv/helix"
_tok = {"value": "", "until": 0.0}
server = MCPServer("twitch", version="1.0")


def _get(path: str, params) -> list[dict]:
    if not (CID and SECRET):
        raise ToolError("client id and secret missing (plugin card)")
    if time.time() > _tok["until"]:
        r = httpx.post("https://id.twitch.tv/oauth2/token", timeout=30, data={
            "client_id": CID, "client_secret": SECRET, "grant_type": "client_credentials"}).json()
        if "access_token" not in r:
            raise ToolError(f"Twitch refused the app's keys ({r.get('message')})")
        _tok.update(value=r["access_token"], until=time.time() + r.get("expires_in", 3600) - 300)
    r = httpx.get(f"{API}/{path}", params=params, timeout=30,
                  headers={"Client-Id": CID, "Authorization": f"Bearer {_tok['value']}"})
    r.raise_for_status()
    return r.json().get("data", [])


@server.tool()
def twitch_live(channels: str = "") -> str:
    """Which of these channels (comma separated; default: the favourites of the card) are live now, playing what."""
    names = [c.strip().lower() for c in channels.split(",") if c.strip()] or FAVOURITES
    if not names:
        raise ToolError("name some channels, or set the favourites in the plugin's card")
    live = {s["user_login"]: s for s in _get("streams", [("user_login", n) for n in names[:100]])}
    return "\n".join(f"🔴 {n}: {live[n]['game_name']} — «{live[n]['title'][:100]}» · {live[n]['viewer_count']} spettatori"
                     if n in live else f"⚪ {n}: offline" for n in names)


@server.tool()
def twitch_top(game: str = "", limit: int = 10) -> str:
    """The most watched live streams now, of a game/category if given."""
    params = [("first", max(1, min(limit, 50)))]
    if game.strip():
        found = _get("search/categories", [("query", game), ("first", 1)])
        if not found:
            raise ToolError(f"no category {game!r}")
        params.append(("game_id", found[0]["id"]))
    return "\n".join(f"{s['viewer_count']:>7} · {s['user_name']} — {s['game_name']} — «{s['title'][:80]}»"
                     for s in _get("streams", params)) or "nothing live"


if __name__ == "__main__":
    server.run("stdio")
