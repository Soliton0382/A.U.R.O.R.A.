# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The PDFs of the user's own Documents folder, read only, metadata only (merged from the forged plugin «userpdfs»,
16 Oct: the documents in one plugin). Folder: AURORA_DOCUMENTS_PDFS_DIR, or XDG's Documents, ~/Documenti, ~/Documents."""
from __future__ import annotations

import os
from pathlib import Path

from aurora import sys_config

KEY = "AURORA_DOCUMENTS_PDFS_DIR"


def _xdg_documents(home: Path) -> Path | None:
    """XDG_DOCUMENTS_DIR from ~/.config/user-dirs.dirs, when set."""
    f = home / ".config" / "user-dirs.dirs"
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("XDG_DOCUMENTS_DIR="):
                val = line.split("=", 1)[1].strip().strip('"')
                val = val.replace("$HOME", str(home))
                p = Path(val).expanduser()
                if p != home:
                    return p
    except OSError:
        pass
    return None


def _docs_dir() -> tuple[Path | None, str]:
    """(folder, "") or (None, the reason, in Italian for the owner)."""
    custom = str(sys_config.get().values.get(KEY, "") or "").strip()
    if custom:
        p = Path(custom).expanduser()
        if p.is_dir():
            return p, ""
        return None, f"La cartella indicata in {KEY} non esiste: {p}"
    home = Path.home()
    candidates = []
    x = _xdg_documents(home)
    if x:
        candidates.append(x)
    candidates += [home / "Documenti", home / "Documents"]
    for c in candidates:
        if c.is_dir():
            return c, ""
    return None, ("Cartella Documenti non trovata (cercate: "
                  + ", ".join(str(c) for c in candidates)
                  + f"). Puoi indicarla in {KEY} (Plugin → documents).")


def _scan(root: Path) -> tuple[list[tuple[str, int, float]], int]:
    """Walk the folder without following links: (pdfs as (path, size, mtime), unreadable entries)."""
    found: list[tuple[str, int, float]] = []
    errors = 0

    def onerr(_e):
        nonlocal errors
        errors += 1

    for dirpath, _dirs, files in os.walk(root, onerror=onerr, followlinks=False):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                errors += 1
                continue
            found.append((full, st.st_size, st.st_mtime))
    return found, errors


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
