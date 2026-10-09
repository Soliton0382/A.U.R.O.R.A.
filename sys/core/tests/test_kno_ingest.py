# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import shutil

import pytest

from aurora.kno_ingest import Importer, chunk, read_text
from aurora.sol_index import Indexer
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter
from test_sol_index import FakeEncoder

PARA = "La locazione è il contratto col quale una parte si obbliga a far godere all'altra una cosa. "


def test_chunk_keeps_every_word_and_respects_size():
    text = "\n\n".join(PARA * n for n in (3, 40, 1, 7, 2))
    parts = chunk(text, 1000, 300)
    assert " ".join(" ".join(p.split()) for p in parts).split() == text.split()
    assert all(len(p) <= 1000 + 300 for p in parts)          # a short tail may join the last chunk


def test_short_tail_joins_previous_chunk():
    parts = chunk(("A" * 900) + "\n\n" + "coda breve.", 1000, 300)
    assert len(parts) == 1 and parts[0].endswith("coda breve.")


def test_short_single_document_is_kept():
    assert chunk("Art. 1571. Nozione.", 4000, 300) == ["Art. 1571. Nozione."]


def test_oversize_sentence_is_cut_hard():
    parts = chunk("x" * 2500, 1000, 1)
    assert [len(p) for p in parts] == [1000, 1000, 500]


def test_read_markdown_title_and_html_text(cfg):
    text, title = read_text("note.md", "# Titolo vero\n\ncorpo".encode(), cfg)
    assert title == "Titolo vero" and "corpo" in text
    html = b"<html><head><title>Pagina</title><style>x{}</style></head><body><p>uno</p><script>no()</script><p>due</p></body></html>"
    text, title = read_text("p.html", html, cfg)
    assert title == "Pagina" and "uno" in text and "due" in text and "no()" not in text and "x{}" not in text


def test_unsupported_format(cfg):
    with pytest.raises(ValueError, match="unsupported"):
        read_text("a.xlsx", b"x", cfg)                     # .docx is read since C178


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext not installed")
def test_pdf_failure_is_reported(cfg):
    with pytest.raises(ValueError, match="pdftotext (failed|not found)"):      # not found: a Windows without Poppler
        read_text("broken.pdf", b"not a pdf", cfg)


def test_a_missing_pdftotext_is_said_not_a_crash(cfg):
    """C223: on a real Windows the program was not where the setting said and the import died of FileNotFoundError."""
    cfg.values["AURORA_PDFTOTEXT_BIN"] = str(cfg.root / "no" / "pdftotext")
    with pytest.raises(ValueError, match="pdftotext not found"):
        read_text("doc.pdf", b"%PDF-1.4", cfg)


def test_import_writes_indexes_and_is_idempotent(cfg):
    enc = FakeEncoder()
    imp = Importer(VaultWriter(cfg), Indexer(enc, cfg), cfg)
    data = "\n\n".join(f"Articolo {i}. " + PARA * 30 for i in range(4)).encode()   # distinct: same text = same sid
    first = imp.add("codice.txt", data, "law_it")
    assert first.chunks == first.written == first.indexed > 1 and not first.rejected
    again = imp.add("copia.txt", data, "law_it")
    assert again.source_id == first.source_id and again.written == 0 and again.duplicates == first.chunks
    assert VaultReader(cfg).count("law_it") == {"law_it": first.chunks}


class _LLM:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, max_tokens, think=False):
        return type("C", (), {"answer": self.reply})()


def test_title_from_text_accepts_only_a_title_that_is_in_the_text():
    from aurora.kno_ingest import title_from_text
    text = "Licence notice.\n\narXiv:1706.03762v7\n\nAttention Is All You Need\n\nAshish Vaswani"
    assert title_from_text(_LLM("Attention Is All You Need"), text) == "Attention Is All You Need"
    assert title_from_text(_LLM("A Title The Model Made Up"), text) is None       # not in the text
    assert title_from_text(_LLM("NONE"), text) is None
