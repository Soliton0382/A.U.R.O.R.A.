# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F1, the inventory: every document of a collection's folder read once (PDFs; images — jpg, png, tif even of several
pages — through OCR, Tesseract, since 10 Nov: an image-only collection) — its SHA-256, its pages' text (pdftotext, one page at a
time through the form feed), the kind (text, scan, mixed), the passages for the search (FTS5), the identifiers found on
each page (checked). Resumable: a file already read with the same size and time is skipped. The reading in
EVD_WORKERS processes, the writing in this one (SQLite: one writer). The PDFs are never written (law 5)."""
from __future__ import annotations

import hashlib
import os
import resource
import select
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import docids, identifiers, store

PASSAGE, OVERLAP = 1200, 200          # characters (I1: median 1,108 a page): one passage ≈ one page
SCAN_BELOW = 100                       # characters a page under which it counts as a scan (I1: 5.3 % of the PDFs)
PDF = (".pdf",)
IMAGES = (".jpg", ".jpeg", ".png", ".tif", ".tiff")    # I3: Tesseract 0.9 s an image on one core, V8's text matched

# B31 — the readers' ceilings, measured on the corpus's extremes (11 Nov, 1,403,620 documents already read):
# the biggest PDF (9,824 pages, 764 MB) gave pdftotext 17.8 MB of text at a virtual peak of 90 MB; pdfinfo 59 MB;
# the biggest image (5376x7225, 2.5 MB jpg) gave tesseract 1 KB at a virtual peak of 476 MB. The caps are ~4x those
# peaks and 3.6x that output: a PDF bomb (a page that unpacks to GBs, a never-ending text stream) is cut, not the
# corpus. Not measured: a worse document than these; RLIMIT_AS counts address space, so a reader that maps more than
# it uses would be refused early — none of the three did. Worst case in RAM: EVD_WORKERS x (OUT_CAP + the child's cap).
PDF_MEM, OCR_MEM = 1 << 30, 2 << 30    # RLIMIT_AS of pdftotext / tesseract, bytes
OUT_CAP = 64 << 20                     # a reader's stdout beyond this is refused (~58,000 pages at the median 1,108)
ERR_CAP = 64 << 10                     # of stderr only the first 64 KB are kept (read_doc shows 120 characters)


def _limits(mem: int):
    """A child's preexec_fn: its address space capped at mem bytes (a malloc beyond it fails, the child dies alone)."""
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    return apply


def run_capped(cmd: list[str], timeout: float, mem: int, env: dict | None = None,
               cap: int | None = None) -> subprocess.CompletedProcess:
    """subprocess.run(capture_output=True, timeout) with two more guards (B31): the child's address space capped at
    mem bytes, its stdout refused beyond cap bytes (OUT_CAP; ValueError, the child killed) — the pipes read as they
    fill, so a noisy stderr never deadlocks the child, and nothing bigger than cap ever sits in this process's memory."""
    cap = OUT_CAP if cap is None else cap
    deadline = time.monotonic() + timeout
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, preexec_fn=_limits(mem)) as proc:
        # fd -> [chunks, bytes so far, cap, refuse beyond the cap (stdout) or just stop keeping (stderr)]
        pipes = {proc.stdout.fileno(): [[], 0, cap, True], proc.stderr.fileno(): [[], 0, ERR_CAP, False]}
        open_fds = set(pipes)
        try:
            while open_fds:
                ready, _, _ = select.select(sorted(open_fds), [], [], max(0.0, deadline - time.monotonic()))
                if not ready:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                for fd in ready:
                    block = os.read(fd, 1 << 16)
                    if not block:                    # this pipe is closed: what it gave stays in pipes
                        open_fds.discard(fd)
                        continue
                    chunks, n, limit, strict = pipes[fd]
                    pipes[fd][1] = n + len(block)
                    if n + len(block) > limit:
                        if strict:
                            raise ValueError(f"{cmd[0]} wrote more than {limit:,} bytes: refused (B31)")
                        continue                     # stderr: the head is enough for the error's reason
                    chunks.append(block)
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        out, err = (b"".join(pipes[f][0]) for f in (proc.stdout.fileno(), proc.stderr.fileno()))
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def passages(text: str) -> list[tuple[int, int, str]]:
    """(start, end, text) windows over one page's text, cut at a space when there is one."""
    out, i, n = [], 0, len(text)
    while i < n:
        j = min(n, i + PASSAGE)
        if j < n:
            k = text.rfind(" ", i + PASSAGE // 2, j)
            j = k if k > i else j
        piece = text[i:j].strip()
        if len(piece) >= 40:
            out.append((i, j, piece))
        if j >= n:
            break
        i = max(j - OVERLAP, i + 1)
    return out


def _ocr(p: Path) -> bytes:
    """An image's text: Tesseract, one thread (the processes are the parallelism), pages split by a form feed."""
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    run = run_capped(["tesseract", str(p), "-", "-l", "eng", "--psm", "3", "-c", "preserve_interword_spaces=1"],
                     timeout=600, mem=OCR_MEM, env=env)
    if run.returncode and not run.stdout.strip():    # killed by its memory cap, or no model: said, not an empty page
        raise ValueError(f"tesseract failed (rc {run.returncode}; {run.stderr.decode('utf-8', 'replace').strip()[:120]})")
    return run.stdout


def read_doc(path: str) -> dict:
    """Everything the archive keeps of one document, without writing anything (runs in a worker)."""
    p = Path(path)
    st = p.stat()
    image = p.suffix.lower() in IMAGES
    out = {"path": path, "bytes": st.st_size, "mtime": st.st_mtime, "source": "ocr" if image else "pdf"}
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        out["sha256"] = h.hexdigest()
        if image:
            raw = _ocr(p)
        else:
            run = run_capped(["pdftotext", "-enc", "UTF-8", str(p), "-"], timeout=300, mem=PDF_MEM)
            raw = run.stdout
        pages = raw.decode("utf-8", "replace").split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        if not image and not pages:                      # rc 0 and nothing: a broken xref (audit E4, B19)
            raise ValueError(f"pdftotext read no page (rc {run.returncode}; pdfinfo: {_pdfinfo_pages(p)}; "
                             f"{run.stderr.decode('utf-8', 'replace').strip()[:120]})")
        pages = [" ".join(t.split()) for t in pages]
        out["pages"] = pages
        scans = sum(1 for t in pages if len(t) < SCAN_BELOW)
        out["kind"] = ("image" if image else "scan" if pages and scans == len(pages) else "mixed" if scans else "text")
        out["ids"] = [(n, h.kind, h.value, int(h.valid), h.start, h.end)
                      for n, t in enumerate(pages, 1) for h in identifiers.find(t)]
    except Exception as e:  # noqa: BLE001 — said in the archive, the next run tries again
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    return out


def _pdfinfo_pages(p: Path) -> str:
    """How many pages pdfinfo sees, for the reason of a PDF pdftotext could not read (asked only then)."""
    try:
        out = run_capped(["pdfinfo", str(p)], timeout=60, mem=PDF_MEM).stdout.decode("utf-8", "replace")
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return type(e).__name__
    return next((line.split(":", 1)[1].strip() + " pages" for line in out.splitlines() if line.startswith("Pages:")),
                "no page count")


read_pdf = read_doc                     # the name of before (tests, scripts)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def plan(sources: Path, corpus, exts: tuple[str, ...] = PDF, verify: bool = True) -> dict:
    """What a folder holds against the archive, whatever its path (owner, 10 Nov: «se per errore gli ri do in pasto la
    medesima cartella in percorso diverso lui non riparte da capo»): a document is known by its identity (collection
    and number, docids) and its size — not by where it lies. {"read": paths to read, "moved": [(key, new path)],
    "same": n already read, "conflicts": [(path, why)]}. A known document found elsewhere only changes its path (its
    pages, passages and vectors stay); a file named like a known one with other bytes is a conflict, never written
    over. verify (the default, owner 10 Nov): a moved one's SHA-256 compared with the one kept at its first reading —
    a move is paid once, in reading its bytes; the files that did not move are never read again."""
    known = {r[0]: (r[1], r[2], r[3], "failed" if r[5] == 0 and str(r[1]).lower().endswith(".pdf") else r[4])
             for r in corpus.execute(                   # a PDF kept with 0 pages: read again, now it fails aloud (B19)
                 "SELECT doc, path, bytes, sha256, status, COALESCE(pages, 0) FROM documents")}
    out = {"read": [], "moved": [], "same": 0, "conflicts": []}
    with os.scandir(sources) as it:
        for e in it:
            if not (e.is_file() and e.name.lower().endswith(exts)):
                continue
            key, size = docids.parse(e.path).key, e.stat().st_size
            k = known.get(key)
            if k is None or k[3] not in ("text", "indexed"):
                out["read"].append(e.path)
            elif k[1] != size or (verify and k[0] != e.path and _sha(e.path) != k[2]):
                out["conflicts"].append((e.path, f"{key} is in the archive with other bytes ({k[0]})"))
            elif k[0] != e.path:
                out["moved"].append((key, e.path))
            else:
                out["same"] += 1
    out["read"].sort()
    return out


def todo(sources: Path, corpus, exts: tuple[str, ...] = PDF) -> list[str]:
    return plan(sources, corpus, exts)["read"]


def write(r: dict, corpus, findings) -> None:
    d = docids.parse(r["path"])
    if "error" in r:
        corpus.execute("INSERT INTO documents(doc, collection, number, path, bytes, mtime, status, error) "
                       "VALUES (?,?,?,?,?,?, 'failed', ?) ON CONFLICT(doc) DO UPDATE SET status='failed', error=excluded.error",
                       (d.key, d.collection, d.number, r["path"], r["bytes"], r["mtime"], r["error"]))
        return
    corpus.execute("DELETE FROM pages WHERE doc = ?", (d.key,))
    corpus.execute("DELETE FROM passages WHERE doc = ?", (d.key,))
    findings.execute("DELETE FROM identifiers WHERE doc = ?", (d.key,))
    corpus.execute("INSERT INTO documents(doc, collection, number, path, sha256, bytes, mtime, pages, kind, official_url, "
                   "status) VALUES (?,?,?,?,?,?,?,?,?,?, 'text') ON CONFLICT(doc) DO UPDATE SET sha256=excluded.sha256, "
                   "bytes=excluded.bytes, mtime=excluded.mtime, pages=excluded.pages, kind=excluded.kind, "
                   "official_url=excluded.official_url, status='text', error=NULL",
                   (d.key, d.collection, d.number, r["path"], r["sha256"], r["bytes"], r["mtime"], len(r["pages"]),
                    r["kind"], d.official_url()))
    for n, text in enumerate(r["pages"], 1):
        corpus.execute("INSERT INTO pages(doc, page, text, chars, source) VALUES (?,?,?,?,?)",
                       (d.key, n, text, len(text), r.get("source", "pdf")))
        corpus.executemany("INSERT INTO passages(doc, page, start, end, text) VALUES (?,?,?,?,?)",
                           [(d.key, n, a, b, t) for a, b, t in passages(text)])
    findings.executemany("INSERT INTO identifiers(kind, value, valid, doc, page, start, end) VALUES (?,?,?,?,?,?,?)",
                         [(k, v, ok, d.key, n, a, b) for n, k, v, ok, a, b in r["ids"]])


def run(sources: Path, data_dir: Path, workers: int, limit: int | None = None, say=print, exts=PDF,
        verify: bool = True) -> dict:
    store.create(data_dir)
    corpus, findings = store.connect(data_dir, "corpus.db"), store.connect(data_dir, "findings.db")
    p = plan(sources, corpus, exts, verify)
    for key, path in p["moved"]:                       # found elsewhere: only its path changes
        corpus.execute("UPDATE documents SET path = ? WHERE doc = ?", (path, key))
    corpus.commit()
    for path, why in p["conflicts"][:20]:
        say(f"  conflict, not read: {why} — {path}")
    paths = p["read"][:limit] if limit else p["read"]
    say(f"{len(paths)} documents to read in {sources} · {p['same']} already read · {len(p['moved'])} moved (path "
        f"updated, nothing read again) · {len(p['conflicts'])} conflicts")
    t0, done, failed = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(read_doc, paths, chunksize=8 if exts != PDF else 32):
            write(r, corpus, findings)
            done += 1
            failed += "error" in r
            if done % (500 if exts != PDF else 2000) == 0:
                corpus.commit()
                findings.commit()
                rate = done / (time.time() - t0)
                say(f"  {done}/{len(paths)} read, {failed} failed, {rate:.0f} a second, "
                    f"~{(len(paths) - done) / rate / 60:.0f} min left")
    corpus.commit()
    findings.commit()
    out = {"read": done, "failed": failed, "moved": len(p["moved"]), "conflicts": len(p["conflicts"]),
           "seconds": round(time.time() - t0, 1)}
    corpus.close()
    findings.close()
    return out
