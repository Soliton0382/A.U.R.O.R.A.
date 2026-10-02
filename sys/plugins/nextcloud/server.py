# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "nextcloud": the owner's files on Nextcloud (or any WebDAV server: ownCloud, a NAS, Box…) — list, read text
files, upload one of Aurora's documents. AURORA_WEBDAV_URL is the files root, e.g. Nextcloud's
https://cloud.example.com/remote.php/dav/files/<user>/ ; the password is an app password, not the account's.
Uploading is an external action: the owner approves it. Nothing is ever deleted.
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

BASE = os.environ.get("AURORA_WEBDAV_URL", "").strip().rstrip("/") + "/"
AUTH = (os.environ.get("AURORA_WEBDAV_USER", ""), os.environ.get("AURORA_WEBDAV_PASSWORD", ""))
TEXT = (".txt", ".md", ".csv", ".json", ".log", ".xml", ".html", ".ics", ".vcf", ".py", ".yaml", ".yml")
cfg = sys_config.get()
server = MCPServer("nextcloud", version="1.0")


def _url(path: str) -> str:
    parts = [p for p in path.strip().strip("/").split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise ToolError("a path inside the files root")
    return BASE + "/".join(quote(p) for p in parts)


def _check(r: httpx.Response) -> httpx.Response:
    if r.status_code == 401:
        raise ToolError("WebDAV refused the user/password (Nextcloud: Settings → Security → app password)")
    if r.status_code == 404:
        raise ToolError("not found")
    r.raise_for_status()
    return r


@server.tool()
def files_list(path: str = "") -> str:
    """The files and folders of a folder (name, size, date)."""
    if BASE == "/":
        raise ToolError("no WebDAV address: set it in the plugin's card")
    r = _check(httpx.request("PROPFIND", _url(path), auth=AUTH, headers={"Depth": "1"}, timeout=30))
    root = urlparse(_url(path)).path.rstrip("/")
    rows = []
    for block in re.findall(r"<[a-z]*:?response>(.*?)</[a-z]*:?response>", r.text, re.S | re.I):
        href = unquote(html.unescape(re.search(r"<[a-z]*:?href>(.*?)</", block, re.I).group(1))).rstrip("/")
        if href == unquote(root):
            continue
        folder = "collection" in block.lower()
        size = re.search(r"getcontentlength>(\d+)<", block)
        when = re.search(r"getlastmodified>([^<]+)<", block)
        rows.append(f"{'📁' if folder else '📄'} {href.rsplit('/', 1)[-1]}"
                    + ("" if folder or not size else f"  {int(size.group(1)) / 1024:.0f} KB")
                    + (f"  {when.group(1)[5:16]}" if when else ""))
    return "\n".join(sorted(rows)) or "empty folder"


@server.tool()
def files_read(path: str) -> str:
    """A text file's content (txt, md, csv, json…), at most 50 KB."""
    if not path.lower().endswith(TEXT):
        raise ToolError("only text files are read here")
    r = _check(httpx.get(_url(path), auth=AUTH, timeout=60))
    return r.text[:50_000] + ("\n…(cut)" if len(r.text) > 50_000 else "")


@server.tool()
def files_upload(document: str, folder: str = "Aurora") -> str:
    """Upload one of Aurora's documents (file name in her documents folder, e.g. a PDF) into a folder (an external
    action: the owner confirms it). An existing file is never overwritten."""
    if "/" in document or document.startswith("."):
        raise ToolError("the document's file name only")
    src = cfg.path("AURORA_DOCUMENTS_DIR") / document
    if not src.is_file():
        raise ToolError(f"no document {document}")
    httpx.request("MKCOL", _url(folder), auth=AUTH, timeout=30)          # 405 when it exists already: fine
    target = _url(f"{folder}/{Path(document).name}")
    r = httpx.put(target, content=src.read_bytes(), auth=AUTH, timeout=300, headers={"If-None-Match": "*"})
    if r.status_code == 412:
        raise ToolError("a file with that name is already there: not overwritten")
    _check(r)
    return f"uploaded: {folder}/{Path(document).name} ({src.stat().st_size / 1024:.0f} KB)"


if __name__ == "__main__":
    server.run("stdio")
