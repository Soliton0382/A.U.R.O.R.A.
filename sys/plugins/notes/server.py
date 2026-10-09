# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "notes": the owner's notes, a folder of Markdown files (an Obsidian vault works as it is), AURORA_NOTES_DIR.

Read: list, search (words in titles and text), read one note. Write: a new note or text added at the end of one —
inside that folder only (the cage lets the plugin write there and nowhere else), never deleting or overwriting:
an existing note only grows. Writing is a local action (write_local): it follows the owner's approval rules.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("notes", version="1.0")
MAX_READ = 20_000


def _root() -> Path:
    raw = str(cfg.values.get("AURORA_NOTES_DIR") or "").strip()
    if not raw:
        raise ToolError("no notes folder: set AURORA_NOTES_DIR in the plugin's card")
    root = cfg.path("AURORA_NOTES_DIR")
    if not root.is_dir():
        raise ToolError(f"{root} does not exist")
    return root


def _note(name: str, must_exist: bool = True) -> Path:
    root = _root()
    rel = name.strip().removesuffix(".md") + ".md"
    p = (root / rel).resolve()
    if root.resolve() not in p.parents:
        raise ToolError("a note is a path inside the notes folder")
    if must_exist and not p.is_file():
        raise ToolError(f"no note {rel}")
    return p


def _notes():
    root = _root()
    return sorted((p for p in root.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(root).parts)),
                  key=lambda p: p.stat().st_mtime, reverse=True)


@server.tool()
def notes_list(limit: int = 30) -> str:
    """The most recently changed notes (folder/name, date)."""
    root, rows = _root(), []
    for p in _notes()[:max(1, min(limit, 200))]:
        rows.append(f"{time.strftime('%Y-%m-%d', time.localtime(p.stat().st_mtime))}  {p.relative_to(root).with_suffix('').as_posix()}")
    return "\n".join(rows) or "no notes"


@server.tool()
def notes_search(words: str, limit: int = 10) -> str:
    """Notes that contain all the words (title or text), with the line where they appear."""
    terms = [w.lower() for w in re.findall(r"\w+", words) if len(w) > 1]
    if not terms:
        raise ToolError("give some words to search")
    root, rows = _root(), []
    for p in _notes():
        text = p.read_text(encoding="utf-8", errors="replace")
        low = (p.stem + "\n" + text).lower()
        if all(t in low for t in terms):
            line = next((ln.strip() for ln in text.splitlines() if terms[0] in ln.lower()), "")
            rows.append(f"{p.relative_to(root).with_suffix('').as_posix()}: {line[:160]}")
            if len(rows) >= max(1, min(limit, 50)):
                break
    return "\n".join(rows) or "nothing found"


@server.tool()
def notes_read(name: str) -> str:
    """One note's text (name as in notes_list)."""
    text = _note(name).read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= MAX_READ else text[:MAX_READ] + "\n…(cut)"


@server.tool()
def notes_write(name: str, text: str) -> str:
    """A new note, or the text added at the end of an existing one (never overwritten)."""
    p = _note(name, must_exist=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    with open(p, "a", encoding="utf-8") as f:
        f.write(("\n\n" if existed else "") + text.rstrip() + "\n")
    return f"{'added to' if existed else 'created'}: {p.relative_to(_root()).with_suffix('').as_posix()}"


if __name__ == "__main__":
    server.run("stdio")
