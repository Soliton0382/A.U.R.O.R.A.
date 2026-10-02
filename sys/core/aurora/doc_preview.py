# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A PDF shown as pictures of its pages: the WebUI's viewer works the same on a phone (Chrome for Android has no PDF
viewer to put inside a page) and in the installed app, with no PDF plugin and no page script.

resolve(url)        the file behind a WebUI link — only Aurora's documents and the chat's files, never another path
pages(path)         how many pages (pdfinfo)
page_png(path, n)   one page as PNG (pdftoppm, 110 dpi), kept in <STATUS>/preview by the file's content
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from . import sys_config

DPI, MAX_PAGES, TIMEOUT_S = 110, 500, 60


class PreviewError(ValueError):
    pass


def resolve(cfg: sys_config.Config, url: str) -> Path:
    m = re.fullmatch(r"/v1/aurora/documents/([\w.\-]+\.pdf)", url or "")
    if m:
        p = (cfg.path("AURORA_DOCUMENTS_DIR") / m.group(1)).resolve()
        if cfg.path("AURORA_DOCUMENTS_DIR").resolve() not in p.parents or not p.is_file():
            raise PreviewError("no such document")
        return p
    m = re.fullmatch(r"/v1/aurora/uploads/([0-9a-f]{16})", url or "")
    if m:
        from . import sys_uploads
        found = sys_uploads.get(cfg, m.group(1))
        if not found:
            raise PreviewError("no such file")
        return found[0]
    raise PreviewError("only Aurora's documents and the chat's files can be previewed")


def _is_pdf(path: Path) -> None:
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise PreviewError("not a PDF")


def pages(path: Path) -> int:
    _is_pdf(path)
    r = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=TIMEOUT_S)
    m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
    if r.returncode != 0 or not m:
        raise PreviewError("the PDF cannot be read")
    return min(int(m.group(1)), MAX_PAGES)


def page_png(cfg: sys_config.Config, path: Path, n: int) -> Path:
    total = pages(path)
    if not 1 <= n <= total:
        raise PreviewError(f"page {n} of {total}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    cache = cfg.path("AURORA_STATUS_DIR") / "preview"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{h.hexdigest()[:24]}-{n}.png"
    if not out.is_file():
        prefix = out.with_suffix("")
        r = subprocess.run(["pdftoppm", "-png", "-r", str(DPI), "-f", str(n), "-l", str(n), "-singlefile", str(path),
                            str(prefix)], capture_output=True, text=True, timeout=TIMEOUT_S)
        if r.returncode != 0 or not out.is_file():
            raise PreviewError(f"page {n} could not be drawn")
    return out
