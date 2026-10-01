# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""PDF documents from Markdown: Aurora writes reports, summaries, answers the owner can keep or send.

Markdown (raw HTML disabled: the text stays text) → an HTML page with a clean layout → Chrome headless
prints it to PDF → the PDF gets its metadata, including the EU AI Act mark (machine-readable:
"AI-Generated", IPTC digital source type) and a visible disclosure in the footer.
Files go to AURORA_DOCUMENTS_DIR; names are made safe; an existing name gets a number.
"""
from __future__ import annotations

import html
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import sys_config, sys_disclosure, sys_log

CSS = """
@page { size: A4; margin: 20mm 18mm 22mm 18mm; }
body { padding-bottom: 10mm; font-family: "DejaVu Sans", "Noto Sans", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1b1f29; }
header { border-bottom: 2px solid #7aa2ff; padding-bottom: 6pt; margin-bottom: 14pt; }
header .t { font-size: 18pt; font-weight: 700; }
header .m { font-size: 8.5pt; color: #5b6477; }
h1, h2, h3, h4 { color: #243a73; margin: 14pt 0 6pt; }
h1 { font-size: 15pt; } h2 { font-size: 13pt; } h3 { font-size: 11.5pt; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: #eef1f7; padding: 0 2pt; }
pre { background: #eef1f7; padding: 6pt; white-space: pre-wrap; font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
th, td { border: 1px solid #c9cfdb; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #e8edf8; }
blockquote { border-left: 3px solid #7aa2ff; margin: 6pt 0; padding: 2pt 8pt; color: #3d4556; }
footer { position: fixed; bottom: 0; left: 0; right: 0; font-size: 7.5pt; color: #6b7385; text-align: center;
  border-top: 1px solid #d5dae5; padding-top: 3pt; background: #fff; }
"""


def safe_name(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "documento"
    return f"{time.strftime('%Y%m%d')}-{base}"


def to_html(title: str, markdown: str, lang: str, cfg) -> str:
    from markdown_it import MarkdownIt
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    body = md.render(markdown)
    disclosure = sys_disclosure._line(cfg, lang) if sys_disclosure._on(cfg) else ""
    stamp = time.strftime("%Y-%m-%d %H:%M")
    return (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body><header><div class='t'>{html.escape(title)}</div>"
            f"<div class='m'>Aurora · {stamp}</div></header>{body}"
            f"<footer>{html.escape(disclosure)}</footer></body></html>")


def create(title: str, markdown: str, lang: str = "it", cfg: sys_config.Config | None = None) -> Path:
    cfg = cfg or sys_config.get()
    out_dir = cfg.path("AURORA_DOCUMENTS_DIR")
    out_dir.mkdir(parents=True, exist_ok=True)
    name, n = safe_name(title), 1
    target = out_dir / f"{name}.pdf"
    while target.exists():
        n += 1
        target = out_dir / f"{name}-{n}.pdf"
    with tempfile.TemporaryDirectory(prefix="aurora-pdf-") as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(to_html(title, markdown, lang, cfg), encoding="utf-8")
        raw = Path(tmp) / "raw.pdf"
        r = subprocess.run([str(cfg["AURORA_CHROME_BIN"]), "--headless=new", "--disable-gpu", "--no-first-run",
                            f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer", f"--print-to-pdf={raw}",
                            page.as_uri()], capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not raw.exists():
            raise RuntimeError(f"PDF printing failed: {(r.stderr or r.stdout)[-500:]}")
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter(clone_from=PdfReader(raw))
        meta = {"/Title": title, "/Author": "Aurora", "/Creator": "Aurora", "/Producer": "Aurora (Chrome, pypdf)"}
        if sys_disclosure._on(cfg):
            meta.update({"/AIGenerated": "true", "/DigitalSourceType": sys_disclosure.IPTC_AI,
                         "/Subject": sys_disclosure._line(cfg, lang)})
        writer.add_metadata(meta)
        with open(target, "wb") as f:
            writer.write(f)
    sys_log.get_logger("documents").info("pdf %s (%d bytes)", target.name, target.stat().st_size)
    return target
