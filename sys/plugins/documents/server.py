# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "documents": PDF documents written by Aurora (doc_pdf)."""
from __future__ import annotations

from aurora import doc_pdf, sys_config, txt_lang
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("documents", version="1.0")


@server.tool()
def create_pdf(title: str, markdown: str) -> str:
    """Write a PDF from Markdown (headings, lists, tables, code blocks). Returns the file name; the owner
    downloads it from the WebUI (Documents are listed in the chat's PDF button and in the API)."""
    if not markdown.strip():
        raise ToolError("empty document")
    p = doc_pdf.create(title, markdown, txt_lang.detect(markdown), cfg)
    return f"created {p.name} ({p.stat().st_size // 1024} KB)"


@server.tool()
def list_documents() -> str:
    """The PDF documents Aurora has written, newest first."""
    d = cfg.path("AURORA_DOCUMENTS_DIR")
    files = sorted(d.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True) if d.is_dir() else []
    return "\n".join(f"{f.name} ({f.stat().st_size // 1024} KB)" for f in files[:100]) or "no documents"


if __name__ == "__main__":
    server.run("stdio")
