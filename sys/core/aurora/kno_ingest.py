# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Documents into knowledge solitons: read, chunk, write, index.

A document is read as plain text (txt, md, html, pdf through pdftotext), cut
into chunks of about AURORA_CHUNK_CHARS at paragraph boundaries (sentence
boundaries for a paragraph longer than a chunk), written to the vault and
indexed at once. A tail shorter than AURORA_CHUNK_MIN_CHARS is joined to the
chunk before it, so that no text of the document is lost.

The source id is the hash of the document bytes: importing the same file twice
changes nothing, while a new version of a file is a new source.
"""
from __future__ import annotations

import hashlib
import html.parser
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import sys_config, sys_log, txt_lang
from .sol_index import Indexer
from .sol_schema import Soliton
from .sol_writer import VaultWriter

FORMATS = {".txt": "text", ".md": "text", ".markdown": "text", ".html": "html", ".htm": "html", ".pdf": "pdf",
           ".docx": "docx", ".odt": "odt"}
SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


@dataclass
class ImportReport:
    name: str
    source_id: str
    domain: str
    chunks: int = 0
    written: int = 0
    duplicates: int = 0
    rejected: dict[str, list[str]] = field(default_factory=dict)
    indexed: int = 0
    sids: list[str] = field(default_factory=list)          # every chunk of the document, new or known
    duplicate_of: str = ""                                  # domain/source of the same document already there (C150)


class _TextOfHtml(html.parser.HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "pre"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def read_text(name: str, data: bytes, cfg: sys_config.Config) -> tuple[str, str]:
    """(text, title) of a document; the title is the file name unless the document declares one."""
    kind = FORMATS.get(Path(name).suffix.lower())
    title = Path(name).stem
    if kind is None:
        raise ValueError(f"{name}: unsupported format (supported: {', '.join(sorted(FORMATS))})")
    if kind == "pdf":
        try:
            out = subprocess.run([str(cfg["AURORA_PDFTOTEXT_BIN"]), "-enc", "UTF-8", "-", "-"], input=data,
                                 capture_output=True, timeout=300)
        except OSError as e:                          # not installed where the setting says (C223, a real Windows)
            raise ValueError(f"{name}: pdftotext not found ({cfg['AURORA_PDFTOTEXT_BIN']}): {e.strerror}") from None
        if out.returncode != 0:
            raise ValueError(f"{name}: pdftotext failed: {out.stderr.decode(errors='replace').strip()}")
        text = out.stdout.decode("utf-8", errors="replace").replace("\f", "\n\n")
        # pdftotext breaks lines inside paragraphs: rejoin them, keep blank lines, undo hyphenation.
        text = re.sub(r"-\n(?=[a-zà-ÿ])", "", text)
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        meta = subprocess.run([str(cfg["AURORA_PDFTOTEXT_BIN"]), "-htmlmeta", "-l", "1", "-", "-"], input=data,
                              capture_output=True, timeout=60).stdout.decode("utf-8", errors="replace")
        m = re.search(r"<title>(.*?)</title>", meta, re.S)
        found = html.unescape(m.group(1)).strip() if m else ""
        if found and not re.match(r"(?i)(untitled|microsoft word|document\d*$)", found):
            title = found
        return text, title
    if kind in ("docx", "odt"):
        return _office_text(name, data, kind), title
    text = data.decode("utf-8", errors="replace")
    if kind == "html":
        p = _TextOfHtml()
        p.feed(text)
        return "".join(p.parts), (p.title.strip() or title)
    first = next((l for l in text.splitlines() if l.strip()), "")
    if first.startswith("# "):
        title = first[2:].strip()
    return text, title


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ODT_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_ODT_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


def _office_text(name: str, data: bytes, kind: str) -> str:
    """The text of a Word (.docx) or OpenDocument (.odt) file, read with the standard library: paragraphs in order, a
    table row as its cells joined by " | " (a dietitian's plan is often a table — C178: .docx accepted, never read)."""
    import io
    import zipfile
    from xml.etree import ElementTree as ET
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ET.fromstring(z.read("word/document.xml" if kind == "docx" else "content.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f"{name}: not a readable {kind} file ({type(e).__name__})") from None
    if kind == "docx":
        par, tbl, row, cell = f"{_W}p", f"{_W}tbl", f"{_W}tr", f"{_W}tc"

        def runs(p) -> str:
            out = []
            for e in p.iter():
                if e.tag == f"{_W}t":
                    out.append(e.text or "")
                elif e.tag in (f"{_W}tab",):
                    out.append("\t")
                elif e.tag in (f"{_W}br", f"{_W}cr"):
                    out.append("\n")
            return "".join(out)
    else:
        par, tbl, row, cell = f"{_ODT_TEXT}p", f"{_ODT_TABLE}table", f"{_ODT_TABLE}table-row", f"{_ODT_TABLE}table-cell"

        def runs(p) -> str:
            return "".join(p.itertext())
    heading = f"{_ODT_TEXT}h"
    lines: list[str] = []

    def walk(node) -> None:
        for e in node:
            if e.tag == tbl:
                for r in e.iter(row):
                    cells = [" / ".join(t for t in (" ".join(runs(p).split()) for p in c.iter(par)) if t)
                             for c in r if c.tag == cell]
                    if any(cells):
                        lines.append(" | ".join(cells))
                lines.append("")
            elif e.tag in (par, heading):
                lines.append(runs(e).strip())
            else:
                walk(e)
    walk(root)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


SYS_TITLE = ("Return the title of this document exactly as it is written at its beginning (the paper or "
             "document title, not a journal, licence notice, arXiv stamp or author). Output only the title, or NONE.")


def title_from_text(llm, text: str) -> str | None:
    """The document's own title, found by the reasoner in its first page; accepted only if it is really
    there (it cannot be invented)."""
    head = " ".join(text[:2500].split())
    out = " ".join(llm.complete(SYS_TITLE, head, 60).answer.split()).strip(" .\"'")
    if not out or out.upper() == "NONE" or not 3 <= len(out) <= 300:
        return None
    return out if out.lower() in head.lower() else None


def chunk(text: str, size: int, min_chars: int) -> list[str]:
    """Paragraph-aligned chunks of about `size` characters; a short tail joins the previous chunk."""
    pieces = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if not para:
            continue
        if len(para) <= size:
            pieces.append(para)
            continue
        cur = ""
        for sent in SENTENCE_END.split(para):
            while len(sent) > size:                          # a "sentence" longer than a chunk: hard cut
                if cur:
                    pieces.append(cur)
                    cur = ""
                pieces.append(sent[:size])
                sent = sent[size:]
            if cur and len(cur) + 1 + len(sent) > size:
                pieces.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip()
        if cur:
            pieces.append(cur)

    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + 2 + len(p) > size and len(cur) >= min_chars:   # a short chunk is never left alone
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        if chunks and len(cur) < min_chars:
            chunks[-1] = f"{chunks[-1]}\n\n{cur}"
        else:
            chunks.append(cur)
    return chunks


class Importer:
    def __init__(self, writer: VaultWriter, indexer: Indexer, cfg: sys_config.Config | None = None, llm=None):
        self.cfg = cfg or sys_config.get()
        self.writer, self.indexer, self.llm = writer, indexer, llm
        self.log = sys_log.get_logger("ingest")

    def add(self, name: str, data: bytes, domain: str, title: str = "", origin: str = "",
            run_id: str | None = None, meta: dict | None = None) -> ImportReport:
        source_id = "doc:" + hashlib.blake2b(data, digest_size=16).hexdigest()
        rep = ImportReport(name, source_id, domain)
        text, found_title = read_text(name, data, self.cfg)
        if not title and found_title == Path(name).stem and self.llm is not None:   # no title of its own
            found_title = title_from_text(self.llm, text) or found_title
        parts = chunk(text, self.cfg["AURORA_CHUNK_CHARS"], self.cfg["AURORA_CHUNK_MIN_CHARS"])
        rep.chunks = len(parts)
        if not parts:
            raise ValueError(f"{name}: no text found")
        from . import kno_dedup                       # the same document in another form: not a second copy (C150)
        lang = txt_lang.detect(" ".join(parts[:3]))
        from .sol_reader import VaultReader
        copy_of = kno_dedup.find(self.cfg, VaultReader(self.cfg), title or found_title, lang, " ".join(parts[:3]), origin) \
            if not (meta or {}).get("replace") else None
        if copy_of:
            rep.duplicate_of = f"{copy_of[0]}/{copy_of[1]}"
            self.log.info("import %s -> %s: the same document is already in the vault (%s), not written",
                          name, domain, rep.duplicate_of)
            return rep
        extra = {"file": name, **({"origin": origin} if origin else {}),
                 **{k: str(v)[:300] for k, v in (meta or {}).items() if k in ("licence", "url") and v}}
        sols = [Soliton.new(p, domain, "knowledge", txt_lang.detect(p), source_id, title or found_title,
                            chunk_index=i, chunk_count=len(parts), extra=extra) for i, p in enumerate(parts)]
        rep.sids = [x.sid for x in sols]
        w = self.writer.add_many(sols, run_id=run_id)
        rep.written, rep.duplicates, rep.rejected = len(w.written), len(w.duplicates), w.rejected
        if w.written:
            rep.indexed = self.indexer.update(domain, run_id=run_id)
            kno_dedup.remember(self.cfg, title or found_title, domain, source_id, lang, " ".join(parts[:3]), origin)
        self.log.info("import %s -> %s/%s: %d chunks, %d written, %d duplicates, %d rejected, %d indexed",
                      name, domain, source_id, rep.chunks, rep.written, rep.duplicates, len(rep.rejected), rep.indexed)
        sys_log.trace("ingest", "import", {"name": name, "domain": domain, "source_id": source_id,
                                           "chunks": rep.chunks, "written": rep.written}, run_id=run_id)
        return rep
