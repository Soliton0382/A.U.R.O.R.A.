# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "dropbox": the owner's Dropbox (HTTP API v2) — list, search, read text files, upload one of Aurora's
documents. The access token (4 h) is made from the refresh token (authorize.py, once) at each call.
Uploading is an external action: the owner approves it. Nothing is ever deleted or overwritten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

KEY = os.environ.get("AURORA_DROPBOX_APP_KEY", "")
SECRET = os.environ.get("AURORA_DROPBOX_APP_SECRET", "")
REFRESH = os.environ.get("AURORA_DROPBOX_REFRESH_TOKEN", "")
API, CONTENT = "https://api.dropboxapi.com/2", "https://content.dropboxapi.com/2"
TEXT = (".txt", ".md", ".csv", ".json", ".log", ".xml", ".html", ".py", ".yaml", ".yml")
cfg = sys_config.get()
server = MCPServer("dropbox", version="1.0")


def _token() -> str:
    if not (KEY and SECRET and REFRESH):
        raise ToolError("Dropbox is not authorized yet: app key, secret, then authorize.py (plugin card)")
    r = httpx.post("https://api.dropboxapi.com/oauth2/token", timeout=30, data={
        "grant_type": "refresh_token", "refresh_token": REFRESH, "client_id": KEY, "client_secret": SECRET}).json()
    if "access_token" not in r:
        raise ToolError(f"Dropbox refused the refresh token ({r.get('error_description') or r.get('error')})")
    return r["access_token"]


def _rpc(path: str, body: dict) -> dict:
    r = httpx.post(f"{API}/{path}", headers={"Authorization": f"Bearer {_token()}"}, json=body, timeout=60)
    if r.status_code == 409:
        raise ToolError(f"Dropbox: {r.json().get('error_summary', 'not found')}")
    r.raise_for_status()
    return r.json()


def _path(p: str) -> str:
    p = "/" + p.strip().strip("/") if p.strip().strip("/") else ""
    if "/.." in p:
        raise ToolError("a path inside your Dropbox")
    return p


@server.tool()
def dropbox_list(path: str = "") -> str:
    """The files and folders of a folder."""
    d = _rpc("files/list_folder", {"path": _path(path), "limit": 200})
    rows = [f"{'📁' if e['.tag'] == 'folder' else '📄'} {e['name']}"
            + (f"  {e.get('size', 0) / 1024:.0f} KB  {e.get('server_modified', '')[:10]}" if e[".tag"] == "file" else "")
            for e in d.get("entries", [])]
    return "\n".join(sorted(rows)) or "empty folder"


@server.tool()
def dropbox_search(query: str, limit: int = 20) -> str:
    """Files whose name or text matches the words."""
    d = _rpc("files/search_v2", {"query": query, "options": {"max_results": max(1, min(limit, 100))}})
    return "\n".join(m["metadata"]["metadata"].get("path_display", "") for m in d.get("matches", [])) or "nothing found"


@server.tool()
def dropbox_read(path: str) -> str:
    """A text file's content (txt, md, csv, json…), at most 50 KB."""
    if not path.lower().endswith(TEXT):
        raise ToolError("only text files are read here")
    r = httpx.post(f"{CONTENT}/files/download", timeout=60, headers={
        "Authorization": f"Bearer {_token()}", "Dropbox-API-Arg": json.dumps({"path": _path(path)})})
    if r.status_code == 409:
        raise ToolError("not found")
    r.raise_for_status()
    return r.text[:50_000] + ("\n…(cut)" if len(r.text) > 50_000 else "")


@server.tool()
def dropbox_upload(document: str, folder: str = "Aurora") -> str:
    """Upload one of Aurora's documents (file name in her documents folder) into a Dropbox folder (an external action:
    the owner confirms it). An existing file is never overwritten."""
    if "/" in document or document.startswith("."):
        raise ToolError("the document's file name only")
    src = cfg.path("AURORA_DOCUMENTS_DIR") / document
    if not src.is_file():
        raise ToolError(f"no document {document}")
    if src.stat().st_size > 150 * 2**20:
        raise ToolError("more than 150 MB: too large for one upload")
    target = f"{_path(folder)}/{Path(document).name}"
    r = httpx.post(f"{CONTENT}/files/upload", content=src.read_bytes(), timeout=300, headers={
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": json.dumps({"path": target, "mode": "add", "autorename": False})})
    if r.status_code == 409:
        raise ToolError("a file with that name is already there: not overwritten")
    r.raise_for_status()
    return f"uploaded: {target} ({src.stat().st_size / 1024:.0f} KB)"


if __name__ == "__main__":
    server.run("stdio")
