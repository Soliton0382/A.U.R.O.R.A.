# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Render invented documents: text PDFs (one page per entry), image-only «scanned» PDFs and PNG photos of a page."""
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["font.family"] = "DejaVu Sans"
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

W, H = 8.27, 11.69   # A4 inches
LINES = 52


def _page_fig(text: str, dpi=100):
    fig = plt.figure(figsize=(W, H), dpi=dpi)
    y = 0.95
    for para in text.split("\n"):
        for line in (textwrap.wrap(para, 92) or [""]):
            fig.text(0.07, y, line, fontsize=9.2, va="top")
            y -= 0.0175
    return fig


def text_pdf(path: Path, pages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path, metadata={"Creator": "bench", "CreationDate": None, "ModDate": None}) as pdf:
        for t in pages:
            fig = _page_fig(t)
            pdf.savefig(fig)
            plt.close(fig)


def png_page(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = _page_fig(text, dpi=200)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def scanned_pdf(path: Path, pages: list[str], tmp: Path) -> None:
    """A PDF that holds only pictures of its pages: no text layer, like a scanner's output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path, metadata={"Creator": "bench-scan", "CreationDate": None, "ModDate": None}) as pdf:
        for i, t in enumerate(pages):
            img = tmp / f"_scan_{path.stem}_{i}.png"
            png_page(img, t)
            arr = plt.imread(img)
            fig = plt.figure(figsize=(W, H), dpi=150)
            ax = fig.add_axes([0, 0, 1, 1]); ax.imshow(arr); ax.axis("off")
            pdf.savefig(fig)
            plt.close(fig)
