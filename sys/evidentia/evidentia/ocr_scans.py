# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C751: the scanned pages inside PDFs, read by OCR (owner, 27 Nov: «dobbiamo completare il giro di quello che non è
stato processato se no siamo ciechi su quei files»).

The inventory ran OCR on image files only; a scanned page of a PDF kept pdftotext's text, which for a scan is none
(135 658 pages measured with ≤ 20 characters). Here each such page is rendered (pdftoppm, 300 dpi, grey) and read
(Tesseract, one thread: the processes are the parallelism, as in the inventory), then written back as the inventory
writes a page: its text, its passages (the search's FTS follows by trigger), the identifiers found on it. A page read
is marked source «ocr-page» even when nothing came out (a photo, a blank page), so a run stopped half-way goes on from
where it was and never reads a page twice. Nothing is described of a picture: only the words printed on the page."""
from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import identifiers, store
from .inventory import OCR_MEM, PDF_MEM, passages, run_capped

EMPTY = 20                       # characters: a page with this many or fewer was never really read
SOURCE = "ocr-page"


def todo(corpus, limit: int | None = None) -> list[tuple[str, int, str]]:
    q = ("SELECT p.doc, p.page, d.path FROM pages p JOIN documents d ON d.doc = p.doc "
         "WHERE d.kind IN ('scan', 'mixed') AND p.chars <= ? AND p.source = 'pdf' ORDER BY d.path, p.page")
    rows = [tuple(r) for r in corpus.execute(q, (EMPTY,)).fetchall()]   # plain tuples: they go to the workers (pickled)
    return rows[:limit] if limit else rows


def read_page(job: tuple[str, int, str]) -> dict:
    """One page: rendered, read; the text, or the reason it failed. Runs in a worker; writes nothing but a temp image."""
    doc, page, path = job
    with tempfile.TemporaryDirectory(prefix="evd-ocr-") as tmp:
        png = Path(tmp) / "p"
        try:
            r = run_capped(["pdftoppm", "-r", "300", "-gray", "-png", "-f", str(page), "-l", str(page), "-singlefile",
                            path, str(png)], timeout=300, mem=PDF_MEM)
            if r.returncode or not png.with_suffix(".png").exists():
                return {"doc": doc, "page": page, "error": f"pdftoppm rc {r.returncode}"}
            env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
            t = run_capped(["tesseract", str(png.with_suffix(".png")), "-", "-l", "eng", "--psm", "3"],
                           timeout=600, mem=OCR_MEM, env=env)
            if t.returncode and not t.stdout.strip():
                return {"doc": doc, "page": page, "error": f"tesseract rc {t.returncode}"}
            text = " ".join(t.stdout.decode("utf-8", "replace").split())     # as the inventory keeps a page
        except (ValueError, OSError) as e:
            return {"doc": doc, "page": page, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"doc": doc, "page": page, "text": text}


def write(r: dict, corpus, findings) -> bool:
    """The page as the inventory writes one; False when it failed (left as it was, tried again next run)."""
    if "error" in r:
        return False
    doc, page, text = r["doc"], r["page"], r["text"]
    corpus.execute("UPDATE pages SET text = ?, chars = ?, source = ? WHERE doc = ? AND page = ?",
                   (text, len(text), SOURCE, doc, page))
    corpus.execute("DELETE FROM passages WHERE doc = ? AND page = ?", (doc, page))
    corpus.executemany("INSERT INTO passages(doc, page, start, end, text) VALUES (?,?,?,?,?)",
                       [(doc, page, a, b, t) for a, b, t in passages(text)])
    findings.execute("DELETE FROM identifiers WHERE doc = ? AND page = ?", (doc, page))
    findings.executemany("INSERT INTO identifiers(kind, value, valid, doc, page, start, end) VALUES (?,?,?,?,?,?,?)",
                         [(h.kind, h.value, int(h.valid), doc, page, h.start, h.end) for h in identifiers.find(text)])
    return True


def run(data_dir: Path, workers: int, limit: int | None = None, say=print) -> dict:
    corpus, findings = store.connect(data_dir, "corpus.db"), store.connect(data_dir, "findings.db")
    jobs = todo(corpus, limit)
    say(f"{len(jobs)} scanned pages without text to read")
    t0, done, failed, with_text = time.time(), 0, 0, 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(read_page, jobs, chunksize=4):
            ok = write(r, corpus, findings)
            done += 1
            failed += not ok
            with_text += ok and len(r["text"]) > EMPTY
            if done % 50 == 0:                         # short write transactions: another writer waits seconds, not
                corpus.commit()                        # minutes (a folder read in from the WebUI meanwhile)
                findings.commit()
            if done % 500 == 0:
                rate = done / (time.time() - t0)
                say(f"  {done}/{len(jobs)} read, {with_text} with text, {failed} failed, {rate:.1f} a second, "
                    f"~{(len(jobs) - done) / rate / 60:.0f} min left")
    corpus.commit()
    findings.commit()
    corpus.close()
    findings.close()
    return {"pages": done, "with_text": with_text, "failed": failed, "seconds": round(time.time() - t0, 1)}
