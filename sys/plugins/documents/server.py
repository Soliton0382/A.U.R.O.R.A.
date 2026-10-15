# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "documents": PDF documents written by Aurora (doc_pdf), and the PDFs of the user's own Documents folder
(my_pdfs, read only)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aurora import doc_pdf, sys_config, txt_lang
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from my_pdfs import _docs_dir, _scan, _size

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
def list_documents(limit: int = 100, contains: str = "") -> str:
    """The PDF documents of the Documents page (AURORA_DOCUMENTS_DIR, its folders included: the routines file their
    reports in folders of their own): how many in all and per folder, then the newest first; `contains` filters on
    the path."""
    d = cfg.path("AURORA_DOCUMENTS_DIR")
    files = [f for f in d.rglob("*.pdf") if f.is_file()] if d.is_dir() else []
    if contains:
        files = [f for f in files if contains.lower() in str(f.relative_to(d)).lower()]
    if not files:
        return "no documents" + (f" with «{contains}»" if contains else "")
    per: dict[str, int] = {}
    for f in files:
        rel = f.relative_to(d)
        top = rel.parts[0] if len(rel.parts) > 1 else "(main folder)"
        per[top] = per.get(top, 0) + 1
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    head = [f"{len(files)} PDF in all" + (f" with «{contains}»" if contains else "") + ": "
            + ", ".join(f"{k} {v}" for k, v in sorted(per.items(), key=lambda kv: -kv[1]))]
    return "\n".join(head + [f"{f.relative_to(d)} ({f.stat().st_size // 1024} KB)" for f in files[:max(1, min(limit, 500))]])


@server.tool()
def my_pdfs_count() -> str:
    """How many PDFs the user's own Documents folder holds, subfolders included: total size and the count per top folder (read only, never a file's content)."""
    try:
        root, msg = _docs_dir()
        if root is None:
            return msg
        pdfs, errs = _scan(root)
        if not pdfs:
            out = f"Nessun PDF in {root} (sottocartelle incluse)."
            return out + (f" {errs} elementi non leggibili." if errs else "")
        total = sum(s for _, s, _ in pdfs)
        per: dict[str, int] = {}
        for p, _, _ in pdfs:
            rel = Path(p).relative_to(root)
            top = rel.parts[0] if len(rel.parts) > 1 else "(cartella principale)"
            per[top] = per.get(top, 0) + 1
        lines = [f"PDF in {root}: {len(pdfs)} (sottocartelle incluse), totale {_size(total)}."]
        lines.append("Per cartella:")
        for k, v in sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:30]:
            lines.append(f"- {k}: {v}")
        if len(per) > 30:
            lines.append(f"- … altre {len(per) - 30} cartelle")
        if errs:
            lines.append(f"Attenzione: {errs} elementi non leggibili (permessi).")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def my_pdfs_list(limit: int = 50, order: str = "recenti", contains: str = "") -> str:
    """The PDFs of the user's own Documents folder (path, size, date) with the total; order: recenti, nome or grandi; contains filters on the path (read only)."""
    try:
        root, msg = _docs_dir()
        if root is None:
            return msg
        pdfs, errs = _scan(root)
        total_all = len(pdfs)
        if contains:
            needle = contains.lower()
            pdfs = [x for x in pdfs if needle in x[0].lower()]
        if not pdfs:
            extra = f" contenenti «{contains}»" if contains else ""
            return f"Nessun PDF{extra} in {root} (sottocartelle incluse; PDF totali: {total_all})."
        o = (order or "").lower()
        if o.startswith("nom"):
            pdfs.sort(key=lambda x: x[0].lower())
        elif o.startswith("grand") or o.startswith("dim"):
            pdfs.sort(key=lambda x: -x[1])
        else:
            pdfs.sort(key=lambda x: -x[2])
        limit = max(1, min(int(limit or 50), 500))
        head = f"PDF in {root}: {len(pdfs)}"
        if contains:
            head += f" contenenti «{contains}» (su {total_all} totali)"
        head += f", totale {_size(sum(s for _, s, _ in pdfs))}."
        lines = [head]
        for p, s, m in pdfs[:limit]:
            rel = Path(p).relative_to(root)
            when = datetime.fromtimestamp(m).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {rel} | {_size(s)} | {when}")
        if len(pdfs) > limit:
            lines.append(f"… e altri {len(pdfs) - limit} (aumenta limit per vederli).")
        if errs:
            lines.append(f"Attenzione: {errs} elementi non leggibili (permessi).")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
